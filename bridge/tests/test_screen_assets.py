"""Validate the actual compressed firmware artwork and cyclic dirty regions."""

from pathlib import Path
import re
import zlib

import numpy as np


def test_compressed_screen_frames_and_loop_bounds():
    source = (Path(__file__).resolve().parents[2] / 'voice-device/src/screen_assets.h').read_text(encoding='utf-8')
    frames = {}
    for name, payload in re.findall(r'uint8_t (SCREEN_FACE_\d+_\d+)\[\] PROGMEM = \{(.*?)\};', source, re.S):
        compressed = bytes(int(value, 16) for value in re.findall(r'0x([0-9A-F]{2})', payload))
        raw = zlib.decompress(compressed)
        assert len(raw) == 240 * 240 * 2
        frames[name] = np.frombuffer(raw, dtype='>u2').reshape(240, 240)
    assert len(frames) == 69
    for state, count in ((1, 24), (4, 24), (5, 16)):
        assert all(f'SCREEN_FACE_{state}_{i}' in frames for i in range(count))
    entries = re.findall(r'\{(SCREEN_FACE_\d+_\d+), sizeof\(\1\), \{(\d+), (\d+), (\d+), (\d+)\}\}', source)
    for name, *bounds in entries:
        state, index = map(int, name.removeprefix('SCREEN_FACE_').split('_'))
        count = sum(key.startswith(f'SCREEN_FACE_{state}_') for key in frames)
        previous = frames[f'SCREEN_FACE_{state}_{(index - 1) % count}']
        changed = previous != frames[name]
        x0, y0, x1, y1 = map(int, bounds)
        assert 0 <= x0 <= x1 < 240 and 0 <= y0 <= y1 < 240
        changed[y0:y1 + 1, x0:x1 + 1] = False
        assert not changed.any(), f'Dirty bounds missed changed pixels in {name}'
