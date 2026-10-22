#!/usr/bin/env python3
"""Generate the procedural backgrounds in src/backgrounds/.

    python3 src/tools/gen_backgrounds.py [synthwave] [automata]

Both are composed around rEFInd's menu, which sits in the middle of the screen
(icons around y=430-650 at 1080p): the busy parts stay above and below it.
Drawn at 2x and downsampled for clean anti-aliasing. Deterministic (seeded).
"""
import math
import pathlib
import random
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

OUT = pathlib.Path(__file__).resolve().parents[1] / "backgrounds"
W, H = 1920, 1080
SS = 2


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def vgradient(size, stops):
    """Vertical gradient through (position, rgb) stops."""
    w, h = size
    col = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / (h - 1)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                col.putpixel((0, y), lerp(c0, c1, (t - p0) / (p1 - p0 or 1)))
                break
    return col.resize((w, h))


def glow(layer, radius, strength=1.0):
    """Additive bloom: the layer plus a blurred copy of itself."""
    blurred = layer.filter(ImageFilter.GaussianBlur(radius))
    if strength != 1.0:
        blurred = blurred.point(lambda v: min(255, round(v * strength)))
    return ImageChops.add(layer, blurred)


def synthwave():
    w, h = W * SS, H * SS
    horizon = round(h * 0.72)
    img = vgradient((w, h), [(0, (8, 2, 30)), (0.45, (38, 8, 72)), (0.72, (120, 22, 100)), (1, (120, 22, 100))])

    # Stars, thinning out towards the horizon.
    rnd = random.Random(7)
    d = ImageDraw.Draw(img)
    for _ in range(900):
        x, y = rnd.randrange(w), int(rnd.random() ** 1.8 * horizon * 0.85)
        b = rnd.randint(90, 230)
        r = rnd.choice([1, 1, 1, 2, 2, 3])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(b, b, min(255, b + 25)))

    # Sun above the menu: yellow to hot pink, with slats cut out of its lower half.
    cx, cy, r = w // 2, round(h * 0.215), round(h * 0.17)
    sun = vgradient((2 * r, 2 * r), [(0, (255, 226, 92)), (0.55, (255, 120, 90)), (1, (255, 40, 140))])
    mask = Image.new("L", (2 * r, 2 * r), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=255)
    y, gap = r * 1.0, 4 * SS
    while y < 2 * r:
        md.rectangle([0, y, 2 * r, y + gap], fill=0)
        y += gap * 2.6 + (2 * r - y) * 0.06
        gap += 1.1 * SS
    sun_layer = Image.new("RGB", (w, h))
    sun_layer.paste(sun, (cx - r, cy - r), mask)
    img = ImageChops.add(img, sun_layer.filter(ImageFilter.GaussianBlur(60 * SS)).point(lambda v: round(v * 0.55)))
    img.paste(sun, (cx - r, cy - r), mask)

    # Mountains on both flanks, leaving the middle open.
    rnd = random.Random(3)
    mountains = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mountains)
    for side in (-1, 1):
        pts, x = [], w // 2 + side * round(w * 0.16)
        pts.append((x, horizon))
        while 0 <= x <= w:
            x += side * rnd.randint(60, 160) * SS
            pts.append((x, horizon - rnd.randint(20, 150) * SS * (abs(x - w / 2) / (w / 2)) ** 0.7))
        pts.append((x, horizon))
        md.polygon(pts, fill=255)
    img.paste((24, 6, 46), (0, 0), mountains)
    rim = mountains.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 40 else 0)
    rim_layer = Image.new("RGB", (w, h))
    rim_layer.paste((255, 70, 200), (0, 0), rim)
    img = ImageChops.add(img, glow(rim_layer, 6 * SS, 1.4))

    # Floor and perspective grid converging on the vanishing point.
    floor = vgradient((w, h - horizon), [(0, (40, 4, 60)), (1, (6, 0, 16))])
    img.paste(floor, (0, horizon))
    grid = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(grid)
    pink, lw = (255, 46, 200), 2 * SS
    for i in range(1, 40):
        t = (i / 18) ** 2.2
        y = horizon + round(t * (h - horizon) * 1.0)
        if y > h:
            break
        gd.line([(0, y), (w, y)], fill=pink, width=lw)
    for i in range(-30, 31):
        x_bottom = w / 2 + i * w * 0.075
        gd.line([(w / 2 + i * 12 * SS, horizon), (x_bottom, h)], fill=pink, width=lw)
    img = ImageChops.add(img, glow(grid, 5 * SS, 1.3))

    # Cyan horizon line.
    line = Image.new("RGB", (w, h))
    ImageDraw.Draw(line).line([(0, horizon), (w, horizon)], fill=(0, 230, 255), width=3 * SS)
    img = ImageChops.add(img, glow(line, 12 * SS, 1.6))
    return img.resize((W, H), Image.LANCZOS)


