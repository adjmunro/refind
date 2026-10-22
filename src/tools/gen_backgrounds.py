#!/usr/bin/env python3
"""Generate the procedural backgrounds in src/backgrounds/.

    python3 src/tools/gen_backgrounds.py [name ...]     (default: all in BACKGROUND_NAMES)

All are composed around rEFInd's menu, which sits in the middle of the screen
(icons around x=730-1190, y=430-700 at 1080p): the busy parts stay clear of it.
Drawn at 2x and downsampled for clean anti-aliasing. Deterministic (seeded).
Needs Pillow, and rsvg-convert for the fish.
"""
import io
import math
import pathlib
import random
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from magikarp import carp

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


# A big orange carp with a crown fin, whiskers, a gaping mouth and an empty
# stare, facing left. Fan art for this machine's namesake; drawn on a 600x520 box.
FISH_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="600" height="520" viewBox="0 0 600 520">
<defs>
  <radialGradient id="body" cx="0.42" cy="0.32" r="0.75">
    <stop offset="0" stop-color="#ff9a52"/><stop offset="0.55" stop-color="#f2592b"/><stop offset="1" stop-color="#c63a1a"/>
  </radialGradient>
  <linearGradient id="fin" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#fff4c2"/><stop offset="1" stop-color="#f0d27a"/>
  </linearGradient>
  <clipPath id="clip"><ellipse cx="315" cy="265" rx="215" ry="168"/></clipPath>
</defs>
<g stroke="#6e1c0c" stroke-width="5" stroke-linejoin="round" stroke-linecap="round">
  <!-- tail -->
  <path d="M505 215 L592 128 L560 238 L596 262 L560 290 L592 400 L505 318 Z" fill="url(#fin)"/>
  <path d="M520 230 L568 180 M522 300 L568 352" fill="none" stroke="#d9b45a" stroke-width="4"/>
  <!-- crown dorsal fin -->
  <path d="M205 132 L232 38 L272 112 L318 22 L352 106 L398 40 L410 136 Z" fill="url(#fin)"/>
  <!-- far pectoral fin -->
  <path d="M352 388 L330 470 L392 446 L420 470 L404 386 Z" fill="url(#fin)"/>
  <!-- body -->
  <ellipse cx="315" cy="265" rx="215" ry="168" fill="url(#body)"/>
</g>
<!-- scales: rows of crescents, clipped to the body -->
<g clip-path="url(#clip)" fill="none" stroke="#b53216" stroke-width="4.5" stroke-linecap="round">
  SCALES
</g>
<!-- pale belly -->
<path clip-path="url(#clip)" d="M110 330 Q300 470 530 330 L530 440 L110 440 Z" fill="#ffd9a8" opacity="0.55"/>
<g stroke="#6e1c0c" stroke-width="5" stroke-linejoin="round" stroke-linecap="round">
  <!-- outline again on top of the scales -->
  <ellipse cx="315" cy="265" rx="215" ry="168" fill="none"/>
  <!-- gill -->
  <path d="M262 150 Q300 265 258 382" fill="none" stroke="#a52d12" stroke-width="7"/>
  <!-- near pectoral fin -->
  <path d="M262 318 L232 420 L296 392 L330 418 L318 322 Z" fill="url(#fin)"/>
  <path d="M270 340 L252 398 M296 340 L298 392" fill="none" stroke="#d9b45a" stroke-width="4"/>
  <!-- whiskers -->
  <path d="M142 214 C90 168 58 118 82 58" fill="none" stroke="#6e1c0c" stroke-width="22"/>
  <path d="M142 214 C90 168 58 118 82 58" fill="none" stroke="#f6dc84" stroke-width="13"/>
  <path d="M150 336 C108 384 94 424 120 474" fill="none" stroke="#6e1c0c" stroke-width="22"/>
  <path d="M150 336 C108 384 94 424 120 474" fill="none" stroke="#f6dc84" stroke-width="13"/>
  <!-- mouth -->
  <ellipse cx="118" cy="276" rx="48" ry="58" fill="#ffdcbc"/>
  <ellipse cx="114" cy="278" rx="26" ry="36" fill="#7d1a0e"/>
  <!-- eye -->
  <circle cx="218" cy="205" r="46" fill="#ffffff"/>
  <circle cx="210" cy="208" r="10" fill="#1a0b06" stroke="none"/>
