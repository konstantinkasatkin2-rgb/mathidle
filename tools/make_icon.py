"""Генерирует иконку игры: assets/icon.ico + web/icon.png + android mipmap.

    python tools/make_icon.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from mathidle import assets  # noqa: E402

BG_TOP = (26, 33, 47)
BG_BOTTOM = (14, 18, 26)
ACCENT = (79, 209, 197)
GOLD = (246, 196, 83)
TEXT = (232, 237, 245)


def rounded_gradient(size, radius_ratio=0.22):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(grad)
    for y in range(size):
        k = y / max(1, size - 1)
        draw.line(
            [(0, y), (size, y)],
            fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * k) for i in range(3)) + (255,),
        )
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255
    )
    img.paste(grad, (0, 0), mask)
    return img


def make_icon(size=512):
    img = rounded_gradient(size)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(assets.resource("assets/fonts/Roboto-Regular.ttf"), int(size * 0.56))

    sigma = "Σ"
    box = draw.textbbox((0, 0), sigma, font=font)
    draw.text(
        ((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1] - size * 0.02),
        sigma, font=font, fill=TEXT,
    )

    small = ImageFont.truetype(assets.resource("assets/fonts/Roboto-Regular.ttf"), int(size * 0.30))
    plus = "+"
    pbox = draw.textbbox((0, 0), plus, font=small)
    draw.text(
        (size - (pbox[2] - pbox[0]) - size * 0.10, size * 0.06 - pbox[1]),
        plus, font=small, fill=GOLD,
    )

    # тонкая рамка
    draw.rounded_rectangle(
        [2, 2, size - 3, size - 3],
        radius=int(size * 0.22),
        outline=(*ACCENT, 90),
        width=max(2, int(size * 0.012)),
    )
    return img


def main():
    base = make_icon(512)

    ico_path = os.path.join(ROOT, "assets", "icon.ico")
    os.makedirs(os.path.dirname(ico_path), exist_ok=True)
    base.save(ico_path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"[ok] {os.path.relpath(ico_path, ROOT)}")

    web_icon = os.path.join(ROOT, "web", "icon.png")
    os.makedirs(os.path.dirname(web_icon), exist_ok=True)
    base.resize((192, 192), Image.LANCZOS).save(web_icon)
    print(f"[ok] {os.path.relpath(web_icon, ROOT)}")

    res = os.path.join(ROOT, "android", "app", "src", "main", "res")
    for folder, px in [
        ("mipmap-mdpi", 48), ("mipmap-hdpi", 72), ("mipmap-xhdpi", 96),
        ("mipmap-xxhdpi", 144), ("mipmap-xxxhdpi", 192),
    ]:
        target = os.path.join(res, folder)
        os.makedirs(target, exist_ok=True)
        base.resize((px, px), Image.LANCZOS).save(os.path.join(target, "ic_launcher.png"))
        print(f"[ok] android/.../{folder}/ic_launcher.png ({px}px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
