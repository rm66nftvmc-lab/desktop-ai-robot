"""Generate the robot's calm, low-contrast offline screen background."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "voice-device" / "assets" / "aurora-gradient.png"
WIDTH, HEIGHT = 240, 320


def glow(x: float, y: float, cx: float, cy: float, sx: float, sy: float) -> float:
    return math.exp(-(((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2) * 2.2)


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = image.load()
    for y in range(HEIGHT):
        fy = y / (HEIGHT - 1)
        for x in range(WIDTH):
            fx = x / (WIDTH - 1)
            # A visible teal-to-indigo-to-violet aurora, still subdued behind text/faces.
            stops = ((0.0, (22, 104, 128)), (0.48, (24, 48, 94)),
                     (1.0, (94, 61, 129)))
            for index in range(len(stops) - 1):
                if stops[index][0] <= fy <= stops[index + 1][0]:
                    start, first = stops[index]
                    end, second = stops[index + 1]
                    amount = (fy - start) / (end - start)
                    base = [first[i] * (1 - amount) + second[i] * amount
                            for i in range(3)]
                    break
            teal = glow(fx, fy, 0.85, 0.22, 0.48, 0.22) * 0.38
            violet = glow(fx, fy, 0.12, 0.82, 0.56, 0.34) * 0.34
            blue = glow(fx, fy, 0.14, 0.18, 0.52, 0.25) * 0.18
            colors = (
                base[0] + 7 * teal + 35 * violet + 5 * blue,
                base[1] + 43 * teal + 10 * violet + 14 * blue,
                base[2] + 33 * teal + 58 * violet + 52 * blue,
            )
            pixels[x, y] = tuple(max(0, min(255, round(c))) for c in colors)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, optimize=True)
    print(f"Generated {OUTPUT} ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
