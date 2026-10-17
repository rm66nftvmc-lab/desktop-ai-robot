"""Build the ESP32 screen background and compact transparent animation frames."""

from __future__ import annotations

import hashlib
import urllib.request
import zlib
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "voice-device" / "assets"
ATLAS = Path.home() / "AppData" / "Local" / "DesktopAiRobot" / "faces" / "spritesheet.webp"
BACKGROUND = ASSETS / "aurora-gradient.png"
OUT = ROOT / "voice-device" / "src" / "screen_assets.h"
PREVIEW = ROOT / "faces-screen-preview.png"

ATLAS_URL = (
    "https://raw.githubusercontent.com/f0909172434/deepseek-girl-codex-pet/"
    "2572709632b0e81401b9e92994f2c3786c186397/pet/spritesheet.webp"
)
ATLAS_SHA256 = "234f24a97c18195a00c6093da0090773e675993c169e92e7e13a24c37b323fa2"

WIDTH, HEIGHT = 240, 320
FACE = 240
INTERPOLATION_STEPS = 4
FRAME_COUNT = 6 * INTERPOLATION_STEPS
ROTATE_CCW = 90
BRIGHTNESS = 0.9

# Face id -> atlas row, first animation column, frame count. Keep recording
# static so LCD transfers cannot interrupt the microphone's USB audio stream.
# Use every valid frame in each action; the wave row has only four.
ANIMATION = {
    0: (3, 0, 1),  # boot greeting (static)
    1: (0, 0, 6),  # idle
    2: (6, 0, 1),  # waiting for user (static)
    3: (6, 0, 1),  # listening / attentive
    4: (7, 0, 6),  # thinking / working
    5: (3, 0, 4),  # speaking / waving; columns 4 and 5 are blank
    6: (8, 0, 1),  # tool approval / reviewing
    7: (5, 0, 1),  # error (static)
}
ATLAS_SIZE = (1536, 2288)
CELL_SIZE = (192, 208)


def rgb565(red: int, green: int, blue: int) -> int:
    return ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)


