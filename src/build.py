#!/usr/bin/env python3
"""Build everything that gets deployed from src/config.json.

    python3 src/build.py            # rebuild refind.conf and themes/*
    python3 src/build.py --preview  # also write docs/preview-<theme>.jpg mock-ups

Writes refind.conf (from src/refind.conf.in), themes/<name>/ (theme.conf,
background, icons, selection marks, label font), and preview/ data for the
configurator (preview/index.html). Needs rsvg-convert (librsvg) and Pillow.
The output is committed, so deploying never needs these tools.

src/config.json is what the configurator edits: icon picks, each theme's
background, rotation, boot timeout and default. Theme palettes live in THEMES below.
"""
import argparse
import hashlib
import io
import json
import pathlib
import re
import subprocess

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CANDIDATES = SRC / "candidates"
PREVIEW = ROOT / "preview"

SCREEN = (1920, 1080)                       # magikarp's display; backgrounds are cut to this exactly
BIG, SMALL = 128, 48                        # big_icon_size / small_icon_size in src/refind.conf.in
BIG_TILE, SMALL_TILE = BIG * 9 // 8, SMALL * 4 // 3   # rEFInd's tile sizes for those icon sizes
FONT_FILE = "/usr/share/fonts/Adwaita/AdwaitaMono-Regular.ttf"
FONT_PX = 22
# How much of the icon square a glyph's bounding box fills, so every candidate
# comes out the same visual size whatever padding its source had.
FILL = {"os": 0.74, "func": 0.80}

# Things deleted in the configurator: never offered, generated or fetched again.
REMOVED = json.loads((SRC / "removed.json").read_text()) if (SRC / "removed.json").exists() else {}


def background_sources():
    """Backgrounds anyone can pick for any theme: the upstream originals plus
    src/backgrounds/*, minus deleted ones."""
    found = {
        "minimal": ROOT / "upstream" / "rEFInd-minimal" / "background.png",
        "ambience": ROOT / "upstream" / "refind-ambience" / "background.png",
        "sublime": ROOT / "upstream" / "refind-sublime" / "background.png",
        **{p.stem: p for p in sorted((SRC / "backgrounds").glob("*.png"))},
    }
    return {k: v for k, v in found.items() if v.exists() and k not in REMOVED.get("backgrounds", [])}


BACKGROUNDS = background_sources()

# Theme palettes. Our own SVGs (candidate id "own") use #ffffff for the glyph
# colour and #999999 for the shade; every other candidate is single-tone and is
# recoloured from its alpha channel. shadow: (colour, strength, blur px at 48px,
# drop px at 48px); a coloured shadow with no drop is a glow.
THEMES = {
    "minimal": dict(
        glyph="#0e0f10", shade=("#ffffff", 0.45), alpha=0.94, shadow=None,
        mark=("caret", "#0e0f10", 0.85), small=("disc", "#0e0f10", 0.10),
    ),
    "ambience": dict(
        glyph="#ffffff", shade=("#000000", 0.25), alpha=0.95, shadow=("#000000", 0.25, 1.0, 1),
        mark=("bar", "#ffffff", 0.95), small=("disc", "#ffffff", 0.20),
    ),
    "sublime": dict(
        glyph="#f5f1e6", shade=("#000000", 0.28), alpha=0.92, shadow=("#000000", 0.45, 1.0, 1),
        mark=("diamond", "#f5f1e6", 0.90), small=("disc", "#ffffff", 0.20),
    ),
    "synthwave": dict(
        glyph="#fff0fb", shade=("#ff2bd6", 0.45), alpha=0.97, shadow=("#ff2bd6", 0.95, 2.5, 0),
        mark=("bar", "#ff4fd8", 1.0), small=("disc", "#ff4fd8", 0.28),
    ),
    "automata": dict(
        glyph="#4b473c", shade=("#d4cfba", 0.45), alpha=0.95, shadow=None,
        mark=("brackets", "#4b473c", 0.90), small=("box", "#4b473c", 0.14),
    ),
    "magikarp": dict(
        glyph="#fffaf0", shade=("#0b3a66", 0.35), alpha=0.96, shadow=("#04213d", 0.55, 1.2, 1),
        mark=("bar", "#ffcf4a", 0.95), small=("disc", "#ffffff", 0.22),
    ),
}


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(hex_rgb(a), hex_rgb(b)))


def rgba(color, alpha):
    return (*hex_rgb(color), round(255 * alpha))


