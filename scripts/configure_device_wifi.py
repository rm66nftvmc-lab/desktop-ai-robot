"""Run locally with Bridge stopped; passwords never appear in arguments or logs."""
import argparse
import getpass
import ipaddress
import json
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge.app.device import find_port, open_device_port
from bridge.app.protocol import FrameParser, encode
from bridge.app.security import resolve_data_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='Computer LAN IPv4 address')
    parser.add_argument('--port', type=int, default=8788)
    args = parser.parse_args()
    address = ipaddress.ip_address(args.host)
    if not address.is_private or address.version != 4 or address.is_unspecified:
        parser.error('Use the computer LAN IPv4 address')
    if not 1024 <= args.port <= 65535:
        parser.error('Invalid listener port')
    ssid = input('2.4 GHz Wi-Fi SSID: ').strip()
    password = getpass.getpass('Wi-Fi password (hidden): ')
    if not 1 <= len(ssid.encode()) <= 32 or len(password.encode()) > 63:
        parser.error('Invalid SSID or password length')
    directory, _ = resolve_data_dir()
    path = directory / 'device-network.json'
    old = json.loads(path.read_text()) if path.exists() else {}
    config = dict(host=args.host, port=args.port, token=old.get('token') or secrets.token_hex(32))
    frame = encode(16, 0, json.dumps(dict(config, ssid=ssid, password=password),
                                    ensure_ascii=False).encode())
    name = find_port()
    if not name:
        raise SystemExit('Connect the robot USB first.')
    with open_device_port(name) as port:
        time.sleep(2)
        port.write(frame)
        decoder = FrameParser()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            for result in decoder.feed(port.read(4096)):
                if result.kind == 17:
                    if result.payload != b'\x01':
                        raise SystemExit('Device rejected settings; existing listener config retained.')
                    directory.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix('.tmp')
                    temporary.write_text(json.dumps(config), encoding='utf-8')
                    temporary.replace(path)
                    print('Configured. Restart Bridge; then power robot from a USB charger.')
                    return
    raise SystemExit('No provisioning confirmation; settings not confirmed. Check firmware and stop Bridge.')


if __name__ == '__main__':
    main()
