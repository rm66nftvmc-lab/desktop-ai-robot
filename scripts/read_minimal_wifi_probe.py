"""Run the one-shot minimal-radio firmware already installed on USB.

This reader does not flash/erase firmware or configure credentials. Stop Bridge
first. The minimal firmware must be restored to normal firmware after testing.
"""
import json
import argparse
from pathlib import Path
import sys
import time

import serial

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge.app.device import find_port, open_device_port


def read_probe(*, calibration_only=False):
    name = find_port()
    if not name:
        raise RuntimeError('USB device not found')
    sent = False
    last = None
    records = []
    buffer = bytearray()
    try:
        with open_device_port(name) as port:
            end = time.monotonic() + 15
            while time.monotonic() < end:
                buffer.extend(port.read(4096))
                while b'\n' in buffer:
                    line, _, buffer = buffer.partition(b'\n')
                    try:
                        value = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if not isinstance(value, dict):
                        continue
                    if 'idf_version' in value and 'stage' not in value:
                        records.append(value)
                        print(json.dumps(value), flush=True)
                        continue
                    if value.get('probe') != 'minimal-radio-1':
                        continue
                    records.append(value)
                    last = value.get('stage')
                    print(json.dumps(value), flush=True)
                    if last == 'ready' and not sent:
                        port.write(b'READ_CALIBRATION\n' if calibration_only else b'RUN_RADIO\n')
                        sent = True
                    elif last == 'complete':
                        return {'outcome': 'complete', 'records': records}
                    elif sent and last not in ('ready', 'calibration_cache') and value.get('result') not in (0, None):
                        # Existing event loop/netif are harmless in an Arduino runtime.
                        if last not in ('event_loop', 'netif_init') or value.get('result_name') != 'ESP_ERR_INVALID_STATE':
                            return {'outcome': 'api_error', 'records': records}
    except serial.SerialException:
        return {'outcome': 'USB_disconnected', 'last_stage': last, 'records': records}
    return {'outcome': 'timeout', 'last_stage': last, 'records': records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibration-only', action='store_true')
    result = read_probe(calibration_only=parser.parse_args().calibration_only)
    print(json.dumps({key: value for key, value in result.items() if key != 'records'}), flush=True)
