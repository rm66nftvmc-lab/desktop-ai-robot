import json

import pytest
import serial

from scripts import read_minimal_wifi_probe as probe


class Port:
    def __init__(self, records):
        self.data = b''.join(json.dumps(r).encode()+b'\n' for r in records)
        self.writes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        if not self.data:
            raise serial.SerialException('test disconnect')
        data, self.data = self.data[:size], self.data[size:]
        return data

    def write(self, data):
        self.writes.append(data)


def record(stage, **extra):
    return {'probe': 'minimal-radio-1', 'stage': stage, 'result': 0, **extra}


@pytest.mark.parametrize('embedded_version', [False, True])
def test_old_and_sdk_reports_trigger_once_and_complete(monkeypatch, embedded_version):
    version = {'idf_version': 'v4.4.7'} if embedded_version else {}
    records = [record('ready', **version), record('ready', **version),
               record('wifi_start', **version), record('complete', **version)]
    port = Port(records)
    monkeypatch.setattr(probe, 'find_port', lambda: 'COM_TEST')
    monkeypatch.setattr(probe, 'open_device_port', lambda _: port)
    result = probe.read_probe()
    assert result['outcome'] == 'complete'
    assert port.writes == [b'RUN_RADIO\n']
    assert result['records'][-1]['stage'] == 'complete'


def test_usb_loss_retains_last_rf_stage_without_retry(monkeypatch):
    port = Port([record('ready', idf_version='v4.4.7'),
                 record('before_wifi_start', idf_version='v4.4.7')])
    monkeypatch.setattr(probe, 'find_port', lambda: 'COM_TEST')
    monkeypatch.setattr(probe, 'open_device_port', lambda _: port)
    result = probe.read_probe()
    assert result['outcome'] == 'USB_disconnected'
    assert result['last_stage'] == 'before_wifi_start'
    assert port.writes == [b'RUN_RADIO\n']
