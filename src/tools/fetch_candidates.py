#!/usr/bin/env python3
"""Collect candidate icons for each slot into src/candidates/<slot>/<id>.<ext>.

Sources are permissively licensed icon sets from npm (pinned below), the three
upstream themes in upstream/, the distro's own CachyOS artwork, and our own
masters in src/icons. Writes src/candidates/SOURCES.md with provenance.
`python3 src/build.py` then renders every candidate in every theme's colours
for the icon lab in preview/index.html.

    python3 src/tools/fetch_candidates.py
"""
import json
import pathlib
import shutil
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "src" / "candidates"

PACKAGES = {  # npm package: (version, licence)
    "@mdi/svg": ("7.4.47", "Apache-2.0"),
    "@phosphor-icons/core": ("2.1.1", "MIT"),
    "@tabler/icons": ("3.49.0", "MIT"),
    "lucide-static": ("1.61.0", "ISC"),
    "bootstrap-icons": ("1.13.2", "MIT"),
    "remixicon": ("4.9.1", "Apache-2.0"),
    "@material-symbols/svg-400": ("0.48.1", "Apache-2.0"),
    "simple-icons": ("16.35.0", "CC0-1.0"),
}
PREFIX = {"@mdi/svg": "mdi", "@phosphor-icons/core": "phosphor", "@tabler/icons": "tabler",
          "lucide-static": "lucide", "bootstrap-icons": "bootstrap", "remixicon": "remix",
          "@material-symbols/svg-400": "material", "simple-icons": "simple"}


def npm(pkg, *files):
    """Candidates from an npm package; each file is a path suffix like 'fill/power-fill.svg'."""
    return [("npm", pkg, f) for f in files]


def phosphor(name, weights=("thin", "light", "regular", "bold", "fill", "duotone")):
    return npm("@phosphor-icons/core", *[f"{w}/{name}{'' if w == 'regular' else '-' + w}.svg" for w in weights])


def local(*paths):
    return [("local", None, p) for p in paths]


FANMADE = "https://raw.githubusercontent.com/mitsuaki-41/CachyOS-logo-redesign/HEAD/CachyOS_logo_fan-made.svg"

SLOTS = {
    "os_cachyos": local("src/icons/os_cachyos.svg", "/usr/share/icons/cachyos.svg",
                        "/usr/share/icons/hicolor/scalable/apps/org.cachyos.hello.svg",
                        "/usr/share/icons/hicolor/scalable/apps/cachyos-pi.png")
                  + [("url", "MIT (mitsuaki-41/CachyOS-logo-redesign)", FANMADE)]
                  + npm("simple-icons", "icons/cachyos.svg", "icons/archlinux.svg")
                  + npm("@mdi/svg", "svg/arch.svg")
                  + local("upstream/rEFInd-minimal/icons/os_arch.png", "upstream/refind-ambience/icons/os_arch.png"),
    "os_win": local("src/icons/os_win.svg", "upstream/refind-ambience/icons/os_win.png",
                    "upstream/refind-ambience/icons/os_win10.png", "upstream/rEFInd-minimal/icons/os_win.png",
                    "upstream/refind-sublime/icons/os_win.png")
              + npm("@mdi/svg", "svg/microsoft-windows-classic.svg", "svg/microsoft-windows.svg")
              + phosphor("windows-logo", ("regular", "fill"))
              + npm("@tabler/icons", "outline/brand-windows.svg", "filled/brand-windows.svg")
              + npm("bootstrap-icons", "icons/windows.svg")
              + npm("remixicon", "/windows-fill.svg", "/windows-line.svg")
              + npm("simple-icons", "icons/windows.svg", "icons/windows11.svg", "icons/windowsxp.svg"),
    "os_mint": local("src/icons/os_mint.svg", "upstream/refind-ambience/icons/os_linuxmint.png",
                     "upstream/rEFInd-minimal/icons/os_linuxmint.png", "upstream/refind-sublime/icons/os_linuxmint.png")
               + npm("simple-icons", "icons/linuxmint.svg")
               + npm("@mdi/svg", "svg/linux-mint.svg", "svg/leaf.svg", "svg/sprout.svg")
               + phosphor("leaf") + phosphor("plant", ("regular", "fill"))
               + npm("@tabler/icons", "outline/leaf.svg", "filled/leaf.svg", "outline/plant-2.svg")
               + npm("lucide-static", "icons/leaf.svg", "icons/sprout.svg")
               + npm("remixicon", "/leaf-fill.svg", "/leaf-line.svg", "/seedling-fill.svg"),
    "func_shutdown": local("src/icons/func_shutdown.svg", "upstream/refind-ambience/icons/func_shutdown.png",
                           "upstream/refind-sublime/icons/func_exit.png")
                     + npm("@mdi/svg", "svg/power.svg", "svg/power-standby.svg")
                     + phosphor("power")
                     + npm("@tabler/icons", "outline/power.svg")
                     + npm("lucide-static", "icons/power.svg", "icons/circle-power.svg")
                     + npm("bootstrap-icons", "icons/power.svg")
                     + npm("remixicon", "/shut-down-line.svg", "/shut-down-fill.svg")
                     + npm("@material-symbols/svg-400", "rounded/power_settings_new.svg", "rounded/mode_off_on.svg"),
    "func_reset": local("src/icons/func_reset.svg", "upstream/refind-ambience/icons/func_reset.png",
                        "upstream/refind-sublime/icons/func_reset.png")
                  + npm("@mdi/svg", "svg/restart.svg", "svg/refresh.svg")
                  + phosphor("arrow-clockwise")
                  + npm("@tabler/icons", "outline/refresh.svg", "outline/rotate-clockwise.svg")
                  + npm("lucide-static", "icons/rotate-cw.svg", "icons/refresh-cw.svg")
                  + npm("bootstrap-icons", "icons/arrow-clockwise.svg")
                  + npm("remixicon", "/restart-line.svg", "/restart-fill.svg")
                  + npm("@material-symbols/svg-400", "rounded/restart_alt.svg", "rounded/refresh.svg"),
    "func_firmware": local("src/icons/func_firmware.svg", "upstream/refind-ambience/icons/func_firmware.png")
                     + npm("@mdi/svg", "svg/chip.svg", "svg/cpu-64-bit.svg")
                     + phosphor("cpu")
                     + npm("@tabler/icons", "outline/cpu.svg", "filled/cpu.svg")
                     + npm("lucide-static", "icons/cpu.svg", "icons/microchip.svg")
                     + npm("bootstrap-icons", "icons/cpu.svg", "icons/cpu-fill.svg")
                     + npm("remixicon", "/cpu-line.svg", "/cpu-fill.svg")
                     + npm("@material-symbols/svg-400", "rounded/memory.svg", "rounded/memory-fill.svg",
                           "rounded/developer_board.svg"),
}

