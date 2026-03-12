"""
make_icon.py — Generate app.ico for CITableCleaner.

Draws a stylised microplate well-selector icon:
  • Dark rounded-rectangle background  (#1e293b)
  • 4 × 3 well grid — five wells highlighted sky-blue, others teal / slate
  • Sky-blue "CSV arrow" badge in the bottom-right corner
  • Exported as multi-resolution .ico  (16, 24, 32, 48, 64, 128, 256)

Run from the CITableCleaner/ directory:
    python make_icon.py
"""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ── Colours (app palette) ─────────────────────────────────────────────────
C_BG       = (15,  26, 42,  255)   # #0f172a
C_SURF     = (30,  41, 59,  255)   # #1e293b
C_ELEV     = (45,  63, 85,  255)   # #2d3f55
C_TEAL     = (13, 148, 136, 255)   # #0d9488
C_SKY      = (56, 189, 248, 255)   # #38bdf8
C_SKY_DIM  = (14, 165, 233, 180)   # #0ea5e9 semi
C_EMPTY    = (51,  65, 85,  220)   # #334155
C_WHITE    = (241, 245, 249, 255)  # #f1f5f9
TRANSPARENT= (0, 0, 0, 0)


def rr(draw: ImageDraw.ImageDraw, xy, radius: float, fill, outline=None, width=1):
    """Draw a filled rounded rectangle."""
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill,
                           outline=outline, width=width)


def circle(draw: ImageDraw.ImageDraw, cx, cy, r, fill, outline=None, width=1):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill,
                 outline=outline, width=width)


def make_frame(size: int) -> Image.Image:
    """Render the icon at the given pixel size."""
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    d   = ImageDraw.Draw(img)

    s = size          # shorthand
    pad = s * 0.06    # outer padding

    # ── Background rounded rect ───────────────────────────────────────────
    bg_r = s * 0.18
    rr(d, (pad, pad, s - pad, s - pad), bg_r, fill=C_SURF)

    # Optional subtle inner glow border
    rr(d, (pad + 1, pad + 1, s - pad - 1, s - pad - 1),
       bg_r - 1, fill=None, outline=C_SKY_DIM, width=max(1, int(s * 0.018)))

    # ── Well grid  (4 columns × 3 rows) ──────────────────────────────────
    #   Leave room at the bottom for the arrow badge (~20 % of height)
    grid_cols = 4
    grid_rows = 3

    area_x0 = s * 0.14
    area_x1 = s * 0.86
    area_y0 = s * 0.14
    area_y1 = s * 0.74      # upper 74 % for the well grid

    cell_w = (area_x1 - area_x0) / grid_cols
    cell_h = (area_y1 - area_y0) / grid_rows

    # Which wells are "selected" (sky-blue)?  visually appealing pattern
    selected = {(0, 0), (0, 1), (1, 0), (2, 2), (3, 2)}
    teal_set  = {(1, 1), (2, 0), (3, 0), (3, 1)}   # available
    # rest = empty / dark

    for row in range(grid_rows):
        for col in range(grid_cols):
            cx = area_x0 + cell_w * col + cell_w / 2
            cy = area_y0 + cell_h * row + cell_h / 2
            r  = min(cell_w, cell_h) * 0.36

            if (col, row) in selected:
                fill = C_SKY
                # tiny white highlight dot
                circle(d, cx, cy, r, fill)
                if r > 4:
                    circle(d, cx - r * 0.3, cy - r * 0.3,
                           max(1, r * 0.18), (255, 255, 255, 160))
            elif (col, row) in teal_set:
                circle(d, cx, cy, r, C_TEAL)
            else:
                circle(d, cx, cy, r, C_EMPTY)

    # ── Bottom badge: arrow-into-csv motif ────────────────────────────────
    #   A right-pointing arrow shape + small "CSV" if size >= 48
    bx0 = s * 0.13
    bx1 = s * 0.87
    by0 = s * 0.77
    by1 = s * 0.91
    badge_r = (by1 - by0) * 0.4
    rr(d, (bx0, by0, bx1, by1), badge_r, fill=C_ELEV)

    # Arrow pointing right inside the badge
    mid_y  = (by0 + by1) / 2
    ah     = (by1 - by0) * 0.52   # arrow total height
    aw     = (bx1 - bx0) * 0.46   # arrow total width
    ax0    = (bx0 + bx1) / 2 - aw / 2
    ax1    = ax0 + aw
    shaft_h= ah * 0.40

    if size >= 24:
        # shaft
        rr(d,
           (ax0, mid_y - shaft_h / 2, ax1 - ah * 0.38, mid_y + shaft_h / 2),
           1, fill=C_SKY)
        # arrowhead
        head_x = ax1 - ah * 0.38
        d.polygon([
            (head_x, mid_y - ah / 2),
            (ax1,    mid_y),
            (head_x, mid_y + ah / 2),
        ], fill=C_SKY)
    else:
        # At 16px just draw a filled arrow rectangle
        rr(d, (ax0, mid_y - ah/2, ax1, mid_y + ah/2), 1, fill=C_SKY)

    return img


def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]

    out_dir = Path(__file__).parent / "citablecleaner" / "resources"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "app.ico"

    # Pillow's ICO plugin takes ONE source image and scales it to all
    # requested sizes internally.  Render each size at native resolution
    # so the artwork is crisp, then write them together via icoformat.
    #
    # The cleanest approach: use the ico format with a pre-rendered dict.
    import struct, io

    def _ico_bytes_for_frames(frame_dict: dict) -> bytes:
        """
        Build a valid ICO binary containing one BMP entry per size.
        frame_dict: {size: PIL.Image RGBA}
        """
        entries = sorted(frame_dict.keys())
        n = len(entries)
        # ICO header: 6 bytes
        # Directory entries: n × 16 bytes
        # Then PNG/BMP data blobs
        header = struct.pack("<HHH", 0, 1, n)   # reserved, type=1(ico), count
        dir_offset = 6 + n * 16
        images_bytes = []
        dirs = []
        for sz in entries:
            img = frame_dict[sz].convert("RGBA")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            data = buf.getvalue()
            encoded_sz = sz if sz < 256 else 0   # 256 stored as 0 per ICO spec
            dirs.append(struct.pack(
                "<BBBBHHII",
                encoded_sz, encoded_sz,  # width, height
                0, 0,                    # color count, reserved
                1, 32,                   # planes, bit count
                len(data),               # size of image data
                dir_offset,              # offset
            ))
            images_bytes.append(data)
            dir_offset += len(data)
        return header + b"".join(dirs) + b"".join(images_bytes)

    frame_dict = {sz: make_frame(sz) for sz in sizes}
    ico_data = _ico_bytes_for_frames(frame_dict)
    out_path.write_bytes(ico_data)
    print(f"Saved {out_path}  ({len(sizes)} sizes: {sizes})")


if __name__ == "__main__":
    main()
