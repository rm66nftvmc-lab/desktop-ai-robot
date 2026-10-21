"""Opt-in local wake recognition; background PCM is bounded, never saved/uploaded."""
import importlib.util
import json
import math
import queue
import re
import struct
import threading
import time

from .storage import get_setting, set_setting

PHRASE = '你好大肥鱼'
END_SILENCE = 1.0
CHANNELS = {'auto': 0, 'left': 1, 'right': 2}


class WakeRecognizer:
    def __init__(self, path):
        from vosk import Model, KaldiRecognizer, SetLogLevel
        SetLogLevel(-1)
        self.model = Model(str(path))
        remaining, words = PHRASE, []
        while remaining:
            word = next((remaining[:n] for n in range(len(remaining), 0, -1)
                         if self.model.vosk_model_find_word(remaining[:n]) >= 0), None)
            if word is None:
                raise ValueError('Wake phrase is outside model vocabulary')
            words.append(word)
            remaining = remaining[len(word):]
        self.rec = KaldiRecognizer(self.model, 16000, json.dumps([' '.join(words), '[unk]'], ensure_ascii=False))
        self.rec.SetWords(True)
        # Word-aligned partials withhold the last word until alignment is final.
        # Plain partial hypotheses are earlier; require the complete phrase to
        # remain unchanged for 300 ms before accepting one.
        self.rec.SetPartialWords(False)
        self._partial_audio = 0.

    def reset(self):
        self.rec.Reset()
        self._partial_audio = 0.

    def accept(self, pcm):
        final = self.rec.AcceptWaveform(pcm)
        result = json.loads(self.rec.Result() if final else self.rec.PartialResult())
        text = re.sub(r'[^\u4e00-\u9fff]', '', result.get('text' if final else 'partial', ''))
        words = result.get('result' if final else 'partial_result', [])
        confident = bool(words) and sum(w.get('conf', 0) for w in words)/len(words) >= .75
        matched = text == PHRASE and (confident if final or words else True)
        if final:
            self._partial_audio = 0.
            return matched
        self._partial_audio = self._partial_audio + len(pcm)/32000 if matched else 0.
        return self._partial_audio >= .3


