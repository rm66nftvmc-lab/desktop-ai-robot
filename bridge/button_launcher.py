"""Small USB-only standby listener, independent of the Bridge server."""

import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import time
import urllib.request

import serial

from .app.browser import BridgeBrowser
from .app.device import find_port, open_device_port
from .app.protocol import FrameParser, HELLO, OPEN_BRIDGE

URL = 'http://127.0.0.1:8787/'
REPO = Path(__file__).resolve().parents[1]
LOG = logging.getLogger(__name__)
_mutex = None


def single_instance():
    global _mutex
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    _mutex = kernel.CreateMutexW(None, False, 'Local\\DesktopAiRobotButtonLauncher')
    if not _mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    return ctypes.get_last_error() != 183


class ButtonLauncher:
    def __init__(self):
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.browser = BridgeBrowser(URL)

    def ready(self):
        try:
            with self.http.open(URL + 'health', timeout=0.4) as response:
                return json.loads(response.read(4096)).get('ok') is True
        except (OSError, ValueError, AttributeError):
            return False

    def listen(self, port):
        """Return on a verified robot gesture or when Bridge takes ownership.

        No WELCOME, heartbeat, microphone request or AI request is sent here.
        The caller closes the serial handle before starting Bridge.
        """
        parser = FrameParser()
        identified = False
        probe_at = 0.0
        while True:
            now = time.monotonic()
            if now >= probe_at:
                if self.ready():
                    return False
                probe_at = now + 0.5
            for frame in parser.feed(port.read(4096)):
                if frame.kind == HELLO:
                    try:
                        info = json.loads(frame.payload)
                        identified = (info.get('protocol') == 1 and
                                      str(info.get('firmware', '')).startswith('voice-device-'))
                    except (ValueError, AttributeError):
                        identified = False
                elif identified and frame.kind == OPEN_BRIDGE and frame.payload == b'\x01':
                    return True

    def start_bridge(self):
        LOG.info('Long press received; serial released; starting Bridge')
        launcher = subprocess.Popen(
            ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
             str(REPO / 'scripts/start_bridge.ps1')], cwd=str(REPO),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if self.ready():
                self.browser.open()
                LOG.info('Bridge ready; opened Edge')
                return True
            result = launcher.poll()
            if result is not None and result != 0:
                LOG.error('Bridge startup failed (exit %s); see Bridge logs', result)
                return False
            time.sleep(0.5)
        LOG.error('Bridge startup readiness timed out; see Bridge logs')
        return False

    def run(self):
        while True:
            try:
                if self.ready():
                    time.sleep(1)
                    continue
                name = find_port()
                if not name:
                    time.sleep(1)
                    continue
                with open_device_port(name) as port:
                    # Standby never records audio; a bounded read keeps handoff prompt.
                    port.timeout = 0.1
                    launch = self.listen(port)
                if launch:
                    self.start_bridge()
            except (serial.SerialException, OSError):
                LOG.debug('Device absent or busy; retrying', exc_info=True)
                time.sleep(1)
            except Exception:
                LOG.exception('Standby listener recovered from an error')
                time.sleep(2)


def main():
    if not single_instance():
        return
    from .app.security import anchor_path, resolve_data_dir
    anchor = anchor_path()
    root = Path(anchor.read_text(encoding='utf-8-sig').strip()) if anchor.is_file() else resolve_data_dir()[0]
    root.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(root / 'button-launcher.log', maxBytes=1_000_000, backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.info('USB standby button listener started')
    ButtonLauncher().run()


if __name__ == '__main__':
    main()
