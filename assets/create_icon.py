#!/usr/bin/env python3
"""
Gera o ícone do DJ Mix Player em formato .ico
Execute: py -3 assets/create_icon.py
Requer: pip install pillow
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter


def draw_headphones(size: int) -> Image.Image:
    scale = size / 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ── background circle ─────────────────────────────────────────────────
    bg = [(0, 0), (size - 1, size - 1)]
    d.ellipse(bg, fill=(18, 18, 26, 255))

    # subtle inner gradient via concentric circles
    for i in range(int(40 * scale), 0, -1):
        alpha = int(18 * (i / (40 * scale)))
        d.ellipse(
            [size // 2 - i, size // 2 - i, size // 2 + i, size // 2 + i],
            fill=(30, 60, 120, alpha),
        )

    # ── accent ring ───────────────────────────────────────────────────────
    ring_w = max(1, int(2 * scale))
    d.ellipse(bg, outline=(20, 100, 180, 120), width=ring_w)

    # ── headband arc ──────────────────────────────────────────────────────
    cx, cy = size // 2, size // 2
    band_r = int(88 * scale)
    band_w = max(2, int(14 * scale))

    # draw arc as thick white stroke (top semicircle)
    # PIL arc doesn't support width well at small sizes → use polygon approach
    outer_r = band_r + band_w // 2
    inner_r = band_r - band_w // 2

    pts_outer, pts_inner = [], []
    for deg in range(180, 361):
        rad = math.radians(deg)
        pts_outer.append((cx + outer_r * math.cos(rad), cy + outer_r * math.sin(rad)))
        pts_inner.append((cx + inner_r * math.cos(rad), cy + inner_r * math.sin(rad)))
    pts_inner.reverse()
    band_poly = pts_outer + pts_inner
    d.polygon(band_poly, fill=(230, 235, 245, 255))

    # rounded caps at ends
    cap_r = band_w // 2
    for ang in (180, 360):
        rad = math.radians(ang)
        ex = int(cx + band_r * math.cos(rad))
        ey = int(cy + band_r * math.sin(rad))
        d.ellipse(
            [ex - cap_r, ey - cap_r, ex + cap_r, ey + cap_r],
            fill=(230, 235, 245, 255),
        )

    # ── ear cups ──────────────────────────────────────────────────────────
    cup_w  = int(48 * scale)
    cup_h  = int(60 * scale)
    cup_rx = int(12 * scale)   # corner radius
    stem_w = int(10 * scale)
    stem_h = int(20 * scale)

    for side in (-1, 1):
        # stem connecting headband to cup
        stem_x = cx + side * (band_r - int(7 * scale))
        stem_top = cy
        stem_bot = cy + stem_h
        d.rectangle(
            [stem_x - stem_w // 2, stem_top, stem_x + stem_w // 2, stem_bot],
            fill=(200, 210, 225, 255),
        )

        # cup body
        cup_cx = cx + side * (band_r - int(2 * scale))
        cup_top = stem_bot - int(4 * scale)
        cup_bot = cup_top + cup_h
        cup_l   = cup_cx - cup_w // 2
        cup_r   = cup_cx + cup_w // 2

        # outer shell (blue gradient-like)
        d.rounded_rectangle(
            [cup_l, cup_top, cup_r, cup_bot],
            radius=cup_rx,
            fill=(20, 100, 180, 255),
        )
        # highlight edge
        d.rounded_rectangle(
            [cup_l + int(2 * scale), cup_top + int(2 * scale),
             cup_r - int(2 * scale), cup_bot - int(2 * scale)],
            radius=max(1, cup_rx - int(2 * scale)),
            fill=(25, 120, 210, 255),
            outline=(30, 140, 240, 200),
            width=max(1, int(2 * scale)),
        )
        # inner cushion (dark oval)
        pad = int(8 * scale)
        d.ellipse(
            [cup_l + pad, cup_top + pad, cup_r - pad, cup_bot - pad],
            fill=(12, 14, 20, 255),
            outline=(15, 80, 160, 180),
            width=max(1, int(1.5 * scale)),
        )

    # ── small music note accent (bottom-right) ────────────────────────────
    if size >= 48:
        nx = int(cx + 52 * scale)
        ny = int(cy + 52 * scale)
        nr = int(10 * scale)
        nw = max(1, int(3 * scale))
        # note head
        d.ellipse([nx - nr, ny, nx + nr, ny + int(14 * scale)],
                  fill=(20, 100, 180, 200))
        # stem
        d.rectangle([nx + nr - nw, ny - int(28 * scale), nx + nr, ny + int(4 * scale)],
                    fill=(20, 100, 180, 200))
        # flag
        d.polygon([
            (nx + nr, ny - int(28 * scale)),
            (nx + nr + int(12 * scale), ny - int(20 * scale)),
            (nx + nr, ny - int(14 * scale)),
        ], fill=(20, 100, 180, 200))

    return img


def main():
    out = Path(__file__).parent / "icon.ico"
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    # Render at max size then let Pillow downscale for ICO
    big = draw_headphones(256).convert("RGBA")
    big.save(
        str(out),
        format="ICO",
        sizes=[(s, s) for s in ico_sizes],
    )
    print(f"Ícone gerado: {out}")


if __name__ == "__main__":
    main()
