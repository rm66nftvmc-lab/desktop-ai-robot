"""Reject an absent/stale SDK probe build; report evidence without flashing."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'voice-device/diagnostics/wifi-sdk'


def verify():
    build = PROJECT / '.pio/build/low-power'
    header = build / 'config/sdkconfig.h'
    image = build / 'firmware.bin'
    expected = {
        'CONFIG_ESP_PHY_MAX_WIFI_TX_POWER': 10,
        'CONFIG_ESP_PHY_REDUCE_TX_POWER': 1,
        'CONFIG_ESP_PHY_ENABLE_USB': 1,
        'CONFIG_ESP32S3_DEFAULT_CPU_FREQ_MHZ': 80,
        'CONFIG_ESP32S3_BROWNOUT_DET': 1,
        'CONFIG_ESP32S3_BROWNOUT_DET_LVL': 7,
    }
    values = dict(re.findall(r'^#define\s+(\w+)\s+(\d+)\s*$', header.read_text(), re.M))
    for key, value in expected.items():
        if values.get(key) != str(value):
            raise ValueError(f'SDK configuration mismatch: {key}')
    commands = json.loads((build / 'compile_commands.json').read_text(encoding='utf-8'))
    phy = [c for c in commands if c['file'].replace('\\', '/').endswith('/esp_phy/src/phy_init.c')]
    if not phy:
        raise ValueError('No source build of esp_phy/src/phy_init.c in compile database')
    library = build / 'esp-idf/esp_phy/libesp_phy.a'
    if not library.is_file() or library.stat().st_mtime < header.stat().st_mtime:
        raise ValueError('PHY source library missing or older than SDK configuration')
    # A prior successful image must not be mistaken for a new successful build.
    sources = list((PROJECT / 'src').glob('*')) + [PROJECT / 'sdkconfig.defaults', PROJECT / 'platformio.ini', header]
    if any(p.stat().st_mtime > image.stat().st_mtime for p in sources):
        raise ValueError('Firmware predates source/configuration: rebuild first')
    data = image.read_bytes()
    if len(data) >= 1024*1024 or not data or data[0] != 0xE9:
        raise ValueError('Unexpected diagnostic application size or image header')
    if b'4.4.7' not in data:
        raise ValueError('Expected IDF 4.4.7 application metadata missing')
    return {'configuration': expected, 'phy_source_compiled': True,
            'image_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'hardware_tested': False}


if __name__ == '__main__':
    try:
        print(json.dumps(verify(), indent=2))
    except (OSError, ValueError, KeyError) as exc:
        print(f'SDK probe is not ready: {exc}', file=sys.stderr)
        sys.exit(1)