def automata():
    """A beige machine-interface screen: dot grid, hairlines, brackets, readouts."""
    w, h = W * SS, H * SS
    paper, ink, faint = (212, 207, 186), (75, 71, 60), (190, 184, 160)
    img = vgradient((w, h), [(0, (218, 214, 194)), (0.5, paper), (1, (200, 195, 172))])
    d = ImageDraw.Draw(img)

    # Dot grid and very faint scanlines.
    step = 28 * SS
    for y in range(step, h, step):
        for x in range(step, w, step):
            d.ellipse([x - SS, y - SS, x + SS, y + SS], fill=faint)
    for y in range(0, h, 4 * SS):
        d.line([(0, y), (w, y)], fill=(208, 203, 182), width=1)

    # Header and footer rules with tick marks and square bullets.
    m = 72 * SS
    for y in (m, h - m):
        d.line([(m, y), (w - m, y)], fill=ink, width=2 * SS)
        for x in range(m, w - m + 1, 48 * SS):
            d.line([(x, y - 6 * SS), (x, y)], fill=ink, width=SS)
    for x in (m, w - m - 14 * SS):
        d.rectangle([x, m - 26 * SS, x + 14 * SS, m - 12 * SS], fill=ink)

    # Corner brackets framing the screen.
    b, L = 40 * SS, 56 * SS
    for (x, y, sx, sy) in [(b, b, 1, 1), (w - b, b, -1, 1), (b, h - b, 1, -1), (w - b, h - b, -1, -1)]:
        d.line([(x, y), (x + sx * L, y)], fill=ink, width=3 * SS)
        d.line([(x, y), (x, y + sy * L)], fill=ink, width=3 * SS)

    # Faint concentric rings and a crosshair, off to the right, behind nothing.
    cx, cy = round(w * 0.80), round(h * 0.30)
    for rr in (90, 150, 230, 330):
        rr *= SS
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=faint, width=SS * 2)
    d.line([(cx - 360 * SS, cy), (cx + 360 * SS, cy)], fill=faint, width=SS)
    d.line([(cx, cy - 360 * SS), (cx, cy + 360 * SS)], fill=faint, width=SS)

    # Readouts: a status column on the left, bars on the right.
    try:
        font = ImageFont.truetype("/usr/share/fonts/Adwaita/AdwaitaMono-Regular.ttf", 15 * SS)
    except OSError:
        font = ImageFont.load_default()
    labels = ["BOOT SEQUENCE", "FIRMWARE ........ OK", "STORAGE ......... OK",
              "MEMORY .......... OK", "SELECT SYSTEM"]
    for i, text in enumerate(labels):
        y = m + 40 * SS + i * 30 * SS
        d.rectangle([m, y + 6 * SS, m + 8 * SS, y + 14 * SS], fill=ink)
        d.text((m + 20 * SS, y), text, font=font, fill=ink)
    rnd = random.Random(11)
    for i in range(6):
        y = h - m - 40 * SS - i * 26 * SS
        x1 = w - m
        d.rectangle([x1 - 260 * SS, y, x1, y + 10 * SS], outline=ink, width=SS)
        d.rectangle([x1 - 260 * SS, y, x1 - 260 * SS + rnd.randint(40, 250) * SS, y + 10 * SS], fill=ink)
    d.text((m + 48 * SS, h - m + 18 * SS), "SYS.BOOT // MANAGER", font=font, fill=ink)
    d.text((w - m - 200 * SS, h - m + 18 * SS), "v0.14 // READY", font=font, fill=ink)

    # A little film grain so the beige doesn't band.
    noise = Image.effect_noise((w // 4, h // 4), 18).resize((w, h)).convert("RGB")
    img = Image.blend(img, ImageChops.multiply(img, ImageChops.invert(noise).point(lambda v: 255 - (255 - v) // 12)), 1.0)
    return img.resize((W, H), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[1:] or ["synthwave", "automata"]:
        globals()[name]().save(OUT / f"{name}.png", optimize=True)
        print(f"wrote src/backgrounds/{name}.png")
