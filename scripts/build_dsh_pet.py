"""Build pinned, attributed DSH pet clips for offline ESP32 playback.

Requires FFmpeg with libvpx, Pillow, numpy and OpenCV. Originals stay outside Git.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import urllib.parse
import urllib.request
import zlib

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SHA = 'c6f96350d9307bd6c23bc6ea31974e76a719a8b6'
SOURCE = 'https://github.com/PC2005-cloud/dsh-pet'
NAMES = ['待机呼吸休闲', '东张西望', '轻快记录', '工作状态-思考冒泡',
         '碎碎念-对屏碎碎念', '原地专心玩魔方', '撸猫', '吹气球', '三球抛接',
         '女仆屈膝礼仪', '点击回应-开心跃动', '打瞌睡被惊醒', '鲸鱼吐泡泡特效']
SIZE = 168
FPS = 40


def background():
    a = np.zeros((240, 320, 3), np.uint8)
    for y in range(240):
        t = y / 239
        a[y] = np.array((32, 42, 73)) * (1-t) + np.array((106, 107, 139))*t
    im = Image.fromarray(a)
    d = ImageDraw.Draw(im)
    d.ellipse((258, 18, 281, 41), fill=(225, 220, 192))
    for x, y in [(25, 38), (82, 20), (225, 55), (292, 94), (42, 112)]:
        d.line((x-2, y, x+2, y), fill=(141, 154, 184))
        d.line((x, y-2, x, y+2), fill=(141, 154, 184))
    d.ellipse((55, 208, 268, 239), fill=(148, 138, 151))
    d.ellipse((62, 208, 261, 229), fill=(183, 163, 165))
    d.text((69, 232), 'github.com/PC2005-cloud/dsh-pet', fill=(199, 202, 217), font_size=9)
    return im


def decode(path):
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-c:v', 'libvpx-vp9',
        '-i', str(path), '-vf', f'format=rgba,pad=640:400:0:0:color=black@0,crop=320:320:160:24,scale={SIZE}:{SIZE}:flags=lanczos',
        '-f', 'rawvideo', '-pix_fmt', 'rgba', '-'])
    return np.frombuffer(raw, np.uint8).reshape(-1, SIZE, SIZE, 4).copy()


def intermediate(a, b, flow, fraction):
    ga = cv2.cvtColor(a, cv2.COLOR_RGBA2GRAY)
    gb = cv2.cvtColor(b, cv2.COLOR_RGBA2GRAY)
    forward = flow.calc(ga, gb, None)
    backward = flow.calc(gb, ga, None)
    yy, xx = np.mgrid[:SIZE, :SIZE].astype(np.float32)
    def warp(im, motion, fraction):
        premult = im.astype(np.float32)/255
        premult[:, :, :3] *= premult[:, :, 3:4]
        return cv2.remap(premult, xx-motion[:, :, 0]*fraction,
                         yy-motion[:, :, 1]*fraction, cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT)
    result = warp(a, forward, fraction)*(1-fraction)+warp(b, backward, 1-fraction)*fraction
    result[:, :, :3] /= np.maximum(result[:, :, 3:4], 1e-5)
    return np.rint(np.clip(result, 0, 1)*255).astype(np.uint8)


def build(cache, out):
    cv2.setNumThreads(2)
    flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    cache.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    if not (cache/'tree.json').exists():
        urllib.request.urlretrieve(
            f'https://api.github.com/repos/PC2005-cloud/dsh-pet/git/trees/{SHA}?recursive=1',
            cache/'tree.json')
    tree = json.loads((cache/'tree.json').read_text(encoding='utf-8-sig'))
    assert tree['sha'] == SHA and not tree.get('truncated'), 'Unexpected source tree'
    blobs = {i['path']: i for i in tree['tree']}
    source_meta = []
    for name in NAMES:
        relative = f'dsh-pet/assets/webm/{name}.webm'
        path = cache/f'{name}.webm'
        if not path.exists():
            urllib.request.urlretrieve(f'https://raw.githubusercontent.com/PC2005-cloud/dsh-pet/{SHA}/'+urllib.parse.quote(relative), path)
        data = path.read_bytes()
        digest = hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
        assert digest == blobs[relative]['sha'], name
        source_meta.append({'name': name, 'path': relative, 'git_blob': digest})
    bg = background()
    crop = bg.crop((76, 36, 244, 204))
    def compose(frame):
        return Image.alpha_composite(crop.convert('RGBA'), Image.fromarray(frame)).convert('RGB')
    samples = []
    for name in NAMES:
        npy = cache/f'{name}.{SIZE}.npy'
        if not npy.exists():
            np.save(npy, decode(cache/f'{name}.webm'))
        frames = np.load(npy, mmap_mode='r')
        samples.extend(np.asarray(compose(f))[::4, ::4] for f in frames[::24])
    palette = Image.fromarray(np.concatenate(samples, axis=0)).quantize(64)
    colors = np.pad(np.array(palette.getpalette(), np.uint8), (0, 768-len(palette.getpalette()))).reshape(256, 3).astype(np.uint16)
    colors = np.rint(255*(colors.astype(np.float32)/255)**.85).astype(np.uint16)
    rgb565 = ((colors[:, 0]>>3)<<11)|((colors[:, 1]>>2)<<5)|(colors[:, 2]>>3)
    bg_index = np.asarray(bg.quantize(palette=palette, dither=Image.Dither.NONE))
    Image.fromarray(colors[bg_index].astype(np.uint8)).save(out/'background.png')
    # Every frame and the surrounding background use the same quantization.
    background_bytes = rgb565[bg_index].astype('>u2')
    (out/'background.bin').write_bytes(np.rot90(background_bytes).tobytes())
    clips, table, payloads, preview = [], [], bytearray(), []
    total = 0
    for clip_id, name in enumerate(NAMES):
        frames = np.load(cache/f'{name}.{SIZE}.npy', mmap_mode='r')
        start = total
        previous = np.zeros((SIZE, SIZE), np.uint8)
        count = round(len(frames)*FPS/24)
        for j in range(count):
            position = j*len(frames)/count
            i = int(position)
            fraction = position-i
            f = frames[i] if fraction < 1e-6 else intermediate(frames[i], frames[(i+1)%len(frames)], flow, fraction)
            indices = np.asarray(compose(f).quantize(palette=palette, dither=Image.Dither.NONE))
            key = j % FPS == 0
            delta = indices if key else np.bitwise_xor(indices, previous)
            packed = zlib.compress(delta.tobytes(), 9)
            table.append((len(payloads), len(packed) | (0x80000000 if key else 0)))
            payloads.extend(packed)
            previous = indices.copy()
            if j == count//2:
                preview.append(Image.fromarray(colors[indices].astype(np.uint8)).resize((168,168)))
            total += 1
        clips.append((start, total-start))
        print(f'{clip_id}: {name}: {total-start} frames, total {len(payloads)/1048576:.2f} MiB', flush=True)
    clip_offset = 28+512
    frame_offset = clip_offset+len(clips)*8
    data_offset = frame_offset+len(table)*8
    header = struct.pack('<4sHHHHIIII', b'DSP1', SIZE, SIZE, FPS, len(clips), total, clip_offset, frame_offset, data_offset)
    pack = header+rgb565.astype('<u2').tobytes()+b''.join(struct.pack('<II',*c) for c in clips)+b''.join(struct.pack('<II',*f) for f in table)+payloads
    (out/'animations.bin').write_bytes(pack)
    manifest = {'source': SOURCE, 'revision': SHA, 'fps':FPS, 'size':SIZE,
        'interpolation':'offline bidirectional optical-flow resampling; source duration retained',
        'source_fps':24, 'display_gamma':.85, 'random_actions': list(range(5,13)), 'idle_gap_ms':[8000,22000],
        'clips':[dict(source_meta[i], first=first, frames=count, seconds=count/FPS) for i,(first,count) in enumerate(clips)],
        'sha256':hashlib.sha256(pack).hexdigest(), 'bytes':len(pack)}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sheet = Image.new('RGB',(168*5,168*3),(32,42,73))
    for i, im in enumerate(preview):sheet.paste(im,((i%5)*168,(i//5)*168))
    sheet.save(out/'preview.png')
    urllib.request.urlretrieve(f'https://raw.githubusercontent.com/PC2005-cloud/dsh-pet/{SHA}/LICENSE',out/'LICENSE')
    (out/'NOTICE.md').write_text(f'# DSH pet assets\n\nSource: {SOURCE}\n\nRevision: `{SHA}`. Copyright PC2005-cloud, 2026.\n\nCode: MIT (see LICENSE). Animation materials: upstream permits open-source use, prohibits commercial use, and requires the original repository link in derivatives. See the source README license section. These material restrictions are distinct from the code license.\n\nThis derivative crops, composites, quantizes and interpolates the original animations. Background generated locally. Original source videos are verified by Git blob hash and cached outside this repository.\n',encoding='utf-8')


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--cache',type=Path,default=Path(os.environ['LOCALAPPDATA'])/'DesktopAiRobot/display-dsh')
    p.add_argument('--out',type=Path,default=ROOT/'voice-device/assets/dsh_pet')
    a=p.parse_args()
    build(a.cache,a.out)