_listing = {}


def find(pkg, suffix):
    ver = PACKAGES[pkg][0]
    if pkg not in _listing:
        url = f"https://data.jsdelivr.com/v1/packages/npm/{pkg}@{ver}?structure=flat"
        _listing[pkg] = [f["name"] for f in json.load(urllib.request.urlopen(url))["files"]]
    hits = [n for n in _listing[pkg] if n.endswith(suffix if suffix.startswith("/") else "/" + suffix)]
    return f"https://cdn.jsdelivr.net/npm/{pkg}@{ver}{hits[0]}" if hits else None


def candidate_id(kind, pkg, path):
    stem = pathlib.PurePosixPath(path).stem
    if kind == "npm":
        return f"{PREFIX[pkg]}-{stem}"
    if kind == "url":
        return "fanmade-" + stem.lower().replace("_", "-")
    if path.startswith("src/icons/"):
        return "own"
    if path.startswith("upstream/"):
        return path.split("/")[1].lower().replace("refind-", "") + "-" + stem
    return "system-" + stem.replace("org.", "")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    rows, missing = [], []
    for slot, specs in SLOTS.items():
        (OUT / slot).mkdir(parents=True)
        for kind, pkg, path in specs:
            cid = candidate_id(kind, pkg, path)
            if kind == "npm":
                url = find(pkg, path)
                if not url:
                    missing.append(f"{slot}: {pkg} {path}")
                    continue
                dest = OUT / slot / f"{cid}.svg"
                dest.write_bytes(urllib.request.urlopen(url).read())
                rows.append((slot, cid, f"[{pkg}@{PACKAGES[pkg][0]}]({url})", PACKAGES[pkg][1]))
            elif kind == "url":
                dest = OUT / slot / f"{cid}.svg"
                dest.write_bytes(urllib.request.urlopen(path).read())
                rows.append((slot, cid, f"[{path.split('/')[4]}]({path})", pkg))
            else:
                src = pathlib.Path(path) if path.startswith("/") else ROOT / path
                if not src.exists():
                    missing.append(f"{slot}: {path}")
                    continue
                dest = OUT / slot / f"{cid}{src.suffix}"
                shutil.copy(src, dest)
                licence = ("this repo" if cid == "own" else "upstream theme, see its LICENSE"
                           if path.startswith("upstream/") else "CachyOS artwork (trademark)")
                rows.append((slot, cid, f"`{path}`", licence))
    with open(OUT / "SOURCES.md", "w") as f:
        f.write("# Icon candidates\n\nGenerated by `src/tools/fetch_candidates.py`. "
                "Brand logos are trademarks of their owners; used here for personal theming.\n\n"
                "| Slot | Candidate | Source | Licence |\n|---|---|---|---|\n")
        f.writelines(f"| {s} | `{c}` | {src} | {lic} |\n" for s, c, src, lic in rows)
    print(f"{len(rows)} candidates in {OUT.relative_to(ROOT)}")
    for m in missing:
        print("  not found:", m)


if __name__ == "__main__":
    main()
