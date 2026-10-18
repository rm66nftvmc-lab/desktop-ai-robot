"""Identify manual playback requests so late starts/stops cannot affect newer audio."""

from collections import deque
import threading
import uuid


class PlaybackControl:
    def __init__(self, device):
        self.device = device
        self._lock = threading.Lock()
        self._active = None
        self._retired = deque(maxlen=256)

    def claim(self, identity=None):
        identity = identity or str(uuid.uuid4())
        with self._lock:
            if identity in self._retired:
                return identity, None, True
            generation = self.device.stop_playback()
            if generation is not None:
                if self._active:
                    self._retired.append(self._active['id'])
                self._active = {'id': identity, 'generation': generation, 'synthesizing': True}
            return identity, generation, False

    def stop(self, identity=None):
        with self._lock:
            if identity:
                self._retired.append(identity)
                if not self._active or self._active['id'] != identity:
                    return False
            if self._active:
                self._retired.append(self._active['id'])
                generation = self.device.stop_playback(expected_generation=self._active['generation'])
                self._active = None
            else:
                generation = self.device.stop_playback()
            return generation is not None

    def finished(self, identity):
        with self._lock:
            if self._active and self._active['id'] == identity:
                self._active['synthesizing'] = False

    def snapshot(self):
        with self._lock:
            if self._active:
                current = self.device.is_current_generation(self._active['generation'])
                if not current or (not self._active['synthesizing'] and not self.device.snapshot()['playing']):
                    self._retired.append(self._active['id'])
                    self._active = None
            if not self._active:
                return {'state': 'idle', 'playback_id': None}
            return {'state': 'synthesizing' if self._active['synthesizing'] else 'playing',
                    'playback_id': self._active['id']}
