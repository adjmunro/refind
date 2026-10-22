"""A Magikarp drawn in SVG, facing left, for gen_backgrounds.py.

    carp(width, style="natural" | "flat" | "silhouette", angle=0) -> RGBA Image

Fan art of the machine's namesake: rounded orange body, a three-spike crown
fin, two cream whiskers drooping from the upper lip like a moustache, a thick
cream lip ring around a gaping mouth, a big blank eye, spiky pale fins and
tail, crescent scales behind the gill and a paler belly. Drawn on a 620x520 box.
"""
import io
import subprocess

from PIL import Image

PALETTES = {
    # top / middle / belly of the body, scale lines, fins, fin shading, outline, lips, inside of mouth
    "natural": dict(top="#e8481f", mid="#f4622a", belly="#ffb35c", scale="#b8341a", fin="#fff3c8",
                    fin_dark="#e3c46e", line="#5a1407", lip="#fff4d9", mouth="#6a1008", width=5),
    "flat": dict(top="#d9452a", mid="#d9452a", belly="#f0a04b", scale="#9e2c16", fin="#f3e3b5",
                 fin_dark="#cdb173", line="#1c1a2e", lip="#f6ead0", mouth="#4a0f0a", width=9),
}

SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="620" height="520" viewBox="0 0 620 520">
<defs>
  <linearGradient id="body" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{top}"/><stop offset="0.55" stop-color="{mid}"/><stop offset="1" stop-color="{belly}"/>
  </linearGradient>
  <clipPath id="clip"><path d="{body}"/></clipPath>
</defs>
<g stroke="{line}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round">
  <!-- behind the body: tail, crown, far fin -->
  <path d="M520 196 L604 128 L584 196 L612 236 L584 262 L612 304 L584 332 L604 392 L520 316 Z" fill="{fin}"/>
  <path d="M532 214 L586 168 M536 258 L596 258 M532 300 L586 350" fill="none" stroke="{fin_dark}" stroke-width="4"/>
  <path d="M206 120 L232 26 L276 96 L320 14 L356 90 L404 32 L426 122 Z" fill="{fin}"/>
  <path d="M240 60 L252 108 M320 46 L322 100 M398 66 L392 112" fill="none" stroke="{fin_dark}" stroke-width="4"/>
  <path d="M408 396 L398 476 L438 448 L470 474 L458 392 Z" fill="{fin}"/>
  <path d="{body}" fill="url(#body)"/>
</g>
<g clip-path="url(#clip)" fill="none" stroke="{scale}" stroke-width="4" stroke-linecap="round">
{scales}
</g>
<g stroke="{line}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round">
  <path d="{body}" fill="none"/>
  <path d="M270 132 Q312 252 272 396" fill="none" stroke="{scale}" stroke-width="7"/>
  <!-- near pectoral fin, spiky -->
  <path d="M300 322 L270 404 L302 392 L322 432 L344 396 L382 414 L356 318 Z" fill="{fin}"/>
  <path d="M308 340 L292 392 M324 340 L322 414 M340 338 L360 400" fill="none" stroke="{fin_dark}" stroke-width="4"/>
  <!-- whiskers: both off the upper lip, drooping like a moustache -->
  <!-- whiskers: both sprout from behind the top of the lip and droop down and back -->
  <path d="M150 236 C178 296 182 364 152 424 C140 448 150 472 174 476" fill="none" stroke="{line}" stroke-width="{whisker_outline}"/>
  <path d="M150 236 C178 296 182 364 152 424 C140 448 150 472 174 476" fill="none" stroke="{fin}" stroke-width="13"/>
  <path d="M170 232 C214 288 226 360 204 430 C196 456 208 478 232 480" fill="none" stroke="{line}" stroke-width="{whisker_outline}"/>
  <path d="M170 232 C214 288 226 360 204 430 C196 456 208 478 232 480" fill="none" stroke="{fin}" stroke-width="13"/>
  <!-- lips and gaping mouth, set into the front of the face, over the whisker roots -->
  <ellipse cx="128" cy="276" rx="50" ry="56" fill="{lip}"/>
  <ellipse cx="117" cy="279" rx="27" ry="34" fill="{mouth}" stroke="none"/>
  <!-- eye: big and blank -->
  <circle cx="212" cy="182" r="43" fill="#ffffff"/>
  <circle cx="203" cy="186" r="8" fill="#140805" stroke="none"/>
</g>
</svg>"""

BODY = "M120 256 C116 146 240 84 360 84 C482 84 556 168 556 252 C556 332 482 418 356 424 C228 430 124 366 120 256 Z"


def svg(style="natural"):
    p = dict(PALETTES["natural" if style == "silhouette" else style])
    rows = []
    for j, y in enumerate(range(118, 450, 32)):
        for x in range(300 + (j % 2) * 21, 560, 42):
            rows.append(f'  <path d="M{x - 19} {y} A21 21 0 0 0 {x + 19} {y}"/>')
    p.update(body=BODY, scales="\n".join(rows), whisker_outline=p["width"] * 2 + 13)
    return SVG.format(**p)


def carp(width, style="natural", angle=0):
    png = subprocess.run(["rsvg-convert", "-w", str(width)], input=svg(style).encode(),
                         capture_output=True, check=True).stdout
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    if style == "silhouette":
        sil = Image.new("RGBA", im.size, (0, 0, 0, 255))
        sil.putalpha(im.getchannel("A"))
        im = sil
    return im.rotate(angle, resample=Image.BICUBIC, expand=True) if angle else im


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "carp.png"
    sheet = Image.new("RGBA", (1900, 560), (40, 110, 170, 255))
    for i, style in enumerate(["natural", "flat", "silhouette"]):
        f = carp(600, style)
        sheet.alpha_composite(f, (20 + i * 630, 20))
    sheet.save(out)
    print("wrote", out)
