"""Génère assets/icon.ico (barres d'onde sonore sur fond bleu nuit)."""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512
BG = (11, 15, 23, 255)
BLUE = (111, 143, 214, 255)
VIOLET = (154, 133, 216, 255)
HEIGHTS = [0.30, 0.55, 0.85, 0.50, 0.70]


def draw() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=110, fill=BG)
    bar, gap = 54, 28
    total = len(HEIGHTS) * bar + (len(HEIGHTS) - 1) * gap
    x = (SIZE - total) // 2
    for i, h in enumerate(HEIGHTS):
        bh = int(SIZE * 0.62 * h)
        y0 = (SIZE - bh) // 2
        d.rounded_rectangle((x, y0, x + bar, y0 + bh), radius=bar // 2,
                            fill=VIOLET if i % 2 else BLUE)
        x += bar + gap
    return img


if __name__ == "__main__":
    out = Path(__file__).with_name("icon.ico")
    draw().save(out, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(out)
