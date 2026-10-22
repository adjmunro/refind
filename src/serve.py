#!/usr/bin/env python3
"""The configurator's server: serves preview/ and applies saved settings.

    python3 src/serve.py [--host IP] [--port 8765]     (normally via scripts/refind-manager)

Binds to localhost and this machine's Tailscale address, nothing else, so your
devices reach it at http://<tailnet name>:8765/ (port 80 is the magikarp home page).

    GET  /api/state   config, git state, and what's deployed to the ESP
    POST /api/save    {config}: write src/config.json, build, commit, push,
                      then start refind-esp-sync.service to update the ESP
"""
import argparse
import http.server
import json
import pathlib
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = ROOT / "src" / "config.json"
STATE = pathlib.Path("/var/lib/refind-manager")
VERSION = pathlib.Path("/usr/local/lib/refind-manager/VERSION")
GENERATED = ["src/config.json", "refind.conf", "themes", "preview", "docs"]
LOCK = threading.Lock()


def run(*cmd, timeout=300):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return None


def system_state():
    want = run("scripts/system-version.sh").stdout.strip()
    have = read(VERSION)
    return {"installed": have is not None, "current": have == want,
            "deployed": read(STATE / "deployed"), "active": read(STATE / "active")}


def git_state():
    run("git", "fetch", "-q", timeout=30)
    counts = run("git", "rev-list", "--left-right", "--count", "HEAD...@{u}").stdout.split()
    return {"head": run("git", "log", "-1", "--format=%h %s").stdout.strip(),
            "dirty": bool(run("git", "status", "--porcelain").stdout.strip()),
            "ahead": int(counts[0]) if counts else 0, "behind": int(counts[1]) if counts else 0}


def save(config):
    """Each step is {step, ok, detail}; stops at the first failure."""
    steps = []

    def step(name, ok, detail=""):
        steps.append({"step": name, "ok": ok, "detail": detail.strip()})
        return ok

    pull = run("git", "pull", "--ff-only", "-q")
    if not step("Sync with GitHub", pull.returncode == 0, pull.stderr):
        return steps
    previous = CONFIG.read_text()
    CONFIG.write_text(json.dumps(config, indent=2) + "\n")
    build = run(sys.executable, "src/build.py", "--preview")
    if not step("Build themes", build.returncode == 0, build.stderr[-1500:] or build.stdout[-300:]):
        CONFIG.write_text(previous)
        run("git", "checkout", "--", *GENERATED)   # drop any half-written output
        return steps
    run("git", "add", "--", *GENERATED)
    if run("git", "diff", "--cached", "--quiet").returncode:
        commit = run("git", "commit", "-q", "-m", "Configure boot menu", "-m", summary(config))
        if not step("Commit", commit.returncode == 0, commit.stderr):
            return steps
        push = run("git", "push", "-q")
        if not step("Push", push.returncode == 0, push.stderr):
            return steps
    else:
        step("Commit", True, "no changes to commit")
    sysinfo = system_state()
    if not sysinfo["current"]:
        step("Update boot menu", False, "System setup needed: double-click rEFInd Manager on magikarp "
             "and approve the password prompt once. Your changes are saved and pushed.")
        return steps
    sync = run("systemctl", "start", "refind-esp-sync.service")
    log = read(STATE / "last-sync.log") or ""
    step("Update boot menu", sync.returncode == 0, log or sync.stderr)
    return steps


def summary(cfg):
    rot = cfg["rotation"]
    lines = [f"rotation: {rot['mode']} over {', '.join(rot['themes'])}" if rot["mode"] != "off"
             else f"theme: {cfg['theme']}",
             f"boot: default {cfg['boot']['default']}, timeout {cfg['boot']['timeout']}s",
             "backgrounds: " + ", ".join(f"{t}={v['background']}" for t, v in cfg["themes"].items()),
             "icons: " + ", ".join(f"{s}={c}" for s, c in cfg["icons"].items())]
    return "\n".join(lines)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        if not self.path.startswith(("/preview/candidates/", "/preview/backgrounds/", "/themes/")):
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/preview"):
            self.send_response(302)
            self.send_header("Location", "/preview/")
            self.end_headers()
        elif path == "/api/ping":
            self.reply(200, {"ok": True})
        elif path == "/api/state":
            self.reply(200, {"config": json.loads(CONFIG.read_text()), "git": git_state(), "system": system_state()})
        elif any(part.startswith(".") for part in path.split("/")):
            self.send_error(404)
        else:
            super().do_GET()

    def do_POST(self):
        if self.path != "/api/save":
            return self.send_error(404)
        try:
            config = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            assert isinstance(config, dict) and set(config) == set(json.loads(CONFIG.read_text()))
        except (ValueError, AssertionError):
            return self.reply(400, {"error": "body must be the full config object"})
        if not LOCK.acquire(blocking=False):
            return self.reply(409, {"error": "a save is already running"})
        try:
            started = time.time()
            steps = save(config)
            self.reply(200, {"steps": steps, "ok": all(s["ok"] for s in steps), "seconds": round(time.time() - started, 1)})
        finally:
            LOCK.release()


def tailscale_ip():
    out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True).stdout.split()
    return out[0] if out else "127.0.0.1"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", action="append",
                    help="address to bind; repeatable (default: 127.0.0.1 and the Tailscale IPv4)")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    hosts = args.host or sorted({"127.0.0.1", tailscale_ip()})
    servers = [http.server.ThreadingHTTPServer((h, args.port), Handler) for h in hosts]
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    print(f"Serving {ROOT} on " + ", ".join(f"http://{h}:{args.port}/" for h in hosts), flush=True)
    servers[0].serve_forever()
