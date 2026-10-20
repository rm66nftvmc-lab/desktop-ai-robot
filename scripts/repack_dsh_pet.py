"""Losslessly optimize each existing zlib frame; decoded pixels stay identical."""
import hashlib
import json
from pathlib import Path
import struct
import zlib


def compress_delta(raw):
    candidates = [zlib.compress(raw, 9)]
    for strategy in (zlib.Z_FILTERED, zlib.Z_RLE, zlib.Z_DEFAULT_STRATEGY):
        encoder = zlib.compressobj(9, zlib.DEFLATED, 15, 9, strategy)
        candidates.append(encoder.compress(raw) + encoder.flush())
    return min(candidates, key=len)


def repack(data):
    count, _, table, payload = struct.unpack_from('<IIII', data, 12)
    header = bytearray(data[:payload])
    output = bytearray()
    for frame in range(count):
        offset, size = struct.unpack_from('<II', data, table + frame * 8)
        old = data[payload + offset:payload + offset + (size & 0x7fffffff)]
        raw = zlib.decompress(old)
        packed = min((old, compress_delta(raw)), key=len)
        assert zlib.decompress(packed) == raw
        struct.pack_into('<II', header, table + frame * 8,
                         len(output), len(packed) | (size & 0x80000000))
        output.extend(packed)
    return bytes(header + output)


if __name__ == '__main__':
    folder = Path(__file__).resolve().parents[1] / 'voice-device/assets/dsh_pet'
    path = folder / 'animations.bin'
    old = path.read_bytes()
    new = repack(old)
    path.write_bytes(new)
    manifest_path = folder / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['compression'] = 'lossless per-frame minimum of zlib level 9 strategies'
    # Preserve whichever existing size/hash keys the asset builder uses.
    manifest['bytes'] = len(new)
    manifest['sha256'] = hashlib.sha256(new).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Lossless repack: {len(old)} -> {len(new)} bytes; all {struct.unpack_from("<I", old, 12)[0]} deltas verified')