def entries():
    """The menuentry stanzas in entries.conf, as dicts."""
    out = []
    for m in re.finditer(r'^menuentry\s+"([^"]+)"\s*\{(.*?)^\}', (ROOT / "entries.conf").read_text(), re.S | re.M):
        fields = dict(re.findall(r"^\s*(\w+)\s+(\S+)", m.group(2), re.M))
        out.append({"title": m.group(1), "icon": pathlib.PurePosixPath(fields["icon"]).stem,
                    "loader": fields.get("loader"), "volume": fields.get("volume", "rEFInd's own ESP")})
    return out


def load_config():
    cfg = json.loads((SRC / "config.json").read_text())
    problems = []
    for name, t in cfg["themes"].items():
        if name not in THEMES:
            problems.append(f"theme {name!r} has no palette in THEMES")
        if t["background"] not in BACKGROUNDS:
            problems.append(f"theme {name!r}: unknown background {t['background']!r}")
    for slot, cid in cfg["icons"].items():
        if not list((CANDIDATES / slot).glob(f"{cid}.*")):
            problems.append(f"icon {slot}: no candidate {cid!r}")
    rot = cfg["rotation"]
    if rot["mode"] not in ("off", "next", "random"):
        problems.append(f"rotation mode must be off, next or random, not {rot['mode']!r}")
    if not set(rot["themes"]) <= set(cfg["themes"]) or not rot["themes"]:
        problems.append("rotation themes must be a non-empty subset of themes")
    if cfg["theme"] not in cfg["themes"]:
        problems.append(f"theme {cfg['theme']!r} is not defined")
    if not isinstance(cfg["boot"]["timeout"], int) or not -1 <= cfg["boot"]["timeout"] <= 120:
        problems.append("boot timeout must be an integer from -1 to 120")
    if cfg["boot"]["default"] not in [e["title"] for e in entries()]:
        problems.append(f"boot default {cfg['boot']['default']!r} is not an entry in entries.conf")
    if problems:
        raise SystemExit("src/config.json: " + "; ".join(problems))
    return cfg


