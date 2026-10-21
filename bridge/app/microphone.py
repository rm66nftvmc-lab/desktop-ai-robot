"""Conservative two-microphone enhancement for a 5 cm synchronous array.

Runs on the PC, not the LCD task. This is delay-and-sum with a bounded
coherence postfilter, not speaker identification or acoustic echo cancellation.
"""
import numpy as np


class DualMicrophone:
    RATE, SIZE, HOP = 16000, 256, 128

    def __init__(self, spacing_m=.05):
        self.limit = spacing_m / 343 * self.RATE
        self.window = np.sqrt(np.hanning(self.SIZE + 1)[:-1])
        self.omega = 2 * np.pi * np.fft.rfftfreq(self.SIZE)
        self.band = (self.omega * self.RATE / (2*np.pi) >= 250) & (
            self.omega * self.RATE / (2*np.pi) <= 2800)
        self.delays = np.linspace(-self.limit, self.limit, 33)
        self.steering = np.exp(-1j * self.delays[:, None] * self.omega)
        self.highpass = np.clip((self.omega*self.RATE/(2*np.pi) - 60)/120, 0, 1)
        self.reset()

    def reset(self):
        self.pending = np.empty((0, 2), dtype=np.float64)
        self.history = np.zeros((self.HOP, 2))
        self.overlap = np.zeros(self.HOP)
        self.power = np.zeros((self.SIZE//2+1, 2))
        self.cross = np.zeros(self.SIZE//2+1, dtype=complex)
        self.gain = np.ones(self.SIZE//2+1)
        self.delay = 0.0
        self.frames = 0
        self.stats = {'mode': 'warming', 'spacing_cm': 5, 'raw_rms': [0., 0.],
                      'output_rms': 0., 'delay_samples': 0., 'coherence': 0.}

    def process(self, payload, *, capture=False):
        if len(payload) % 4:
            raise ValueError('Stereo PCM must contain complete pairs')
        raw = np.frombuffer(payload, dtype='<i2').reshape(-1, 2).astype(np.float64)
        self.pending = np.concatenate((self.pending, raw))
        output = []
        while len(self.pending) >= self.HOP:
            block, self.pending = self.pending[:self.HOP], self.pending[self.HOP:]
            frame = np.concatenate((self.history, block))
            self.history = block.copy()
            # Remove each microphone's DC bias before checking channel health.
            frame = frame - frame.mean(axis=0)
            levels = np.sqrt(np.mean(frame*frame, axis=0))
            valid = (levels > 2) & (levels > max(levels.max(), 1) / 30)
            spectra = np.fft.rfft(frame * self.window[:, None], axis=0)
            if valid.all():
                cross = spectra[:, 0] * spectra[:, 1].conj()
                weights = self.band / np.maximum(np.abs(cross), 1)
                scores = (self.steering * (cross*weights)[None, :]).real.sum(axis=1)
                if not capture and scores.max() > self.band.sum() * .35:
                    estimate = self.delays[int(np.argmax(scores))]
                    self.delay = .85*self.delay + .15*estimate
                phase = np.exp(1j * self.omega * self.delay)
                aligned = spectra[:, 1] * phase
                alpha = 0 if self.frames == 0 else .85
                self.power = alpha*self.power + (1-alpha)*np.abs(spectra)**2
                self.cross = alpha*self.cross + (1-alpha)*cross
                # Positive coherence in the steered direction suppresses diffuse
                # noise conservatively. A floor prevents hard gating syllables.
                coherence = np.clip((self.cross*phase.conj()).real /
                    np.sqrt(np.maximum(self.power[:, 0]*self.power[:, 1], 1)), 0, 1)
                target = np.maximum(.45, np.sqrt(coherence))
                self.gain = .7*self.gain + .3*target
                merged = (spectra[:, 0] + aligned)*.5*self.gain
                mode = 'dual'
                quality = float(coherence[self.band].mean())
            else:
                # Missing/clipped-off channel must never halve a working mic.
                merged = spectra[:, int(np.argmax(levels))]
                mode, quality = 'single_fallback', 0.
            wave = np.fft.irfft(merged*self.highpass, n=self.SIZE)*self.window
            result = wave[:self.HOP] + self.overlap
            self.overlap = wave[self.HOP:]
            self.frames += 1
            output.append(result)
            self.stats = {'mode': mode, 'spacing_cm': 5,
                'raw_rms': [round(float(v), 1) for v in levels],
                'output_rms': round(float(np.sqrt(np.mean(result*result))), 1),
                'delay_samples': round(self.delay, 3), 'coherence': round(quality, 3)}
        if not output:
            return b''
        return np.clip(np.rint(np.concatenate(output)), -32768, 32767).astype('<i2').tobytes()


class SpeechActivity:
    """Streaming use of the already-installed, local Silero VAD v6 model."""
    def __init__(self):
        self.session = None
        self.reset()

    def reset(self):
        self.pending = bytearray()
        self.h = np.zeros((1, 1, 128), dtype=np.float32)
        self.c = self.h.copy()
        self.context = np.zeros(64, dtype=np.float32)
        self.probability = 0.

    def accept(self, pcm):
        if self.session is None:
            from faster_whisper.vad import get_vad_model
            self.session = get_vad_model().session
        self.pending.extend(pcm)
        while len(self.pending) >= 1024:
            audio = np.frombuffer(bytes(self.pending[:1024]), dtype='<i2').astype(np.float32)/32768
            del self.pending[:1024]
            values = np.concatenate((self.context, audio))[None, :]
            probability, self.h, self.c = self.session.run(None,
                {'input': values, 'h': self.h, 'c': self.c})
            self.context = audio[-64:].copy()
            self.probability = float(np.ravel(probability)[0])
        return self.probability >= .5
