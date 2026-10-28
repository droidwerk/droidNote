"""Ganho automático do microfone.

Microfone de notebook longe da boca chega 20–30 dB abaixo do áudio do sistema:
o VAD perde o começo das frases e o Whisper erra mais. Aqui o canal do
microfone (já sem eco) é levado a um nível de fala estável antes da transcrição.

- Só mede o nível nos quadros de fala (acima do ruído de fundo): o silêncio
  não é amplificado até virar chiado.
- Sobe devagar e desce rápido, para não "bombear" entre palavras.
- Só aumenta (nunca abaixo de 1×) e tem limitador suave contra clipping.
A gravação WAV não passa por aqui: ela fica como o microfone captou.
"""

from __future__ import annotations

import numpy as np

FRAME = 320  # 20 ms a 16 kHz
TARGET_RMS = 0.08  # ~ -22 dBFS de fala
MAX_GAIN = 8.0  # +18 dB
SPEECH_OVER_NOISE = 3.0
RISE = 0.02  # por quadro de fala
FALL = 0.3


class AutoGain:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self._gain = 1.0
        self._noise = 0.002
        self._speech = TARGET_RMS

    @property
    def gain(self) -> float:
        return self._gain if self.enabled else 1.0

    @property
    def gain_db(self) -> float:
        return float(20.0 * np.log10(max(self.gain, 1e-6)))

    def process(self, samples: np.ndarray) -> np.ndarray:
        data = np.asarray(samples, dtype=np.float32).reshape(-1)
        if not self.enabled or data.size == 0:
            return data
        out = np.empty_like(data)
        for lo in range(0, data.size, FRAME):
            hi = min(data.size, lo + FRAME)
            frame = data[lo:hi]
            rms = float(np.sqrt(np.mean(frame * frame))) if frame.size else 0.0
            if rms < self._noise * SPEECH_OVER_NOISE:
                # Fundo: acompanha o ruído e mantém o ganho como está.
                self._noise = 0.97 * self._noise + 0.03 * max(rms, 1e-5)
            else:
                self._speech = 0.9 * self._speech + 0.1 * rms
                wanted = min(MAX_GAIN, max(1.0, TARGET_RMS / max(self._speech, 1e-6)))
                rate = FALL if wanted < self._gain else RISE
                self._gain += (wanted - self._gain) * rate
                # Nunca deixa o pico do quadro estourar.
                peak = float(np.max(np.abs(frame)))
                if peak * self._gain > 0.98:
                    self._gain = max(1.0, 0.98 / max(peak, 1e-6))
            out[lo:hi] = frame * self._gain
        np.clip(out, -1.0, 1.0, out=out)
        return out
