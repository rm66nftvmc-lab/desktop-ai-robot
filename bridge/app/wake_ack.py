"""Local wake acknowledgement, completed before microphone capture starts."""
import time
import hashlib
import io
import threading
import wave
import logging

import numpy as np

from .tts import selected_voice, synthesize_chunks


class WakeAcknowledgement:
    def __init__(self, data_dir, device, audio_output):
        self.data_dir, self.device, self.audio_output = data_dir, device, audio_output
        self._voice = None
        self._clips = ()
        self._lock = threading.Lock()
        self._warm_thread = None
        self._stopped = threading.Event()
        self._status = {'text': '在呢', 'ready': False, 'warming': False}

    def snapshot(self):
        return dict(self._status, ready=self._voice == selected_voice(self.data_dir) and bool(self._clips))

    @staticmethod
    def _compact(clips):
        pcm = bytearray()
        for clip in clips:
            with wave.open(io.BytesIO(clip), 'rb') as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                    raise ValueError('Invalid wake cue format')
                pcm.extend(audio.readframes(audio.getnframes()))
        signal = np.frombuffer(pcm, dtype='<i2')
        if len(signal) < 160 or len(signal) > 160000:
            raise ValueError('Invalid wake cue length')
        active = np.flatnonzero(np.abs(signal.astype(float)) > max(3, np.max(np.abs(signal.astype(float)))*.015))
        if not active.size:
            raise ValueError('Silent wake cue')
        # Keep consonants and the soft ending; trim model-generated blank tails.
        signal = signal[max(0, active[0]-960):min(len(signal), active[-1]+1601)]
        result = io.BytesIO()
        with wave.open(result, 'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
            audio.writeframes(signal.tobytes())
        return result.getvalue()

    @staticmethod
    def _rhythm(clip):
        with wave.open(io.BytesIO(clip), 'rb') as audio:
            signal = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(float)
        duration = len(signal)/16000
        frames = signal[:len(signal)//160*160].reshape(-1, 160)
        energy = np.sqrt(np.mean(frames*frames, axis=1))
        active = np.flatnonzero(energy >= max(8, energy.max()*.08))
        longest = run = 0
        if active.size:
            for value in energy[active[0]:active[-1]+1]:
                run = run+1 if value < max(8, energy.max()*.08) else 0
                longest = max(longest, run)
        return duration, longest*.01

    def prepare(self, cancelled=lambda: False):
        with self._lock:
            voice = selected_voice(self.data_dir)
            if voice == self._voice and self._clips:
                return True
            identity = hashlib.sha256(('wake-cue-v3|在呢！|' + voice).encode()).hexdigest()[:24]
            path = self.data_dir / 'cache' / 'wake-cues' / (identity + '.wav')
            try:
                if path.stat().st_size > 320044:
                    raise ValueError('Oversized cue')
                clip = self._compact([path.read_bytes()])
            except (OSError, ValueError, wave.Error, EOFError):
                candidates = []
                for _ in range(3):
                    if cancelled() or self._stopped.is_set():
                        return False
                    generated = self._compact(tuple(synthesize_chunks('在呢！', self.data_dir, cancelled=cancelled)))
                    duration, gap = self._rhythm(generated)
                    candidates.append((duration + gap*4, generated))
                    if duration <= 1.05 and gap <= .08:
                        break
                clip = min(candidates, key=lambda item: item[0])[1]
            if cancelled() or self._stopped.is_set() or selected_voice(self.data_dir) != voice:
                return False
            self._voice, self._clips = voice, (clip,)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix('.tmp')
                temporary.write_bytes(clip)
                temporary.replace(path)
            except OSError:
                logging.getLogger(__name__).warning('Wake cue disk cache unavailable; keeping memory cache')
            return True

    def warm(self):
        if self._warm_thread and self._warm_thread.is_alive():
            return
        def run():
            self._status['warming'] = True
            try:
                for _ in range(2):
                    if self.prepare(self._stopped.is_set):
                        break
            except Exception:
                logging.getLogger(__name__).warning('Wake cue prewarm failed; will retry on wake')
            finally:
                self._status['warming'] = False
        self._warm_thread = threading.Thread(target=run, name='wake-cue-prewarm', daemon=True)
        self._warm_thread.start()

    def stop(self):
        self._stopped.set()

    def __call__(self, cancelled):
        if cancelled():
            return False
        if not self.audio_output.enabled:
            return True  # Preserve global mute, but still allow a voice question.
        if not self.prepare(cancelled):
            return False
        if cancelled():
            return False
        state = self.device.snapshot()
        if state.get('listening') or state.get('playing') or state.get('device_playing'):
            return False
        generation = self.device.stop_playback()
        if generation is None:
            return False
        try:
            for clip in self._clips:
                if cancelled() or not self.device.is_current_generation(generation):
                    return False
                if not self.device.append_wav(clip, generation=generation):
                    return False
        finally:
            self.device.finish_playback(generation)
        # Device playback status, not HTTP/TTS completion, gates recording.
        deadline, quiet_since = time.monotonic() + 12, None
        while time.monotonic() < deadline:
            if cancelled() or not self.device.is_current_generation(generation):
                self.device.stop_playback(expected_generation=generation)
                return False
            state = self.device.snapshot()
            if not state.get('connected') or state.get('listening'):
                return False
            stream_finished = state.get('playback_finished_generation') == generation
            # STATUS arrives every 3 seconds; an old `device_playing=True`
            # must not add a full telemetry interval after acknowledged AUDIO_END.
            if state.get('playing') or (state.get('device_playing') and not stream_finished):
                quiet_since = None
            else:
                quiet_since = quiet_since or time.monotonic()
                if time.monotonic() - quiet_since >= .3:
                    return True
            time.sleep(.05)
        self.device.stop_playback(expected_generation=generation)
        raise RuntimeError('Wake acknowledgement playback timed out')