def render_svg(svg, size):
    png = subprocess.run(["rsvg-convert", "-a", "-w", str(size), "-h", str(size)],
                         input=svg.encode(), capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")


def glyph(path, spec, ss=512):
    """A candidate rendered large in the theme's colours, trimmed to its visible pixels."""
    if path.stem == "own":
        svg = path.read_text().replace("#ffffff", spec["glyph"]).replace("#999999", mix(spec["glyph"], *spec["shade"]))
        im = render_svg(svg, ss)
    else:
        src = render_svg(path.read_text(), ss) if path.suffix == ".svg" else Image.open(path).convert("RGBA")
        a = src.getchannel("A")
        peak = a.getextrema()[1] or 255   # upstream PNGs are pre-faded; restore full opacity
        im = Image.new("RGBA", src.size, rgba(spec["glyph"], 1))
        im.putalpha(a.point(lambda v: min(255, round(v * 255 / peak))))
    return im.crop(im.getchannel("A").getbbox())


def icon(path, size, spec):
    g = glyph(path, spec)
    box = size * FILL["os" if path.parent.name.startswith("os_") else "func"]
    scale = box / max(g.size)
    g = g.resize((max(1, round(g.width * scale)), max(1, round(g.height * scale))), Image.LANCZOS)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    im.paste(g, ((size - g.width) // 2, (size - g.height) // 2))
    im.putalpha(im.getchannel("A").point(lambda v: round(v * spec["alpha"])))
    if spec["shadow"]:
        colour, strength, blur, drop = spec["shadow"]
        k = size / 48
        shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
        mask = im.getchannel("A").filter(ImageFilter.GaussianBlur(blur * k)).point(lambda v: min(255, round(v * strength)))
        shadow.paste(rgba(colour, 1), (0, round(drop * k)), mask)
        im = Image.alpha_composite(shadow, im)
    return im


def selection(size, mark, color, alpha, ss=4):
    S = size * ss
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fill = rgba(color, alpha)
    c = S / 2
    if mark == "caret":
        w, h, y = 18 * ss, 10 * ss, S - 3 * ss
        d.polygon([(c - w / 2, y), (c + w / 2, y), (c, y - h)], fill=fill)
    elif mark == "bar":
        w, h, y = 60 * ss, 4 * ss, S - 4 * ss
        d.rounded_rectangle([c - w / 2, y - h, c + w / 2, y], radius=h / 2, fill=fill)
    elif mark == "diamond":
        r, y = 7 * ss, S - 10 * ss
        d.polygon([(c, y - r), (c + r, y), (c, y + r), (c - r, y)], fill=fill)
    elif mark == "brackets":
        m, L, w = 3 * ss, 20 * ss, 3 * ss          # margin, arm length, line width
        near, far = (m, m + L), (S - m - L, S - m)
        thin_near, thin_far = (m, m + w), (S - m - w, S - m)
        for xs in (near, far):                    # horizontal arms
            for ys in (thin_near, thin_far):
                d.rectangle([xs[0], ys[0], xs[1], ys[1]], fill=fill)
        for xs in (thin_near, thin_far):          # vertical arms
            for ys in (near, far):
                d.rectangle([xs[0], ys[0], xs[1], ys[1]], fill=fill)
    elif mark == "disc":
        r = c - ss
        d.ellipse([c - r, c - r, c + r, c + r], fill=fill)
    elif mark == "box":
        d.rectangle([2 * ss, 2 * ss, S - 2 * ss, S - 2 * ss], fill=fill)
    return im.resize((size, size), Image.LANCZOS)


def background(src):
    im = Image.open(src).convert("RGB")
    scale = max(SCREEN[0] / im.width, SCREEN[1] / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    left, top = (im.width - SCREEN[0]) // 2, (im.height - SCREEN[1]) // 2
    return im.crop((left, top, left + SCREEN[0], top + SCREEN[1]))


def text_colour(im):
    # rEFInd takes its menu background colour from the banner's top-left pixel and
    # uses white text on a dark one, black on a light one.
    r, g, b = im.convert("RGB").getpixel((0, 0))
    return "white" if (r * 299 + g * 587 + b * 114) / 1000 < 128 else "black"


def font():
    # rEFInd fonts: one row of 96 equal-width cells (ASCII 32-126 plus a fallback glyph),
    # black on transparent. rEFInd switches to white text itself on dark backgrounds.
    f = ImageFont.truetype(FONT_FILE, FONT_PX)
    ascent, descent = f.getmetrics()
    w, h = round(f.getlength("M")), ascent + descent
    im = Image.new("RGBA", (w * 96, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, ch in enumerate([chr(c) for c in range(32, 127)] + ["?"]):
        d.text((i * w, 0), ch, font=f, fill=(0, 0, 0, 255))
    return im


def save(im, path, **kw):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True, **kw)


def candidate_path(slot, cid):
    return next((CANDIDATES / slot).glob(f"{cid}.*"))


THEME_CONF = """\
# {name}: generated by src/build.py from src/config.json; do not edit.
# Paths are relative to the rEFInd directory on the ESP (/boot/EFI/refind).

banner          themes/{name}/background.png
banner_scale    fillscreen
icons_dir       themes/{name}/icons
selection_big   themes/{name}/selection_big.png
selection_small themes/{name}/selection_small.png
font            themes/{name}/font.png
"""


def build_theme(name, spec, cfg):
    out = ROOT / "themes" / name
    (out).mkdir(parents=True, exist_ok=True)
    (out / "theme.conf").write_text(THEME_CONF.format(name=name))
    for slot, cid in cfg["icons"].items():
        size = BIG if slot.startswith("os_") else SMALL
        save(icon(candidate_path(slot, cid), size, spec), out / "icons" / f"{slot}.png")
    save(selection(BIG_TILE, *spec["mark"]), out / "selection_big.png")
    save(selection(SMALL_TILE, *spec["small"]), out / "selection_small.png")
    save(background(BACKGROUNDS[cfg["themes"][name]["background"]]), out / "background.png")
    save(font(), out / "font.png")
    # Every candidate in this palette, for the icon lab. Skipped when nothing changed.
    lab = PREVIEW / "candidates" / name
    sig = hashlib.sha256(json.dumps([spec, FILL, BIG, SMALL]).encode()).hexdigest()
    stale = not (lab / ".palette").exists() or (lab / ".palette").read_text() != sig
    for path in sorted(CANDIDATES.glob("*/*.*")):
        if path.suffix not in (".svg", ".png"):
            continue
        dest = lab / path.parent.name / f"{path.stem}.png"
        if stale or not dest.exists() or dest.stat().st_mtime < path.stat().st_mtime:
            size = BIG if path.parent.name.startswith("os_") else SMALL
            save(icon(path, size, spec), dest)
    (lab / ".palette").write_text(sig)
    print(f"built themes/{name}")


def build_refind_conf(cfg):
    text = (SRC / "refind.conf.in").read_text()
    text = text.replace("@TIMEOUT@", str(cfg["boot"]["timeout"])).replace("@DEFAULT@", cfg["boot"]["default"])
    (ROOT / "refind.conf").write_text(text)


def build_backgrounds():
    """Full-size JPEGs of every background, so the configurator can show any pairing."""
    for stale in (PREVIEW / "backgrounds").glob("*.jpg"):
        if stale.stem not in BACKGROUNDS:
            stale.unlink()
    info = {}
    for bid, path in BACKGROUNDS.items():
        dest = PREVIEW / "backgrounds" / f"{bid}.jpg"
        if not dest.exists() or dest.stat().st_mtime < path.stat().st_mtime:
            save(background(path), dest, quality=85)
        info[bid] = {"text": text_colour(Image.open(dest))}
    return info


def preview_jpg(name):
    """Approximate rEFInd's main screen as a JPEG, for the README."""
    t = ROOT / "themes" / name
    screen = Image.open(t / "background.png").convert("RGBA")
    W, H = screen.size
    big = [e["icon"] for e in entries()]
    small = ["func_shutdown", "func_reset", "func_firmware"]
    row_big = len(big) * BIG_TILE + (len(big) - 1) * 8
    row_small = len(small) * SMALL_TILE + (len(small) - 1) * 8
    y_big = (H - (BIG_TILE + 16 + SMALL_TILE)) // 2
    y_small = y_big + BIG_TILE + 16
    sel_big = Image.open(t / "selection_big.png")
    for i, n in enumerate(big):
        x = (W - row_big) // 2 + i * (BIG_TILE + 8)
        if i == 0:
            screen.alpha_composite(sel_big, (x, y_big))
        screen.alpha_composite(Image.open(t / "icons" / f"{n}.png"), (x + (BIG_TILE - BIG) // 2, y_big + (BIG_TILE - BIG) // 2))
    for i, n in enumerate(small):
        x = (W - row_small) // 2 + i * (SMALL_TILE + 8)
        screen.alpha_composite(Image.open(t / "icons" / f"{n}.png"), (x + (SMALL_TILE - SMALL) // 2, y_small + (SMALL_TILE - SMALL) // 2))
    glyphs = Image.open(t / "font.png")
    cw, ch = glyphs.width // 96, glyphs.height
    label = entries()[0]["title"]
    y_text = y_small + SMALL_TILE + 24
    x_text = (W - cw * len(label)) // 2
    colour = (255, 255, 255) if text_colour(screen) == "white" else (0, 0, 0)
    for i, c in enumerate(label):
        g = glyphs.crop(((ord(c) - 32) * cw, 0, (ord(c) - 31) * cw, ch))
        tinted = Image.new("RGBA", g.size, colour + (0,))
        tinted.putalpha(g.getchannel("A"))
        screen.alpha_composite(tinted, (x_text + i * cw, y_text))
    save(screen.convert("RGB"), ROOT / "docs" / f"preview-{name}.jpg", quality=88)
    print(f"wrote docs/preview-{name}.jpg")


def browser_data(cfg, backgrounds):
    glyphs = Image.open(ROOT / "themes" / next(iter(cfg["themes"])) / "font.png")
    candidates = {slot: sorted(p.stem for p in (CANDIDATES / slot).glob("*.*") if p.suffix in (".svg", ".png"))
                  for slot in cfg["icons"]}
    data = {"screen": SCREEN, "big": BIG, "small": SMALL, "bigTile": BIG_TILE, "smallTile": SMALL_TILE,
            "cell": [glyphs.width // 96, glyphs.height], "entries": entries(), "config": cfg,
            "backgrounds": backgrounds, "candidates": candidates}
    (PREVIEW / "data.js").write_text("// Generated by src/build.py; do not edit.\nwindow.REFIND = "
                                     + json.dumps(data, indent=2) + ";\n")
    print("wrote preview/data.js")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--preview", action="store_true", help="also write docs/preview-<theme>.jpg")
    args = ap.parse_args()
    cfg = load_config()
    build_refind_conf(cfg)
    for name in cfg["themes"]:
        build_theme(name, THEMES[name], cfg)
        if args.preview:
            preview_jpg(name)
    browser_data(cfg, build_backgrounds())
