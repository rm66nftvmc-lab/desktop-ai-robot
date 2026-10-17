"""Persistent local speaker controls, shared by manual and automatic replies."""

import json
from pathlib import Path
from threading import Lock

import numpy as np


class AudioOutput:
    def __init__(self, data_dir: Path | None = None):
        self._lock = Lock()
        self._path = data_dir / 'audio-output.json' if data_dir else None
        self._volume = 100
        self._muted = False
        if self._path:
            try:
                saved = json.loads(self._path.read_text(encoding='utf-8'))
                if type(saved.get('volume')) is int and 0 <= saved['volume'] <= 100:
                    self._volume = saved['volume']
                if type(saved.get('muted')) is bool:
                    self._muted = saved['muted']
            except (OSError, ValueError, AttributeError):
                pass

    def snapshot(self) -> dict:
        with self._lock:
            return {'volume': self._volume, 'muted': self._muted,
                    'enabled': not self._muted and self._volume > 0}

    @property
    def enabled(self) -> bool:
        return self.snapshot()['enabled']

    def update(self, *, volume: int | None = None, muted: bool | None = None) -> dict:
        if volume is not None and (type(volume) is not int or not 0 <= volume <= 100):
            raise ValueError('Volume must be an integer from 0 to 100')
        if muted is not None and type(muted) is not bool:
            raise ValueError('Muted must be a boolean')
        with self._lock:
            values = {'volume': self._volume if volume is None else volume,
                      'muted': self._muted if muted is None else muted}
            if self._path:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self._path.with_suffix('.json.tmp')
                temporary.write_text(json.dumps(values), encoding='utf-8')
                temporary.replace(self._path)
            self._volume, self._muted = values['volume'], values['muted']
        return self.snapshot()

    def scale_pcm(self, pcm: bytes) -> bytes:
        settings = self.snapshot()
        if not settings['enabled']:
            return bytes(len(pcm))
        if settings['volume'] == 100:
            return pcm
        samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32)
        return np.rint(samples * (settings['volume'] / 100)).astype('<i2').tobytes()
