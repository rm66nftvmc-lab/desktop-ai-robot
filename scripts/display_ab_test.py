"""Controlled static-screen A/B test. Own COM exclusively; Bridge must be stopped.

Write hold, repeat, compute-only, cpu-load, psram-load, ram-load, flash-load, decode-only, colors-only, combined-load, seq-write, transpose-read, seq-read, steady-motion, motion-normal, motion-slow, motion-fast or stop into --control. Default timeout restores animation.
Status JSONL records only hardware telemetry. Pressing the robot button aborts.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge.app.device import open_device_port
from bridge.app import protocol


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', default='COM9')
    p.add_argument('--control', type=Path, required=True)
    p.add_argument('--log', type=Path, required=True)
    p.add_argument('--max-seconds', type=int, default=600)
    p.add_argument('--restore-bridge', action='store_true')
    args = p.parse_args()
    port = open_device_port(args.port)
    parser = protocol.FrameParser()
    sequence = 0
    connected = False
    began = time.monotonic()
    apply_at = float('inf')
    heartbeat = began
    phase = None
    baseline_hash = None
    prior = None

    def send(kind, payload=b''):
        nonlocal sequence
        port.write(protocol.encode(kind, sequence, payload))
        sequence = (sequence+1) & 0xffff

    args.log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.log.open('a', encoding='utf-8') as log:
            while time.monotonic()-began < args.max_seconds:
                now = time.monotonic()
                for frame in parser.feed(port.read(8192)):
                    if frame.kind == protocol.HELLO:
                        if connected:
                            raise RuntimeError('Device restarted or handshake lost; A/B invalid')
                        print('HELLO', frame.payload.decode(), flush=True)
                        send(protocol.WELCOME, b'{"protocol":1}')
                        send(protocol.THEME, b'\x02')
                        send(protocol.ANIMATION, b'\x01')
                        connected = True
                        apply_at = now+1.5
                    elif frame.kind == protocol.BUTTON:
                        raise RuntimeError('Button pressed; stopped to avoid changing the test pose')
                    elif frame.kind == protocol.STATUS:
                        d = json.loads(frame.payload)
                        record = {'phase': phase, **d}
                        log.write(json.dumps(record)+'\n');log.flush()
                        fields = ['uptime_ms','screen_test','screen_test_hash','pixel_writes',
                                  'pet_action','pet_frame','display_theme','animation_enabled','bad_crc','lcd_spi_hz','presents','source_updates','pet_decode_us','pet_load_us',
                                  'pet_cache_bytes','pet_cache_hits','pet_cache_misses']
                        print(json.dumps({'phase':phase, **{k:d.get(k) for k in fields}}),flush=True)
                        if phase=='steady-motion' and d.get('screen_test')==14:
                            assert d['pet_action']==0 and d['animation_enabled'], 'Steady idle diagnostic not active'
                        frozen_modes = {'hold':1,'repeat':2,'compute-only':3,'cpu-load':4,'psram-load':5,'ram-load':6,'flash-load':7,'decode-only':8,'colors-only':9,'combined-load':10,'seq-write':11,'transpose-read':12,'seq-read':13}
                        if phase in frozen_modes and d.get('screen_test') == frozen_modes[phase]:
                            if baseline_hash is None:
                                baseline_hash = d['screen_test_hash']
                            if d['screen_test_hash'] != baseline_hash:
                                raise RuntimeError('Frozen image changed; A/B invalid')
                            if prior and prior.get('screen_test') == d['screen_test']:
                                writes = d['pixel_writes']-prior['pixel_writes']
                                assert (writes > 0) if phase == 'repeat' else (writes == 0)
                                if phase=='compute-only':
                                    assert d['source_updates']>prior['source_updates'], 'Compute workload did not advance'
                                print('VERIFIED',phase,'pixel write delta',writes,'same image hash',baseline_hash,flush=True)
                            prior = d
                if not connected:
                    if now-began > 15:
                        raise RuntimeError('No device HELLO within 15 seconds')
                    continue
                if now-heartbeat >= 1:
                    send(protocol.HEARTBEAT);heartbeat=now
                if now >= apply_at:
                    desired = args.control.read_text(encoding='utf-8-sig').strip()
                    # A writer may briefly truncate the control file before replacing its text.
                    if not desired:
                        continue
                    if desired == 'stop':
                        break
                    modes={'hold':(1,0),'repeat':(2,0),'compute-only':(3,0),
                           'cpu-load':(4,0),'psram-load':(5,0),'ram-load':(6,0),'flash-load':(7,0),
                           'decode-only':(8,0),'colors-only':(9,0),'combined-load':(10,0),
                           'seq-write':(11,0),'transpose-read':(12,0),'seq-read':(13,0),'steady-motion':(14,0),
                           'motion-normal':(0,0),'motion-slow':(0,1),'motion-fast':(0,2)}
                    if desired not in modes:
                        raise RuntimeError('Unknown display test phase')
                    if desired != phase:
                        send(protocol.SCREEN_TEST, bytes(modes[desired]))
                        if desired.startswith('motion-') or desired=='steady-motion':
                            baseline_hash=None
                        phase=desired;prior=None
                        print('REQUESTED',phase,flush=True)
    finally:
        if connected:
            try:
                send(protocol.SCREEN_TEST,b'\x00')
                send(protocol.ANIMATION,b'\x01')
                time.sleep(.15)
            except Exception:
                pass
        port.close()
        print('Serial closed; normal animation requested',flush=True)
        if args.restore_bridge:
            subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',
                            str(Path(__file__).with_name('start_bridge.ps1')),'-Restart'],check=True)


if __name__ == '__main__':
    main()
