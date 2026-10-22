#!/usr/bin/env python3
"""Render every theme's PNGs from src/: icons, selection marks, label font and background.

    python3 src/build.py            # rebuild themes/*/ PNGs
    python3 src/build.py --preview  # also write docs/preview-<theme>.jpg mock-ups

Always writes preview/data.js too, for the in-browser simulator (preview/index.html).

Needs rsvg-convert (librsvg) and Pillow. The output is committed, so deploying
never needs these tools. Theme look is defined in THEMES below; theme.conf files
are hand-written and not touched by this script.
"""
import argparse
import io
import json
import pathlib
import re
import subprocess

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "src" / "candidates"
UPSTREAM = ROOT / "upstream"

SCREEN = (1920, 1080)                       # magikarp's display; backgrounds are cut to this exactly
BIG, SMALL = 128, 48                        # must match big_icon_size / small_icon_size in refind.conf
BIG_TILE, SMALL_TILE = BIG * 9 // 8, SMALL * 4 // 3   # rEFInd's tile sizes for those icon sizes
FONT_FILE = "/usr/share/fonts/Adwaita/AdwaitaMono-Regular.ttf"
FONT_PX = 22

# Which candidate (src/candidates/<slot>/<id>.*) each icon slot uses. Pick them
# in the icon lab (preview/index.html), which prints this dict for you.
CHOICES = {
    "os_cachyos": "own",
    "os_win": "ambience-os_win",
    "os_mint": "own",
    "func_shutdown": "own",
    "func_reset": "own",
    "func_firmware": "own",
}
# How much of the icon square a glyph's bounding box fills, so every candidate
# comes out the same visual size whatever padding its source had.
FILL = {"os": 0.74, "func": 0.80}

# Our own SVGs (candidate id "own") use #ffffff for the main colour and #999999
# for the shade colour; both are swapped for each theme's palette. Every other
# candidate is single-tone and is recoloured from its alpha channel.
THEMES = {
    "minimal": dict(
        background=UPSTREAM / "rEFInd-minimal" / "background.png",
        glyph="#0e0f10", shade=("#ffffff", 0.45), alpha=0.94, shadow=0.0,
        mark="caret", mark_color=("#0e0f10", 0.85), disc=("#0e0f10", 0.10),
    ),
    "ambience": dict(
        background=UPSTREAM / "refind-ambience" / "background.png",
        glyph="#ffffff", shade=("#000000", 0.25), alpha=0.95, shadow=0.25,
        mark="bar", mark_color=("#ffffff", 0.95), disc=("#ffffff", 0.20),
    ),
    "sublime": dict(
        background=UPSTREAM / "refind-sublime" / "background.png",
        glyph="#f5f1e6", shade=("#000000", 0.28), alpha=0.92, shadow=0.45,
        mark="diamond", mark_color=("#f5f1e6", 0.90), disc=("#ffffff", 0.20),
    ),
}


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(hex_rgb(a), hex_rgb(b)))


