"""Local wake acknowledgement, completed before microphone capture starts."""
import time

from .tts import selected_voice, synthesize_chunks


class WakeAcknowledgement:
    def __init__(self, data_dir, device, audio_output):
        self.data_dir, self.device, self.audio_output = data_dir, device, audio_output
        self._voice = None
        self._clips = ()

    def __call__(self, cancelled):
        if cancelled():
            return False
        if not self.audio_output.enabled:
            return True  # Preserve global mute, but still allow a voice question.
        voice = selected_voice(self.data_dir)
        if voice != self._voice:
            clips = tuple(synthesize_chunks('我在呢', self.data_dir, cancelled=cancelled))
            if cancelled():
                return False
            if not clips:
                raise RuntimeError('Empty wake acknowledgement')
            self._voice, self._clips = voice, clips
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
            if state.get('playing') or state.get('device_playing'):
                quiet_since = None
            else:
                quiet_since = quiet_since or time.monotonic()
                if time.monotonic() - quiet_since >= .3:
                    return True
            time.sleep(.05)
        self.device.stop_playback(expected_generation=generation)
        raise RuntimeError('Wake acknowledgement playback timed out')
