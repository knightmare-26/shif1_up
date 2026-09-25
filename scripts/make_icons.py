"""Build the site icons from one set of shapes: a red italic "1" and two speed streaks, on a
carbon-black rounded square.

    python scripts/make_icons.py

Writes public/favicon.svg, public/favicon.ico (16/32/48), public/logo192.png and public/logo512.png.
The same shape is drawn by LogoMark in src/components/ui/Logo.tsx (LOGO_ONE_POINTS) — change both
together.
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.path.join(ROOT, "public")

RED = "#D62828"
BLACK = "#0A0A0A"
SLANT = 0.2126          # tan(12°): the italic lean
BOX, RADIUS = 64, 14

# The "1" in a 64-unit box before the lean: stem and flag.
ONE = [(35, 13), (45, 13), (45, 51), (35, 51), (35, 25), (27.5, 29.5), (27.5, 21.5)]
STREAKS = [((5, 27, 20, 4.5), 1.0), ((2, 35.5, 23, 4.5), 0.6)]   # (x, y, w, h), opacity


def lean(points):
    """Italicise about the box's middle, so the glyph stays centred."""
    return [(round(x - SLANT * (y - BOX / 2), 2), y) for x, y in points]


def svg() -> str:
    one = " ".join(f"{x},{y}" for x, y in lean(ONE))
    streaks = "".join(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="{RED}"'
        f'{"" if op == 1 else f" opacity={chr(34)}{op}{chr(34)}"}/>'
        for (x, y, w, h), op in STREAKS)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BOX} {BOX}">'
            f'<rect width="{BOX}" height="{BOX}" rx="{RADIUS}" fill="{BLACK}"/>'
            f'{streaks}<polygon points="{one}" fill="{RED}"/></svg>\n')


def png(size: int) -> Image.Image:
    """Drawn 4x larger and scaled down, for smooth edges."""
    k = size * 4 / BOX
    img = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, size * 4 - 1, size * 4 - 1], radius=RADIUS * k, fill=BLACK)
    red = Image.new("RGBA", img.size, RED)
    for (x, y, w, h), op in STREAKS:
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([x * k, y * k, (x + w) * k, (y + h) * k], radius=h / 2 * k,
                                               fill=int(255 * op))
        img.paste(red, (0, 0), mask)
    draw.polygon([(x * k, y * k) for x, y in lean(ONE)], fill=RED)
    return img.resize((size, size), Image.LANCZOS)


def main():
    with open(os.path.join(PUBLIC, "favicon.svg"), "w", encoding="utf-8") as f:
        f.write(svg())
    png(192).save(os.path.join(PUBLIC, "logo192.png"))
    png(512).save(os.path.join(PUBLIC, "logo512.png"))
    png(48).save(os.path.join(PUBLIC, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
    print("icons written to public/:", ", ".join(["favicon.svg", "favicon.ico", "logo192.png", "logo512.png"]))
    print("LOGO_ONE_POINTS =", " ".join(f"{x},{y}" for x, y in lean(ONE)))


if __name__ == "__main__":
    main()
