#!/usr/bin/env python3
"""Serve the preview over Tailscale, and let the icon lab save its picks.

    python3 src/serve.py [--host IP] [--port 8765]     (or: scripts/preview.sh)

Binds to magikarp's Tailscale address by default, so it's reachable from your
other devices at http://magikarp:8765/ and nowhere else. Besides static files
it has one write endpoint:

    POST /api/choices {slot: candidate-id, ...}
        writes src/choices.json, runs src/build.py --preview, then commits the
        result (choices + generated files only) and pushes it.
"""
import argparse
import http.server
import json
import pathlib
import re
import subprocess
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHOICES = ROOT / "src" / "choices.json"
GENERATED = ["src/choices.json", "themes", "preview", "docs"]
LOCK = threading.Lock()


def run(*cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def valid(choices):
    slots = json.loads(CHOICES.read_text())
    if not isinstance(choices, dict) or set(choices) != set(slots):
        return f"expected exactly these slots: {sorted(slots)}"
    for slot, cid in choices.items():
        if not isinstance(cid, str) or not re.fullmatch(r"[\w.-]+", cid) \
                or not any((ROOT / "src" / "candidates" / slot).glob(f"{cid}.*")):
            return f"no candidate {cid!r} for {slot}"
    return None


def save(choices):
    """Write, rebuild, commit, push. Returns a list of log lines."""
    log = []
    pull = run("git", "pull", "--ff-only", "-q")
    if pull.returncode:
        log.append("git pull failed (saving anyway): " + pull.stderr.strip())
    CHOICES.write_text(json.dumps(choices, indent=2) + "\n")
    build = run(sys.executable, "src/build.py", "--preview")
    if build.returncode:
        raise RuntimeError("build failed:\n" + build.stderr[-2000:])
    log.append("rebuilt themes")
    run("git", "add", "--", *GENERATED)
    message = "Pick icons in the lab\n\n" + "\n".join(f"{s}: {c}" for s, c in choices.items())
    commit = run("git", "commit", "-q", "-m", message, "--", *GENERATED)
    if commit.returncode:
        log.append("nothing new to commit")
        return log
    log.append("committed " + run("git", "rev-parse", "--short", "HEAD").stdout.strip())
    push = run("git", "push", "-q")
    log.append("pushed" if push.returncode == 0 else "push failed: " + push.stderr.strip())
    return log


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

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
        if self.path in ("/", "/preview"):
            self.send_response(302)
            self.send_header("Location", "/preview/")
            self.end_headers()
        elif self.path == "/api/ping":
            self.reply(200, {"save": True})
        elif any(part.startswith(".") for part in self.path.split("?")[0].split("/")):
            self.send_error(404)
        else:
            super().do_GET()

    def do_POST(self):
        if self.path != "/api/choices":
            return self.send_error(404)
        try:
            choices = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except ValueError:
            return self.reply(400, {"error": "body must be JSON"})
        if err := valid(choices):
            return self.reply(400, {"error": err})
        with LOCK:
            try:
                self.reply(200, {"log": save(choices)})
            except RuntimeError as e:
                self.reply(500, {"error": str(e)})


def tailscale_ip():
    out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True).stdout.split()
    return out[0] if out else "127.0.0.1"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default=None, help="address to bind (default: this machine's Tailscale IPv4)")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    host = args.host or tailscale_ip()
    server = http.server.ThreadingHTTPServer((host, args.port), Handler)
    print(f"Serving {ROOT} on http://{host}:{args.port}/preview/", flush=True)
    server.serve_forever()
