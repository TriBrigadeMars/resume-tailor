"""Generate the ResumeTailor application icon (ResumeTailor.ico).

Run:  .venv\\Scripts\\python make_icon.py
"""

from PIL import Image, ImageDraw, ImageFont

SIZE = 256


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded-square background with a blue->purple gradient.
    s = size
    radius = int(s * 0.22)
    top = (56, 130, 246)    # blue
    bottom = (129, 140, 248)  # indigo
    for y in range(s):
        color = lerp(top, bottom, y / s)
        d.line([(0, y), (s, y)], fill=color + (255,))

    # Mask the square into a rounded rectangle.
    mask = Image.new("L", (s, s), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=255)
    img.putalpha(mask)

    # Draw a document shape (white page with folded corner).
    pad = int(s * 0.16)
    doc_w = int(s * 0.52)
    doc_h = int(s * 0.62)
    x0, y0 = pad, int(s * 0.16)
    x1, y1 = x0 + doc_w, y0 + doc_h
    fold = int(s * 0.12)
    d.polygon(
        [(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1)],
        fill=(255, 255, 255, 255),
    )
    # Fold triangle
    d.polygon(
        [(x1 - fold, y0), (x1 - fold, y0 + fold), (x1, y0 + fold)],
        fill=(226, 232, 240, 255),
    )

    # Text lines on the page.
    line_w = int(s * 0.30)
    line_h = int(s * 0.035)
    lx = x0 + int(s * 0.05)
    ly = y0 + int(s * 0.16)
    for i in range(4):
        d.rounded_rectangle(
            [lx, ly + i * (line_h + int(s * 0.03)), lx + line_w, ly + i * (line_h + int(s * 0.03)) + line_h],
            radius=line_h // 2,
            fill=(148, 163, 184, 255),
        )

    # Sparkle/star in the top-right.
    cx, cy = int(s * 0.78), int(s * 0.26)
    r_outer = int(s * 0.09)
    r_inner = int(s * 0.035)
    pts = []
    for i in range(10):
        r = r_outer if i % 2 == 0 else r_inner
        ang = -90 + i * 36
        import math

        pts.append((cx + r * math.cos(math.radians(ang)), cy + r * math.sin(math.radians(ang))))
    d.polygon(pts, fill=(253, 224, 71, 255))

    return img


if __name__ == "__main__":
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [make_icon(s) for s in sizes]
    imgs[-1].save(
        "ResumeTailor.ico",
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=imgs[:-1],
    )
    print("Wrote ResumeTailor.ico")
