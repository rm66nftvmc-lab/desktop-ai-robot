import json
import socket
import time

import pytest
from websockets.sync.client import connect
from websockets.exceptions import InvalidStatus

from bridge.app.network_device import NetworkDevices, NetworkPort
from bridge.app.protocol import FrameParser, HELLO, encode


def test_network_port_preserves_binary_frame_boundaries_and_timeout():
    class Connection:
        def recv(self, timeout): return encode(HELLO, 1, b'{}')
        def send(self, value): self.sent = value
        def close(self): pass
    connection = Connection()
    port = NetworkPort(connection)
    parser = FrameParser()
    assert parser.feed(port.read(3)) == []
    assert parser.feed(port.read(4096))[0].kind == HELLO
    port.write(b'123')
    assert connection.sent == b'123'


def test_listener_auth_binary_roundtrip_and_disconnect(tmp_path):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        number = probe.getsockname()[1]
    token = 'a' * 64
    (tmp_path / 'device-network.json').write_text(json.dumps(
        dict(host='127.0.0.1', port=number, token=token)))
    network = NetworkDevices(tmp_path)
    network.start()
    url = f'ws://127.0.0.1:{number}/device'
    try:
        with pytest.raises(InvalidStatus):
            connect(url, proxy=None)
        with pytest.raises(InvalidStatus):
            connect(url, additional_headers={'Authorization': 'Bearer ' + token},
                    origin='http://evil.invalid', proxy=None)
        with connect(url, additional_headers={'Authorization': 'Bearer ' + token}, proxy=None) as client:
            deadline = time.monotonic() + 2
            port = None
            while not port and time.monotonic() < deadline:
                port = network.take()
                time.sleep(0.005)
            assert port is not None
            client.send(encode(HELLO, 2, b'{}'))
            data = b''
            while not data and time.monotonic() < deadline:
                data = port.read(4096)
            assert FrameParser().feed(data)[0].kind == HELLO
            port.write(b'answer')
            assert client.recv(timeout=1) == b'answer'
            port.close()
    finally:
        network.stop()


def test_invalid_config_does_not_break_usb_startup(tmp_path):
    (tmp_path / 'device-network.json').write_text('{}')
    network = NetworkDevices(tmp_path)
    network.start()
    assert network.error and network.take() is None


def test_device_link_routes_network_recording_and_playback(tmp_path, monkeypatch):
    from bridge.app import device as module
    from bridge.app.protocol import BUTTON, AUDIO_UP, AUDIO_DOWN, ACK, WELCOME
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        number = probe.getsockname()[1]
    token = 'b' * 64
    (tmp_path / 'device-network.json').write_text(json.dumps(
        dict(host='127.0.0.1', port=number, token=token)))
    network = NetworkDevices(tmp_path)
    captures = []
    device = module.DeviceLink(lambda wav, generation: captures.append(wav), network=network)
    monkeypatch.setattr(module, 'find_port', lambda: None)
    network.start()
    device.start()
    try:
        with connect(f'ws://127.0.0.1:{number}/device',
                     additional_headers={'Authorization': 'Bearer ' + token}, proxy=None) as client:
            client.send(encode(HELLO, 0, b'{"protocol":1,"firmware":"test"}'))
            parser = FrameParser()
            deadline = time.monotonic() + 4
            frames = []
            while not any(frame.kind == WELCOME for frame in frames) and time.monotonic() < deadline:
                frames.extend(parser.feed(client.recv(timeout=3)))
            assert any(frame.kind == WELCOME for frame in frames)
            client.send(encode(BUTTON, 1, b'\x01') + encode(AUDIO_UP, 2, b'\x00\x01' * 128)
                        + encode(BUTTON, 3, b'\x00'))
            while not captures and time.monotonic() < deadline:
                time.sleep(0.01)
            assert len(captures) == 1 and len(captures[0]) > 256
            assert device.snapshot()['transport'] == 'wifi'
            assert device.play_wav(captures[0])
            frames = []
            while not any(frame.kind == AUDIO_DOWN for frame in frames) and time.monotonic() < deadline:
                frames.extend(parser.feed(client.recv(timeout=2)))
            assert any(frame.kind == AUDIO_DOWN for frame in frames)
            client.send(encode(ACK, 4, b'\x01'))
            while device.snapshot()['audio_down_ack'] != 1 and time.monotonic() < deadline:
                time.sleep(0.01)
            assert device.snapshot()['audio_down_ack'] == 1
    finally:
        network.stop()
        device.stop()
