"""Bounded USB-only radio comparison. Stop Bridge first; wiring stays unchanged.

Profile 0 keeps the normal idle load. Profile 1 pauses animation, uninstalls
I2S drivers and uses CPU 80 MHz during the probe. Peripheral power stays on.
"""
import argparse
import json
from pathlib import Path
import sys
import time

import serial

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge.app.device import find_port, open_device_port
from bridge.app.protocol import FrameParser, encode, HELLO, WELCOME, HEARTBEAT, STATUS, NETWORK_STATUS


def wait_hello(port, timeout=7):
    parser = FrameParser()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for frame in parser.feed(port.read(4096)):
            if frame.kind == HELLO:
                port.write(encode(WELCOME, 0, b'{"protocol":1}'))
                return json.loads(frame.payload)
    raise TimeoutError('No device HELLO; no probe sent')


def recover(name):
    end = time.monotonic() + 12
    while time.monotonic() < end:
        try:
            with open_device_port(name) as port:
                wait_hello(port, 4)
                parser = FrameParser()
                status = {}
                deadline = time.monotonic() + 4
                heartbeat = 0
                while time.monotonic() < deadline:
                    if time.monotonic() >= heartbeat:
                        port.write(encode(HEARTBEAT, 1))
                        heartbeat = time.monotonic() + 1
                    for frame in parser.feed(port.read(4096)):
                        if frame.kind in (STATUS, NETWORK_STATUS):
                            status.update(json.loads(frame.payload))
                    if 'reset_reason' in status and 'wifi_safe_mode' in status:
                        return {key: status.get(key) for key in
                                ('reset_reason', 'wifi_safe_mode', 'wifi_configured', 'free_internal')}
        except (serial.SerialException, OSError, TimeoutError):
            time.sleep(0.5)
    return {'recovery': 'not_confirmed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=int, choices=(0, 1), required=True)
    args = parser.parse_args()
    name = find_port()
    if not name:
        raise SystemExit('USB device missing; no probe sent')
    started = False
    last_phase = None
    try:
        with open_device_port(name) as port:
            hello = wait_hello(port)
            if hello.get('firmware') != 'voice-device-1.60':
                raise SystemExit('Expected probe firmware 1.60; no probe sent')
            port.write(encode(18, 2, bytes([args.profile])))
            frames = FrameParser()
            deadline = time.monotonic() + 18
            while time.monotonic() < deadline:
                for frame in frames.feed(port.read(4096)):
                    if frame.kind != 19:
                        continue
                    result = json.loads(frame.payload)
                    last_phase = result.get("phase")
                    print(json.dumps(result), flush=True)
                    if last_phase == "starting":
                        started = True
                    if result.get('phase') == 'complete':
                        return
            print(json.dumps({'profile': args.profile, 'outcome': 'probe_timeout', 'started': started, 'last_phase': last_phase}))
    except serial.SerialException:
        print(json.dumps({'profile': args.profile, 'outcome': 'USB_disconnected', 'started': started, 'last_phase': last_phase}), flush=True)
    print(json.dumps({'after_probe': recover(name)}), flush=True)


if __name__ == '__main__':
    main()