class WakeWorker:
    def __init__(self, database, data_dir, device, voice_busy=lambda: False, recognizer_factory=WakeRecognizer,
                 acknowledge=None, speech_activity=None):
        self.database, self.device, self.voice_busy = database, device, voice_busy
        self.acknowledge = acknowledge
        self.speech_activity = speech_activity
        self.model_path = data_dir / 'models/vosk-model-small-cn-0.22'
        self.factory = recognizer_factory
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._queue = queue.Queue(maxsize=64)  # At most ~0.5s of microphone data.
        self._thread = None
        self._engine = None
        self._epoch = 0
        self._decoder_epoch = -1
        self._pcm = bytearray()
        self._noise = 60.0
        self._automatic = False
        self._started = self._cooldown = 0.0
        self._speech = self._silence = 0.0
        self._generation = 0
        self._count = 0
        self._samples = 0
        self._level = 0.0
        self._error = None
        try:
            saved = json.loads(get_setting(database, 'wake_word') or '{}')
        except (ValueError, TypeError):
            saved = {}
        if not isinstance(saved, dict):
            saved = {}
        self._enabled = saved.get('enabled') is True
        self._channel = saved.get('mic_channel', 'auto')
        if self._channel not in CHANNELS:
            self._channel = 'auto'
        self.device.configure_wake(False, CHANNELS[self._channel])
        self._state = 'loading' if self._enabled else 'disabled'

    def snapshot(self):
        with self._lock:
            return {'enabled': self._enabled, 'phrase': '你好，大肥鱼', 'state': self._state,
                    'mic_channel': self._channel, 'wake_count': self._count, 'last_error': self._error,
                    'pcm_samples': self._samples, 'mic_rms': self._level,
                    'speech_probability': self.speech_activity.probability if self.speech_activity else None,
                    'acknowledgement': self.acknowledge.snapshot() if hasattr(self.acknowledge, 'snapshot') else None,
                    'model_ready': (self.model_path / 'am/final.mdl').is_file()}

    def update(self, enabled, mic_channel):
        if mic_channel not in CHANNELS:
            raise ValueError('Unknown microphone channel')
        if enabled and (not (self.model_path / 'am/final.mdl').is_file()
                        or importlib.util.find_spec('vosk') is None):
            raise RuntimeError('本地唤醒模型尚未安装')
        if enabled and self.device.snapshot().get('wake_protocol') != 1:
            raise RuntimeError('请先连接支持语音唤醒的固件')
        with self._lock:
            if self._automatic:
                self.device.request_capture(2, self._generation)
            self._automatic = False
            self._enabled, self._channel = enabled, mic_channel
            self._epoch += 1
            self._error = None
            self._samples = 0
            self._state = 'loading' if enabled else 'disabled'
            set_setting(self.database, 'wake_word', json.dumps({'enabled': enabled, 'mic_channel': mic_channel}))
        self.device.configure_wake(False, CHANNELS[mic_channel])
        return self.snapshot()

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='local-wake', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.device.configure_wake(False, CHANNELS[self._channel])
        if self._thread:
            self._thread.join(timeout=3)

    def feed(self, pcm, capture, generation):
        with self._lock:
            if not self._enabled:
                return
            if self._state == 'acknowledging':
                return  # Do not accumulate the robot's own acknowledgement.
            self._samples += len(pcm)//2
            item = (self._epoch, bytes(pcm), capture, generation, time.monotonic())
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            # Invalidate the whole backlog rather than recognize stale speech.
            with self._lock:
                self._epoch += 1

    def capture_changed(self, listening, generation):
        with self._lock:
            if self.speech_activity:
                self.speech_activity.reset()
            automatic = listening and self._state == 'waking'
            self._epoch += 1
            self._automatic = automatic
            self._generation = generation
            self._started = time.monotonic()
            self._speech = self._silence = 0
            if not self._enabled:
                return
            if listening:
                self._state = 'recording' if automatic else 'manual'
                if automatic:
                    self._count += 1
            else:
                self._cooldown = time.monotonic()+1.5
                self._state = 'armed'

    def disconnected(self):
        with self._lock:
            self._epoch += 1
            self._automatic = False
            if self._enabled:
                self._state = 'loading'

    def _finish(self, cancel=False):
        self.device.request_capture(2 if cancel else 0, self._generation)
        self._state = 'finishing'
        self._automatic = False

    def _tick(self):
        if self._state in ('armed', 'paused'):
            status = self.device.snapshot()
            if status.get('playing') or status.get('device_playing') or self.voice_busy():
                self._cooldown = time.monotonic()+.8
                if self._state == 'armed':
                    self._state = 'paused'
                    self._engine.reset()
                    self._pcm.clear()
        if self._state == 'waking' and time.monotonic()-self._started > 3:
            self._state, self._error = 'error', '唤醒录音启动未确认，请检查设备'
            self._enabled = False
            self.device.configure_wake(False, CHANNELS[self._channel])
        if self._automatic and time.monotonic()-self._started >= 20:
            self._finish(cancel=self._speech < .2)
        elif self._automatic and self._speech < .2 and time.monotonic()-self._started >= 6:
            self._finish(cancel=True)

    def _consume(self, item):
        epoch, pcm, capture, generation, at = item
        with self._lock:
            if not self._enabled or epoch != self._epoch or time.monotonic()-at > .6:
                return
            values = struct.unpack(f'<{len(pcm)//2}h', pcm)
            rms = math.sqrt(sum(v*v for v in values)/max(1, len(values)))
            self._level = round(rms, 1)
            if capture:
                if self._automatic and generation == self._generation:
                    duration = len(pcm)/32000
                    voiced = (self.speech_activity.accept(pcm) if self.speech_activity
                              else rms >= max(120, self._noise*3))
                    if voiced:
                        self._speech += duration
                        self._silence = 0
                    else:
                        self._silence += duration
                    if self._speech >= .2 and self._silence >= END_SILENCE:
                        self._finish()
                return
            state = self.device.snapshot()
            blocked = (state.get('listening') or state.get('playing') or state.get('device_playing')
                       or self.voice_busy() or time.monotonic() < self._cooldown)
            if blocked or self._state not in ('armed', 'paused'):
                self._pcm.clear()
                if self._state == 'armed':
                    self._state = 'paused'
                    self._engine.reset()
                return
            self._state = 'armed'
            if rms < 300:
                self._noise = .98*self._noise+.02*rms
            self._pcm.extend(pcm)
            if len(self._pcm) < 3200:
                return
            audio = bytes(self._pcm)
            self._pcm.clear()
            if self._engine.accept(audio):
                self._epoch += 1
                self._error = None
                self._state = 'acknowledging' if self.acknowledge else 'waking'
                self._started = time.monotonic()
                if not self.acknowledge and not self.device.request_capture(1):
                    self._state, self._error = 'error', '设备正忙，暂时无法唤醒'

    def _acknowledge_wake(self):
        with self._lock:
            if self._state != 'acknowledging':
                return
            epoch = self._epoch

        def cancelled():
            with self._lock:
                return (self._stop.is_set() or not self._enabled or self._epoch != epoch
                        or self._state != 'acknowledging')

        try:
            ready = self.acknowledge(cancelled)
        except Exception as exc:
            ready = False
            with self._lock:
                if not cancelled():
                    self._error = f'唤醒提示音未完成（{type(exc).__name__}），请重新呼叫'
        with self._lock:
            if cancelled():
                return
            self._epoch += 1
            if not ready:
                self._state = 'armed'
                self._cooldown = time.monotonic() + .8
                return
            self._state = 'waking'
            self._started = time.monotonic()
            if not self.device.request_capture(1):
                self._state, self._error = 'armed', '设备正忙，请稍后重新呼叫'
                self._cooldown = time.monotonic() + .8

    def _run(self):
        while not self._stop.is_set():
            try:
                with self._lock:
                    enabled, epoch = self._enabled, self._epoch
                if enabled:
                    if self._engine is None:
                        self._engine = self.factory(self.model_path)
                    with self._lock:
                        if (not self._stop.is_set() and self._enabled and epoch == self._epoch
                                and self._state == 'loading'):
                            self.device.configure_wake(True, CHANNELS[self._channel])
                            self._state = 'armed'
                        if self._decoder_epoch != self._epoch:
                            self._engine.reset()
                            self._pcm.clear()
                            self._decoder_epoch = self._epoch
                        self._tick()
                item = self._queue.get(timeout=.1)
                self._consume(item)
                self._acknowledge_wake()
            except queue.Empty:
                pass
            except Exception as exc:
                with self._lock:
                    self._enabled = False
                    self._automatic = False
                    self._state, self._error = 'error', f'本地唤醒不可用（{type(exc).__name__}）'
                self.device.configure_wake(False, CHANNELS[self._channel])