def rgba(color, alpha):
    return (*hex_rgb(color), round(255 * alpha))


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
        blur = max(1.0, size / 48)
        shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
        mask = im.getchannel("A").filter(ImageFilter.GaussianBlur(blur)).point(lambda v: round(v * spec["shadow"]))
        shadow.paste((0, 0, 0, 255), (0, max(1, size // 64)), mask)
        im = Image.alpha_composite(shadow, im)
    return im


def selection(size, mark, color, ss=4):
    S = size * ss
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fill = rgba(*color)
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
    elif mark == "disc":
        r = c - ss
        d.ellipse([c - r, c - r, c + r, c + r], fill=fill)
    return im.resize((size, size), Image.LANCZOS)


def background(src):
    im = Image.open(src).convert("RGB")
    scale = max(SCREEN[0] / im.width, SCREEN[1] / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    left, top = (im.width - SCREEN[0]) // 2, (im.height - SCREEN[1]) // 2
    return im.crop((left, top, left + SCREEN[0], top + SCREEN[1]))


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


def save(im, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)


def candidate_path(slot, cid):
    hits = list((CANDIDATES / slot).glob(f"{cid}.*"))
    if not hits:
        raise SystemExit(f"no candidate {cid!r} for {slot}; run src/tools/fetch_candidates.py")
    return hits[0]


def build(name, spec):
    out = ROOT / "themes" / name
    for slot, cid in CHOICES.items():
        size = BIG if slot.startswith("os_") else SMALL
        save(icon(candidate_path(slot, cid), size, spec), out / "icons" / f"{slot}.png")
    # Every candidate too, for the icon lab.
    for path in sorted(CANDIDATES.glob("*/*.*")):
        if path.suffix in (".svg", ".png"):
            size = BIG if path.parent.name.startswith("os_") else SMALL
            save(icon(path, size, spec), ROOT / "preview" / "candidates" / name / path.parent.name / f"{path.stem}.png")
    save(selection(BIG_TILE, spec["mark"], spec["mark_color"]), out / "selection_big.png")
    save(selection(SMALL_TILE, "disc", spec["disc"]), out / "selection_small.png")
    save(background(spec["background"]), out / "background.png")
    save(font(), out / "font.png")
    print(f"built themes/{name}")


def preview(name):
    """Approximate rEFInd's main screen, so themes can be compared without rebooting."""
    t = ROOT / "themes" / name
    screen = Image.open(t / "background.png").convert("RGBA")
    W, H = screen.size
    big = ["os_cachyos", "os_win", "os_mint"]
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
    # Label in the theme's bitmap font. rEFInd takes its menu background colour from the
    # banner's top-left pixel and uses white text if that is dark, black if light.
    glyphs = Image.open(t / "font.png")
    cw, ch = glyphs.width // 96, glyphs.height
    label = "CachyOS"
    y_text = y_small + SMALL_TILE + 24
    x_text = (W - cw * len(label)) // 2
    colour = (255, 255, 255) if text_colour(name) == "white" else (0, 0, 0)
    for i, c in enumerate(label):
        g = glyphs.crop(((ord(c) - 32) * cw, 0, (ord(c) - 31) * cw, ch))
        tinted = Image.new("RGBA", g.size, colour + (0,))
        tinted.putalpha(g.getchannel("A"))
        screen.alpha_composite(tinted, (x_text + i * cw, y_text))
    out = ROOT / "docs" / f"preview-{name}.jpg"
    out.parent.mkdir(exist_ok=True)
    screen.convert("RGB").save(out, quality=88)
    print(f"wrote docs/{out.name}")


def text_colour(name):
    r, g, b = Image.open(ROOT / "themes" / name / "background.png").convert("RGB").getpixel((0, 0))
    return "white" if (r * 299 + g * 587 + b * 114) / 1000 < 128 else "black"


def browser_data():
    """Write preview/data.js for the in-browser simulator (preview/index.html)."""
    entries = []
    for m in re.finditer(r'^menuentry\s+"([^"]+)"\s*\{(.*?)^\}', (ROOT / "entries.conf").read_text(), re.S | re.M):
        fields = dict(re.findall(r"^\s*(\w+)\s+(\S+)", m.group(2), re.M))
        entries.append({"title": m.group(1), "icon": pathlib.PurePosixPath(fields["icon"]).stem,
                        "loader": fields.get("loader"), "volume": fields.get("volume", "rEFInd's own ESP")})
    themes = {}
    for name in sorted(p.name for p in (ROOT / "themes").iterdir() if (p / "theme.conf").exists()):
        glyphs = Image.open(ROOT / "themes" / name / "font.png")
        themes[name] = {"text": text_colour(name), "cell": [glyphs.width // 96, glyphs.height]}
    candidates = {slot: sorted(p.stem for p in (CANDIDATES / slot).glob("*.*") if p.suffix in (".svg", ".png"))
                  for slot in CHOICES}
    data = {"screen": SCREEN, "big": BIG, "small": SMALL, "bigTile": BIG_TILE, "smallTile": SMALL_TILE,
            "entries": entries, "themes": themes, "choices": CHOICES, "candidates": candidates}
    out = ROOT / "preview" / "data.js"
    out.write_text("// Generated by src/build.py; do not edit.\nwindow.REFIND = " + json.dumps(data, indent=2) + ";\n")
    print("wrote preview/data.js")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--preview", action="store_true", help="also write docs/preview-<theme>.jpg")
    ap.add_argument("themes", nargs="*", default=list(THEMES), help="themes to build (default: all)")
    args = ap.parse_args()
    for name in args.themes:
        build(name, THEMES[name])
        if args.preview:
            preview(name)
    browser_data()
