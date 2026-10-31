from bridge import button_launcher as module
from bridge.app.protocol import HELLO, OPEN_BRIDGE, encode


def hello():
    return encode(HELLO, 0, b'{"protocol":1,"firmware":"voice-device-1.65"}')


def test_listener_requires_robot_hello_and_valid_crc_and_does_not_write():
    launcher = module.ButtonLauncher()
    launcher.ready = lambda: False
    bad = bytearray(encode(OPEN_BRIDGE, 1, b'\x01')); bad[-1] ^= 1
    packets = iter([encode(OPEN_BRIDGE, 1, b'\x01'), hello(), bytes(bad),
                    encode(OPEN_BRIDGE, 2, b'bad'), encode(OPEN_BRIDGE, 3, b'\x01')])
    class Port:
        def read(self, size): return next(packets)
        def write(self, data): raise AssertionError('Standby must never request microphone or handshake')
    assert launcher.listen(Port()) is True
    assert list(packets) == []


def test_listener_releases_device_when_bridge_is_running():
    launcher = module.ButtonLauncher()
    launcher.ready = lambda: True
    class Port:
        def read(self, size): raise AssertionError('Bridge owns the port')
    assert launcher.listen(Port()) is False


def test_standby_closes_serial_before_starting_bridge(monkeypatch):
    launcher = module.ButtonLauncher()
    launcher.ready = lambda: False
    events = []
    class Port:
        def __enter__(self): events.append('open'); return self
        def __exit__(self, *args): events.append('close')
    monkeypatch.setattr(module, 'find_port', lambda: 'COM9')
    monkeypatch.setattr(module, 'open_device_port', lambda name: Port())
    launcher.listen = lambda port: True
    class Finished(BaseException): pass
    def start(): events.append('start'); raise Finished()
    launcher.start_bridge = start
    try: launcher.run()
    except Finished: pass
    assert events == ['open', 'close', 'start']


def test_start_waits_for_health_before_edge_and_uses_hidden_fixed_command(monkeypatch):
    launcher = module.ButtonLauncher()
    states = iter([False, False, True])
    launcher.ready = lambda: next(states)
    actions = []
    class Process:
        def poll(self): return None
    def spawn(args, **kwargs):
        assert args[:3] == ['powershell.exe', '-NoProfile', '-ExecutionPolicy']
        assert args[-1].endswith('start_bridge.ps1')
        assert 'creationflags' in kwargs
        actions.append('start'); return Process()
    monkeypatch.setattr(module.subprocess, 'Popen', spawn)
    monkeypatch.setattr(module.time, 'sleep', lambda n: actions.append('wait'))
    launcher.browser.open = lambda: actions.append('edge')
    assert launcher.start_bridge() is True
    assert actions == ['start', 'wait', 'wait', 'edge']


def test_failed_start_does_not_open_edge(monkeypatch):
    launcher = module.ButtonLauncher()
    launcher.ready = lambda: False
    class Process:
        def poll(self): return 1
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *args, **kwargs: Process())
    launcher.browser.open = lambda: (_ for _ in ()).throw(AssertionError('not ready'))
    assert launcher.start_bridge() is False
