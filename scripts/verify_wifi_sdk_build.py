"""Reject an absent/stale SDK probe build; report evidence without flashing."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'voice-device/diagnostics/wifi-sdk'
BUILD = Path(os.environ.get('PLATFORMIO_BUILD_DIR') or
             (str(Path(os.environ['LOCALAPPDATA']) / 'DesktopAiRobot/wifi-sdk-build')
              if os.name == 'nt' else str(PROJECT / '.pio/build'))) / 'low-power'


def verify():
    build = BUILD
    header = build / 'config/sdkconfig.h'
    image = build / 'firmware.bin'
    expected = {
        'CONFIG_ESP_PHY_MAX_WIFI_TX_POWER': 10,
        'CONFIG_ESP_PHY_MAX_TX_POWER': 10,
        'CONFIG_ESP_PHY_REDUCE_TX_POWER': 1,
        'CONFIG_ESP_PHY_ENABLE_USB': 1,
        'CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG': 1,
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
    if not library.is_file():
        raise ValueError('PHY source library missing')
    # SCons can reuse unchanged objects after a config header timestamp changes.
    # Inspect the actual linked IDF 4.4.7 S3 PHY table instead of relying on mtimes.
    with (build / 'firmware.elf').open('rb') as stream:
        elf = ELFFile(stream)
        symbols = [s for s in elf.get_section_by_name('.symtab').iter_symbols()
                   if s.name == 'phy_init_data']
        if len(symbols) != 1 or symbols[0]['st_size'] != 128:
            raise ValueError('Expected S3 PHY initialization table missing')
        symbol = symbols[0]
        section = elf.get_section(symbol['st_shndx'])
        offset = symbol['st_value'] - section['sh_addr']
        init_data = section.data()[offset:offset+128]
        # Official 4.4.7 S3 layout: 14 power entries at offset 2, units 0.25 dBm.
        if init_data[2:16] != bytes([40]*14):
            raise ValueError('Linked PHY initialization table does not use 10 dBm cap')
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
            'linked_phy_power_entries': list(init_data[2:16]),
            'image_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'hardware_tested': False}


if __name__ == '__main__':
    try:
        print(json.dumps(verify(), indent=2))
    except (OSError, ValueError, KeyError) as exc:
        print(f'SDK probe is not ready: {exc}', file=sys.stderr)
        sys.exit(1)
