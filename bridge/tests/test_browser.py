from bridge.app.browser import BridgeBrowser
from bridge.app.device import DeviceLink
from bridge.app.protocol import OPEN_BRIDGE, Frame


def test_edge_launch_uses_argument_list_and_limits_repeated_gestures(monkeypatch):
    from bridge.app import browser
    launched = []
    monkeypatch.setattr(browser.shutil, 'which', lambda name: 'C:/Edge/msedge.exe')
    monkeypatch.setattr(browser.subprocess, 'Popen', lambda args, **kw: launched.append(args))
    now = [10.0]
    monkeypatch.setattr(browser.time, 'monotonic', lambda: now[0])
    action = BridgeBrowser('http://127.0.0.1:8787/')
    action.open(); action.open()
    assert launched == [['C:/Edge/msedge.exe', 'http://127.0.0.1:8787/']]
    now[0] += 4
    action.open()
    assert len(launched) == 2


def test_long_press_requires_handshake_and_does_not_touch_capture():
    calls = []
    device = DeviceLink(on_open_bridge=lambda: calls.append('open'), on_capture=lambda *args: calls.append('capture'))
    frame = Frame(OPEN_BRIDGE, 1, b'\x01')
    device._handle(frame, None, 0)
    assert calls == []
    device._update(connected=True)
    device._handle(Frame(OPEN_BRIDGE, 2, b'bad'), None, 0)
    assert calls == []
    device._handle(frame, None, 0)
    assert calls == ['open']
    assert device.snapshot()['listening'] is False


def test_missing_edge_does_not_crash_device_worker(monkeypatch):
    from bridge.app import browser
    monkeypatch.setattr(browser.shutil, 'which', lambda name: None)
    monkeypatch.setattr(browser.Path, 'is_file', lambda path: False)
    BridgeBrowser('http://127.0.0.1:8787/').open()