def fit_background(image: Image.Image) -> Image.Image:
    image = image.convert("RGB")
    width, height = image.size
    crop_width = min(width, height * WIDTH // HEIGHT)
    left = (width - crop_width) // 2
    image = image.crop((left, 0, left + crop_width, height))
    image = image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    return ImageEnhance.Brightness(image).enhance(BRIGHTNESS)


def make_frame(atlas: Image.Image, row: int, column: int) -> Image.Image:
    x = column * CELL_SIZE[0]
    y = row * CELL_SIZE[1]
    cell = atlas.crop((x, y, x + CELL_SIZE[0], y + CELL_SIZE[1]))
    scale = min(FACE / cell.width, FACE / cell.height)
    size = (round(cell.width * scale), round(cell.height * scale))
    cell = cell.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (FACE, FACE), (0, 0, 0, 0))
    canvas.alpha_composite(cell, ((FACE - size[0]) // 2, (FACE - size[1]) // 2))
    if ROTATE_CCW == 90:
        canvas = canvas.transpose(Image.Transpose.ROTATE_90)
    elif ROTATE_CCW == 270:
        canvas = canvas.transpose(Image.Transpose.ROTATE_270)
    return canvas


def encode_frame(frame: Image.Image) -> list[int]:
    """RLE pairs: two alpha bits and fourteen count bits, then RGB565."""
    pixels: list[tuple[int, int]] = []
    for red, green, blue, alpha in frame.getdata():
        alpha_level = (alpha * 3 + 127) // 255
        pixels.append((alpha_level, rgb565(red, green, blue)))

    encoded: list[int] = []
    alpha, color = pixels[0]
    count = 0
    for next_alpha, next_color in pixels:
        if (alpha, color) != (next_alpha, next_color) or count == 0x3FFF:
            encoded.extend(((alpha << 14) | count, color))
            alpha, color, count = next_alpha, next_color, 1
        else:
            count += 1
    encoded.extend(((alpha << 14) | count, color, 0, 0))
    return encoded


def dirty_bounds(previous: Image.Image, current: Image.Image) -> tuple[int, int, int, int]:
    """Inclusive bounds of every changed RGBA channel, with a safety pixel."""
    boxes = [channel.getbbox() for channel in ImageChops.difference(previous, current).split()]
    boxes = [box for box in boxes if box]
    if not boxes:
        return (0, 0, 0, 0)
    return (max(0, min(box[0] for box in boxes) - 1),
            max(0, min(box[1] for box in boxes) - 1),
            min(FACE - 1, max(box[2] for box in boxes)),
            min(FACE - 1, max(box[3] for box in boxes)))


def interpolate_frames(first: Image.Image, second: Image.Image) -> list[Image.Image]:
    """Bidirectional flow warp in premultiplied alpha, including loop closure."""
    a, b = np.asarray(first).astype(np.float32) / 255, np.asarray(second).astype(np.float32) / 255
    pa, pb = a.copy(), b.copy()
    pa[:, :, :3] *= a[:, :, 3:4]
    pb[:, :, :3] *= b[:, :, 3:4]
    ga = cv2.cvtColor(np.uint8(np.clip(pa[:, :, :3] * 255, 0, 255)), cv2.COLOR_RGB2GRAY)
    gb = cv2.cvtColor(np.uint8(np.clip(pb[:, :, :3] * 255, 0, 255)), cv2.COLOR_RGB2GRAY)
    options = (0.5, 4, 21, 4, 7, 1.5, 0)
    ab = cv2.calcOpticalFlowFarneback(ga, gb, None, *options)
    ba = cv2.calcOpticalFlowFarneback(gb, ga, None, *options)
    gx, gy = np.meshgrid(np.arange(FACE, dtype=np.float32), np.arange(FACE, dtype=np.float32))
    result = [first]
    x0, y0, x1, y1 = dirty_bounds(first, second)
    for step in range(1, INTERPOLATION_STEPS):
        t = step / INTERPOLATION_STEPS
        wa = cv2.remap(pa, gx - t * ab[:, :, 0], gy - t * ab[:, :, 1], cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_CONSTANT)
        wb = cv2.remap(pb, gx - (1 - t) * ba[:, :, 0], gy - (1 - t) * ba[:, :, 1], cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_CONSTANT)
        mixed = wa * (1 - t) + wb * t
        mixed[:, :, :3] /= np.maximum(mixed[:, :, 3:4], 1e-6)
        output = np.asarray(first).copy()
        # Preserve unchanged artwork (especially text) bit-for-bit.
        output[y0:y1 + 1, x0:x1 + 1] = np.uint8(np.clip(np.rint(mixed[y0:y1 + 1, x0:x1 + 1] * 255), 0, 255))
        result.append(Image.fromarray(output))
    return result


def composite565(frame: Image.Image, background: Image.Image) -> np.ndarray:
    rgb = np.asarray(Image.alpha_composite(background, frame).convert("RGB"), dtype=np.uint16)
    return ((rgb[:, :, 0] & 248) << 8) | ((rgb[:, :, 1] & 252) << 3) | (rgb[:, :, 2] >> 3)


def pixel_bounds(previous: np.ndarray, current: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(previous != current)
    if not len(xs):
        return (0, 0, 0, 0)
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


def format_bytes(name: str, values: bytes) -> str:
    lines = [", ".join(f"0x{value:02X}" for value in values[i:i + 20])
             for i in range(0, len(values), 20)]
    return f"static const uint8_t {name}[] PROGMEM = {{\n  " + ",\n  ".join(lines) + "\n};\n"


def format_array(name: str, values: list[int]) -> str:
    lines = [", ".join(f"0x{value:04X}" for value in values[i:i + 12])
             for i in range(0, len(values), 12)]
    return f"static const uint16_t {name}[] PROGMEM = {{\n  " + ",\n  ".join(lines) + "\n};\n"


def ensure_sources() -> Image.Image:
    if not ATLAS.exists():
        ATLAS.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(ATLAS_URL, ATLAS)
    atlas_bytes = ATLAS.read_bytes()
    if hashlib.sha256(atlas_bytes).hexdigest() != ATLAS_SHA256:
        raise SystemExit(f"Sprite atlas checksum mismatch: {ATLAS}")
    if not BACKGROUND.exists():
        raise SystemExit(f"Generated screen background is missing: {BACKGROUND}")
    return Image.open(ATLAS).convert("RGBA")


def main() -> None:
    atlas = ensure_sources()
    if atlas.size != ATLAS_SIZE:
        raise SystemExit(f"Sprite atlas has unexpected size: {atlas.size}")
    background = fit_background(Image.open(BACKGROUND))
    bg_values = [rgb565(*pixel) for pixel in background.getdata()]
    declarations = [format_array("SCREEN_BACKGROUND", bg_values)]
    frame_names: dict[tuple[int, int], str] = {}
    dirty_rects: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    total_bytes = len(bg_values) * 2
    frame_counts: dict[int, int] = {}
    ready_preview: list[Image.Image] = []
    face_background = background.convert("RGBA").crop((0, (HEIGHT-FACE)//2, WIDTH, (HEIGHT+FACE)//2))

    for face_id, (row, first_column, count) in ANIMATION.items():
        frames = [make_frame(atlas, row, first_column + offset)
                  for offset in range(count)]
        for offset, frame in enumerate(frames):
            if frame.getchannel("A").getbbox() is None:
                raise SystemExit(f"Face {face_id} frame {offset} is empty")
        if count > 1:
            frames = [image for offset in range(count)
                      for image in interpolate_frames(frames[offset], frames[(offset + 1) % count])]
        frame_counts[face_id] = len(frames)
        pixels = [composite565(frame, face_background) for frame in frames]
        for offset in range(len(frames)):
            name = f"SCREEN_FACE_{face_id}_{offset}"
            frame = frames[offset]
            raw = pixels[offset].astype(">u2").tobytes()
            values = zlib.compress(raw, 9)
            if zlib.decompress(values) != raw:
                raise SystemExit(f"Frame compression verification failed: {face_id}/{offset}")
            declarations.append(format_bytes(name, values))
            frame_names[(face_id, offset)] = name
            dirty_rects[(face_id, offset)] = pixel_bounds(pixels[offset - 1], pixels[offset])
            total_bytes += len(values)
            if face_id == 1:
                canvas = background.convert("RGBA")
                canvas.alpha_composite(frame, (0, (HEIGHT-FACE)//2))
                ready_preview.append(canvas.convert("RGB"))

    table = []
    for face_id in range(len(ANIMATION)):
        row, first_column, count = ANIMATION[face_id]
        count = frame_counts[face_id]
        names = [frame_names[(face_id, i)] for i in range(count)]
        rects = [dirty_rects[(face_id, i)] for i in range(count)]
        entries = ["{" + name + ", sizeof(" + name + "), {" + ", ".join(map(str, rect)) + "}}"
                   for name, rect in zip(names, rects)]
        table.append("  { { " + ", ".join(entries) + f" }}, {count} }}, // face {face_id}, atlas row {row}")

    header = (
        "// Generated by scripts/build_screen_assets.py; do not edit.\n"
        "// Background: locally generated soft aurora gradient.\n"
        "// Character atlas: f0909172434/deepseek-girl-codex-pet, MIT.\n"
        "// Frames: zlib-compressed, precomposited big-endian RGB565; three optical-flow intermediates per source pair.\n"
        "#pragma once\n#include <Arduino.h>\n#include <pgmspace.h>\n\n"
        f"static constexpr uint16_t SCREEN_BG_WIDTH={WIDTH}, SCREEN_BG_HEIGHT={HEIGHT};\n"
        f"static constexpr uint8_t SCREEN_ANIMATION_FRAME_COUNT={FRAME_COUNT};\n"
        "struct ScreenDirtyRect { uint8_t x0, y0, x1, y1; };\n"
        "struct ScreenCompressedFrame { const uint8_t *data; uint32_t size; ScreenDirtyRect dirty; };\n"
        "struct ScreenFaceFrames { ScreenCompressedFrame frame[SCREEN_ANIMATION_FRAME_COUNT]; uint8_t count; };\n\n"
        + "\n".join(declarations)
        + "\nstatic const ScreenFaceFrames SCREEN_FACES[] PROGMEM = {\n"
        + "\n".join(table)
        + "\n};\n"
    )
    OUT.write_text(header, encoding="utf-8", newline="\n")

    preview = background.convert("RGBA")
    preview.alpha_composite(make_frame(atlas, *ANIMATION[1][:2]),
                            (0, (HEIGHT-FACE)//2))
    preview.convert("RGB").save(PREVIEW, optimize=True)
    # GIF timing is quantized to 10 ms; distribute rounding to retain 1080 ms.
    durations = [(round((i + 1) * 18 / INTERPOLATION_STEPS) -
                  round(i * 18 / INTERPOLATION_STEPS)) * 10
                 for i in range(len(ready_preview))]
    ready_preview[0].save(ROOT / "faces-screen-smooth.gif", save_all=True,
                          append_images=ready_preview[1:], duration=durations, loop=0, disposal=2)
    contact = Image.new("RGB", (WIDTH * 4, HEIGHT))
    for i in range(4):
        contact.paste(ready_preview[i], (WIDTH * i, 0))
    contact.save(ROOT / "faces-interpolation-preview.png")
    print(f"Generated {OUT}; {total_bytes:,} stored asset bytes; frames={frame_counts}.")
    print(f"Generated static screen preview {PREVIEW}.")


if __name__ == "__main__":
    main()
