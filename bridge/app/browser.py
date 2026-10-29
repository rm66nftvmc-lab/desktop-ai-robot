"""Open the local UI in Edge for an explicit physical button gesture."""

import logging
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time


class BridgeBrowser:
    def __init__(self, url):
        self.url = url
        self._lock = threading.Lock()
        self._last_open = float('-inf')

    def open(self):
        # Device retries or repeated holds must not spawn a burst of tabs.
        with self._lock:
            now = time.monotonic()
            if now - self._last_open < 3:
                return
            self._last_open = now
        try:
            edge = shutil.which('msedge.exe')
            if not edge:
                for variable in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
                    root = os.environ.get(variable)
                    candidate = Path(root) / 'Microsoft/Edge/Application/msedge.exe' if root else None
                    if candidate and candidate.is_file():
                        edge = str(candidate)
                        break
            if not edge:
                raise FileNotFoundError('Microsoft Edge is not installed')
            subprocess.Popen([edge, self.url], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logging.getLogger(__name__).info('Physical long press opened Bridge in Edge')
        except OSError:
            logging.getLogger(__name__).exception('Could not open Bridge in Edge')