</g>
</svg>"""


def fish(width):
    rows = []
    for j, y in enumerate(range(130, 440, 34)):
        for x in range(290 + (j % 2) * 22, 560, 44):
            rows.append(f'<path d="M{x - 20} {y} A22 22 0 0 0 {x + 20} {y}"/>')
    svg = FISH_SVG.replace("SCALES", "\n  ".join(rows))
    png = subprocess.run(["rsvg-convert", "-w", str(width)], input=svg.encode(), capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")


def magikarp():
    """Underwater: light from the surface, a carp to the right of the menu, bubbles, a sandy floor."""
    w, h = W * SS, H * SS
    # The top edge stays dark enough that rEFInd (which reads the top-left pixel) uses white text.
    img = vgradient((w, h), [(0, (38, 136, 200)), (0.12, (30, 120, 186)), (0.5, (16, 84, 140)),
                             (0.85, (9, 50, 92)), (1, (6, 34, 64))])

    # Light shafts fanning down from the surface.
    rays = Image.new("L", (w, h), 0)
    rd = ImageDraw.Draw(rays)
    rnd = random.Random(5)
    for _ in range(9):
        x = rnd.uniform(-0.1, 1.0) * w
        spread, lean = rnd.uniform(40, 110) * SS, rnd.uniform(120, 420) * SS
        rd.polygon([(x, 0), (x + spread, 0), (x + spread * 3 + lean, h * 0.9), (x + lean, h * 0.9)], fill=rnd.randint(18, 40))
    rays = rays.filter(ImageFilter.GaussianBlur(28 * SS))
    img = Image.composite(Image.new("RGB", (w, h), (190, 235, 255)), img, rays)

    # Shimmering surface just below the top edge.
    surf = Image.new("RGB", (w, h))
    sd = ImageDraw.Draw(surf)
    for k, (amp, y0, col) in enumerate([(10, 34, (180, 230, 255)), (7, 58, (120, 200, 245)), (5, 80, (90, 175, 230))]):
        pts = [(x, (y0 + amp * math.sin(x / (70 + 17 * k) / SS + k)) * SS) for x in range(0, w + 8, 8)]
        sd.line(pts, fill=col, width=3 * SS)
    img = ImageChops.add(img, glow(surf, 6 * SS, 0.8).point(lambda v: round(v * 0.6)))

    # Far-off fish silhouettes, left side, schooling.
    d = ImageDraw.Draw(img)
    rnd = random.Random(9)
    for _ in range(14):
        cx, cy, s = rnd.uniform(0.04, 0.30) * w, rnd.uniform(0.16, 0.42) * h, rnd.uniform(9, 17) * SS
        col = (18, 74, 124)
        d.ellipse([cx - s * 1.6, cy - s * 0.6, cx + s * 1.6, cy + s * 0.6], fill=col)
        d.polygon([(cx + s * 1.4, cy), (cx + s * 2.4, cy - s * 0.7), (cx + s * 2.4, cy + s * 0.7)], fill=col)

    # Sandy floor with dunes, rocks and swaying weed at the edges.
    floor = Image.new("L", (w, h), 0)
    pts = [(0, h)] + [(x, h * 0.86 + math.sin(x / (230 * SS)) * 22 * SS + math.sin(x / (97 * SS)) * 8 * SS)
                      for x in range(0, w + 16, 16)] + [(w, h)]
    ImageDraw.Draw(floor).polygon(pts, fill=255)
    sand = vgradient((w, h), [(0, (60, 110, 120)), (0.86, (64, 112, 118)), (1, (30, 62, 74))])
    img.paste(sand, (0, 0), floor)
    rnd = random.Random(2)
    for _ in range(12):
        x = rnd.choice([rnd.uniform(0, 0.28), rnd.uniform(0.72, 1.0)]) * w
        r = rnd.uniform(20, 55) * SS
        d.ellipse([x - r * 1.4, h * 0.9 - r, x + r * 1.4, h * 0.9 + r * 0.7], fill=(22, 52, 66))
    for _ in range(26):
        x0 = rnd.choice([rnd.uniform(0, 0.25), rnd.uniform(0.75, 1.0)]) * w
        height, phase = rnd.uniform(140, 330) * SS, rnd.uniform(0, 6)
        stem = [(x0 + math.sin(phase + t / 40) * 18 * SS * (t / height), h * 0.92 - t) for t in range(0, int(height), 6)]
        d.line(stem, fill=rnd.choice([(28, 110, 84), (36, 128, 92), (22, 92, 74)]), width=rnd.randint(7, 12) * SS, joint="curve")

    # The fish, right of the menu, tilted up a little as if gawping at the light.
    f = fish(560 * SS).rotate(-9, resample=Image.BICUBIC, expand=True)
    fx, fy = w - f.width - 40 * SS, round(h * 0.17)
    shadow = Image.new("RGBA", f.size, (4, 22, 44, 0))
    shadow.putalpha(f.getchannel("A").filter(ImageFilter.GaussianBlur(24 * SS)).point(lambda v: v // 2))
    img.paste(shadow, (fx + 18 * SS, fy + 30 * SS), shadow)
    img.paste(f, (fx, fy), f)

    # Bubbles rising from its mouth, plus a few strays.
    bub = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bub)
    rnd = random.Random(4)
    mouth_x, mouth_y = fx + 70 * SS, fy + 210 * SS
    spots = [(mouth_x - i * 6 * SS + math.sin(i) * 14 * SS, mouth_y - i * 46 * SS, 5 + i * 1.6) for i in range(1, 12)]
    spots += [(rnd.uniform(0.02, 0.98) * w, rnd.uniform(0.08, 0.85) * h, rnd.uniform(3, 8)) for _ in range(30)]
    for x, y, r in spots:
        if 0.36 * w < x < 0.64 * w and 0.36 * h < y < 0.70 * h:
            continue                                  # keep the menu clear
        r *= SS
        bd.ellipse([x - r, y - r, x + r, y + r], outline=(220, 245, 255, 170), width=max(2, round(r / 5)))
        bd.ellipse([x - r * 0.45, y - r * 0.55, x - r * 0.1, y - r * 0.2], fill=(255, 255, 255, 200))
    img.paste(bub, (0, 0), bub)
    return img.resize((W, H), Image.LANCZOS)


def caustics(size, seed, scale):
    """Bright wandering lines like sunlight focused through ripples: where two smooth
    noise fields cross. Returns an L image, 0 = dark, 255 = brightest line."""
    w, h = size
    small = (max(8, w // scale), max(8, h // scale))
    a = Image.effect_noise(small, 80).filter(ImageFilter.GaussianBlur(2))
    random.seed(seed)
    b = Image.effect_noise(small, 80).rotate(90, expand=True).resize(small).filter(ImageFilter.GaussianBlur(2))
    diff = ImageChops.difference(a, b).resize(size, Image.BICUBIC)
    return diff.point(lambda v: max(0, 255 - v * 9))


def deep_water(w, h):
    """The water from magikarp(), shared by the underwater variants."""
    img = vgradient((w, h), [(0, (38, 136, 200)), (0.12, (30, 120, 186)), (0.5, (16, 84, 140)),
                             (0.85, (9, 50, 92)), (1, (6, 34, 64))])
    rays = Image.new("L", (w, h), 0)
    rd = ImageDraw.Draw(rays)
    rnd = random.Random(5)
    for _ in range(9):
        x = rnd.uniform(-0.1, 1.0) * w
        spread, lean = rnd.uniform(40, 110) * SS, rnd.uniform(120, 420) * SS
        rd.polygon([(x, 0), (x + spread, 0), (x + spread * 3 + lean, h * 0.9), (x + lean, h * 0.9)], fill=rnd.randint(18, 40))
    rays = rays.filter(ImageFilter.GaussianBlur(28 * SS))
    img = Image.composite(Image.new("RGB", (w, h), (190, 235, 255)), img, rays)
    surf = Image.new("RGB", (w, h))
    sd = ImageDraw.Draw(surf)
    for k, (amp, y0, col) in enumerate([(10, 34, (180, 230, 255)), (7, 58, (120, 200, 245)), (5, 80, (90, 175, 230))]):
        pts = [(x, (y0 + amp * math.sin(x / (70 + 17 * k) / SS + k)) * SS) for x in range(0, w + 8, 8)]
        sd.line(pts, fill=col, width=3 * SS)
    return ImageChops.add(img, glow(surf, 6 * SS, 0.8).point(lambda v: round(v * 0.6)))


def place(img, fish, x, y, shadow=(4, 22, 44), blur=24):
    """Paste a fish with a soft shadow, x/y in output pixels."""
    sh = Image.new("RGBA", fish.size, shadow + (0,))
    sh.putalpha(fish.getchannel("A").filter(ImageFilter.GaussianBlur(blur * SS)).point(lambda v: v // 2))
    img.paste(sh, (x + 18 * SS, y + 30 * SS), sh)
    img.paste(fish, (x, y), fish)


def magikarp_deep():
    """The original water, a more faithful fish, and a soft, dim seabed instead of cartoon weed."""
    w, h = W * SS, H * SS
    img = deep_water(w, h)
    # Kelp far away on both flanks: tall blades, blurred by distance.
    kelp = Image.new("L", (w, h), 0)
    kd = ImageDraw.Draw(kelp)
    rnd = random.Random(21)
    for _ in range(30):
        x0 = rnd.choice([rnd.uniform(-0.02, 0.26), rnd.uniform(0.80, 1.02)]) * w
        tall, sway, width = rnd.uniform(0.35, 0.75) * h, rnd.uniform(20, 60) * SS, rnd.uniform(10, 26) * SS
        left = [(x0 + math.sin(t / tall * 3 + x0) * sway - width / 2 * (1 - t / tall), h - t) for t in range(0, int(tall), 10)]
        right = [(x + width * (1 - (h - y) / tall), y) for x, y in reversed(left)]
        kd.polygon(left + right, fill=rnd.randint(110, 200))
    kelp = kelp.filter(ImageFilter.GaussianBlur(9 * SS))
    img = Image.composite(Image.new("RGB", (w, h), (8, 52, 66)), img, kelp)
    # Sand: a soft gradient rising gently at the edges, with rippled light across it.
    floor = Image.new("L", (w, h), 0)
    pts = [(0, h)] + [(x, h * 0.84 + (1 - math.sin(math.pi * x / w)) * -50 * SS + math.sin(x / (310 * SS)) * 14 * SS)
                      for x in range(0, w + 16, 16)] + [(w, h)]
    ImageDraw.Draw(floor).polygon(pts, fill=255)
    floor = floor.filter(ImageFilter.GaussianBlur(14 * SS))
    sand = vgradient((w, h), [(0, (50, 98, 112)), (0.82, (58, 108, 116)), (1, (26, 54, 66))])
    img = Image.composite(sand, img, floor)
    light = caustics((w, h), 3, 90).point(lambda v: v // 3)
    img = Image.composite(Image.new("RGB", (w, h), (170, 225, 230)), img, ImageChops.multiply(light, floor))
    # Drifting specks.
    d = ImageDraw.Draw(img)
    rnd = random.Random(8)
    for _ in range(260):
        x, y, r = rnd.uniform(0, w), rnd.uniform(0.1, 0.95) * h, rnd.choice([1, 1, 2]) * SS
        if 0.36 * w < x < 0.64 * w and 0.36 * h < y < 0.70 * h:
            continue
        c = rnd.randint(130, 190)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(c, c + 30, c + 50))
    fish = carp(560 * SS, "natural", -6)
    place(img, fish, w - fish.width - 50 * SS, round(h * 0.18))
    return img.resize((W, H), Image.LANCZOS)


def magikarp_splash():
    """Sunset: Magikarp leaps clear of the sea, all splash and no purpose."""
    w, h = W * SS, H * SS
    sea_y = round(h * 0.38)
    img = vgradient((w, h), [(0, (70, 48, 120)), (0.2, (196, 86, 120)), (0.38, (255, 170, 96)),
                             (0.381, (34, 92, 112)), (0.6, (18, 64, 92)), (1, (6, 30, 52))])
    d = ImageDraw.Draw(img)
    # Sun sinking at the horizon, and its broken reflection.
    sx, sr = round(w * 0.22), round(h * 0.11)
    sun = Image.new("RGB", (w, h))
    ImageDraw.Draw(sun).ellipse([sx - sr, sea_y - sr, sx + sr, sea_y + sr], fill=(255, 214, 140))
    sun.paste((0, 0, 0), (0, sea_y, w, h))
    img = ImageChops.add(img, glow(sun, 40 * SS, 0.9))
    d = ImageDraw.Draw(img)
    rnd = random.Random(12)
    for i in range(36):
        y = sea_y + 6 * SS + i * 9 * SS
        half = sr * (1.1 - i / 40) * rnd.uniform(0.4, 1.0)
        x = sx + rnd.uniform(-0.3, 0.3) * sr
        d.line([(x - half, y), (x + half, y)], fill=(255, 196, 120), width=max(2, round((4 - i / 12) * SS)))
    # Gentle swell lines across the sea.
    for i in range(1, 16):
        y = sea_y + (i ** 1.6) * 6 * SS
        pts = [(x, y + math.sin(x / (90 * SS) + i) * 3 * SS) for x in range(0, w + 10, 10)]
        d.line(pts, fill=(60, 128, 146), width=SS * 2)
    # The leap: fish high on the right, splash crown where it left the water.
    fish = carp(320 * SS, "natural", -28)
    fx, fy = w - fish.width - 150 * SS, max(16 * SS, sea_y - fish.height + 10 * SS)
    cx = fx + round(fish.width * 0.80)
    splash = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    spd = ImageDraw.Draw(splash)
    for k in range(3):
        rx, ry = (120 + k * 80) * SS, (14 + k * 7) * SS
        spd.ellipse([cx - rx, sea_y - ry, cx + rx, sea_y + ry], outline=(220, 240, 245, 170 - k * 45), width=3 * SS)
    for _ in range(40):
        a = rnd.uniform(math.pi * 1.05, math.pi * 1.95)
        dist = rnd.uniform(30, 190) * SS
        x, y = cx + math.cos(a) * dist, sea_y + math.sin(a) * dist * 0.9
        r = rnd.uniform(3, 9) * SS
        spd.ellipse([x - r, y - r * 1.3, x + r, y + r * 1.3], fill=(235, 248, 250, 220))
    spd.polygon([(cx - 90 * SS, sea_y), (cx - 40 * SS, sea_y - 120 * SS), (cx, sea_y - 40 * SS), (cx + 30 * SS, sea_y - 150 * SS),
                 (cx + 70 * SS, sea_y - 50 * SS), (cx + 120 * SS, sea_y - 100 * SS), (cx + 110 * SS, sea_y)], fill=(230, 246, 250, 200))
    img.paste(splash, (0, 0), splash)
    img.paste(fish, (fx, fy), fish)
    return img.resize((W, H), Image.LANCZOS)


def magikarp_moon():
    """Night: a silhouette mid-leap across an enormous moon, over still water."""
    w, h = W * SS, H * SS
    sea_y = round(h * 0.80)
    img = vgradient((w, h), [(0, (6, 10, 30)), (0.6, (22, 30, 70)), (0.8, (40, 46, 96)),
                             (0.801, (10, 16, 38)), (1, (4, 6, 18))])
    d = ImageDraw.Draw(img)
    rnd = random.Random(31)
    for _ in range(700):
        x, y = rnd.uniform(0, w), rnd.uniform(0, sea_y * 0.95)
        b, r = rnd.randint(90, 230), rnd.choice([1, 1, 1, 2, 2, 3])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(b, b, min(255, b + 20)))
    mx, my, mr = round(w * 0.76), round(h * 0.40), round(h * 0.27)
    moon = Image.new("RGB", (w, h))
    md = ImageDraw.Draw(moon)
    md.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=(246, 238, 210))
    for _ in range(14):    # faint maria
        a, dist, r = rnd.uniform(0, 6.28), rnd.uniform(0, mr * 0.7), rnd.uniform(0.08, 0.22) * mr
        x, y = mx + math.cos(a) * dist, my + math.sin(a) * dist
        md.ellipse([x - r, y - r, x + r, y + r], fill=(226, 218, 192))
    moon = moon.filter(ImageFilter.GaussianBlur(2 * SS))
    halo = moon.filter(ImageFilter.GaussianBlur(70 * SS)).point(lambda v: round(v * 0.45))
    img = ImageChops.add(img, halo)
    d = ImageDraw.Draw(img)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=255)
    img.paste(moon, (0, 0), mask)
    # Moonlight on the water.
    for i in range(40):
        y = sea_y + 4 * SS + i * 5 * SS
        half = mr * 0.7 * (1 - i / 48) * rnd.uniform(0.3, 1.0)
        x = mx + rnd.uniform(-0.15, 0.15) * mr
        d.line([(x - half, y), (x + half, y)], fill=(200, 196, 170), width=SS * 2)
    fish = carp(520 * SS, "silhouette", -20)
    tinted = Image.new("RGBA", fish.size, (8, 12, 30, 0))
    tinted.putalpha(fish.getchannel("A"))
    img.paste(tinted, (mx - fish.width // 2 + 20 * SS, my - fish.height // 2 - 10 * SS), tinted)
    return img.resize((W, H), Image.LANCZOS)


def magikarp_ukiyo():
    """Woodblock print: indigo field, red sun, mist bands, seigaiha waves, a flat-coloured carp."""
    w, h = W * SS, H * SS
    indigo, deep, cream, red = (30, 44, 78), (20, 30, 58), (238, 226, 196), (196, 56, 44)
    img = Image.new("RGB", (w, h), indigo)
    d = ImageDraw.Draw(img)
    sx, sy, sr = round(w * 0.19), round(h * 0.26), round(h * 0.15)
    d.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=red)
    # Kasumi mist bands, kept off the menu in the middle.
    for x0, x1, y, t in [(0.0, 0.30, 0.32, 34), (0.08, 0.34, 0.40, 22), (0.55, 1.0, 0.10, 30), (0.70, 1.0, 0.16, 18)]:
        d.rounded_rectangle([x0 * w, y * h, x1 * w, y * h + t * SS], radius=t * SS // 2, fill=cream)
    # Seigaiha waves along the bottom: overlapping fans of concentric arcs, row by row.
    r = 74 * SS
    top = round(h * 0.76)
    for row, y in enumerate(range(top, h + r, r // 2)):
        for x in range(-r + (r if row % 2 else 0), w + r, 2 * r):
            for k, rr in enumerate([r, r * 0.76, r * 0.52, r * 0.28]):
                d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=deep if k % 2 == 0 else indigo, outline=cream, width=3 * SS)
    # The carp, leaping clear of the waves on the right.
    fish = carp(500 * SS, "flat", -22)
    img.paste(fish, (w - fish.width - 70 * SS, round(h * 0.20)), fish)
    # Paper grain over everything.
    grain = Image.effect_noise((w // 2, h // 2), 22).resize((w, h)).convert("RGB")
    img = Image.blend(img, ImageChops.multiply(img, grain.point(lambda v: 200 + v // 5)), 0.6)
    return img.resize((W, H), Image.LANCZOS)


BACKGROUND_NAMES = {
    "synthwave": synthwave, "automata": automata, "magikarp": magikarp,
    "magikarp-deep": magikarp_deep, "magikarp-splash": magikarp_splash,
    "magikarp-moon": magikarp_moon, "magikarp-ukiyo": magikarp_ukiyo,
}


if __name__ == "__main__":
    import json
    removed = set(json.loads((OUT.parent / "removed.json").read_text()).get("backgrounds", [])) \
        if (OUT.parent / "removed.json").exists() else set()
    OUT.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[1:] or [n for n in BACKGROUND_NAMES if n not in removed]:
        if name in removed:
            print(f"skipped {name}: deleted in the configurator (src/removed.json)")
            continue
        BACKGROUND_NAMES[name]().save(OUT / f"{name}.png", optimize=True)
        print(f"wrote src/backgrounds/{name}.png")
