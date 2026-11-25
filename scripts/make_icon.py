"""Draw the app icon (docs/images/icon.png, mcpb/icon.png): a calendar with a workout profile.

Run with: uv run --with pillow python scripts/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SIZE = 1024  # drawn large, scaled down for smooth edges
BLUE = (37, 99, 235)
DARK = (30, 64, 175)
WHITE = (255, 255, 255)
BARS = (59, 130, 246)


def draw() -> Image.Image:
    s = SIZE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s // 5, fill=BLUE)

    # calendar page
    left, top, right, bottom = 0.18 * s, 0.24 * s, 0.82 * s, 0.82 * s
    d.rounded_rectangle((left, top, right, bottom), radius=0.06 * s, fill=WHITE)
    d.rounded_rectangle((left, top, right, top + 0.13 * s), radius=0.06 * s, fill=DARK)
    d.rectangle((left, top + 0.07 * s, right, top + 0.13 * s), fill=DARK)
    for x in (0.32, 0.68):  # binder rings
        d.rounded_rectangle(
            (x * s - 0.03 * s, 0.17 * s, x * s + 0.03 * s, 0.31 * s), radius=0.03 * s, fill=WHITE
        )

    # a stepped workout profile: warm-up, intervals, cool-down
    base = bottom - 0.07 * s
    steps = [0.10, 0.17, 0.30, 0.12, 0.30, 0.12, 0.30, 0.17, 0.10]
    x0, x1 = left + 0.06 * s, right - 0.06 * s
    w = (x1 - x0) / len(steps)
    for i, h in enumerate(steps):
        d.rectangle((x0 + i * w + 2, base - h * s, x0 + (i + 1) * w - 2, base), fill=BARS)
    return img


def main() -> None:
    img = draw().resize((512, 512), Image.LANCZOS)
    for path in (ROOT / "mcpb" / "icon.png", ROOT / "docs" / "images" / "icon.png"):
        img.save(path, optimize=True)
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
