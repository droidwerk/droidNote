"""Porteiro de eco do microfone.

Sem fone, o microfone escuta o alto-falante: a fala de quem está do outro lado
da chamada entrava duas vezes na transcrição (uma pelo áudio do sistema, outra
como se fosse "Você"). Aqui cada quadro de 20 ms do microfone é comparado com o
áudio do sistema no mesmo instante. Quando o microfone só carrega o eco, o
quadro é silenciado para a transcrição — a gravação WAV continua intacta.
"""

from __future__ import annotations

from collections import deque

import numpy as np

FRAME = 320  # 20 ms a 16 kHz
LOOP_ACTIVE_RMS = 0.003
DELAY_FRAMES = 10  # até 200 ms entre o som sair e voltar pelo microfone
OWN_SPEECH_MARGIN = 4.0  # ~12 dB acima do eco esperado


class EchoGate:
    def __init__(self) -> None:
        self._history: deque[float] = deque(maxlen=DELAY_FRAMES)
        self._coupling = 0.25
        self._noise = 0.002
        self.gated_ratio = 0.0
        self._recent: deque[int] = deque(maxlen=50)

    @property
    def coupling(self) -> float:
        return self._coupling

    def process(self, mic: np.ndarray, loop: np.ndarray | None) -> np.ndarray:
        data = np.asarray(mic, dtype=np.float32).reshape(-1)
        if loop is None:
            for _ in range(max(1, data.size // FRAME)):
                self._history.append(0.0)
                self._recent.append(0)
            self.gated_ratio = float(np.mean(self._recent)) if self._recent else 0.0
            return data
        other = np.asarray(loop, dtype=np.float32).reshape(-1)
        out = data.copy()
        for lo in range(0, data.size, FRAME):
            hi = min(data.size, lo + FRAME)
            mic_rms = _rms(data[lo:hi])
            loop_rms = _rms(other[lo:hi]) if lo < other.size else 0.0
            self._history.append(loop_rms)
            envelope = max(self._history) if self._history else loop_rms
            if envelope < LOOP_ACTIVE_RMS:
                self._noise = 0.98 * self._noise + 0.02 * mic_rms if mic_rms < self._noise * 4 else self._noise
                self._recent.append(0)
                continue
            ratio = mic_rms / max(envelope, 1e-6)
            if ratio < self._coupling:
                self._coupling = 0.7 * self._coupling + 0.3 * ratio
            else:
                self._coupling = 0.997 * self._coupling + 0.003 * min(ratio, 2.0)
            own = mic_rms > max(self._coupling * envelope * OWN_SPEECH_MARGIN, self._noise * 3.0)
            if own:
                self._recent.append(0)
                continue
            out[lo:hi] = 0.0
            # Só conta como eco quando havia som de verdade no microfone.
            self._recent.append(1 if mic_rms > self._noise * 2.0 else 0)
        self.gated_ratio = float(np.mean(self._recent)) if self._recent else 0.0
        return out


def _rms(frame: np.ndarray) -> float:
    if frame.size == 0:
        return 0.0
    value = float(np.sqrt(np.mean(frame * frame)))
    return value if np.isfinite(value) else 0.0
