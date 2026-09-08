from __future__ import annotations

import sys

from app.domain.ports import AudioCallback, AudioCapturePort


def build_audio_capture(sample_rate: int) -> AudioCapturePort:
    if sys.platform == "win32":
        from app.infrastructure.audio.windows_wasapi import WindowsWasapiCapture

        return WindowsWasapiCapture(sample_rate=sample_rate)
    if sys.platform == "darwin":
        from app.infrastructure.audio.macos_stub import MacOsAudioCapture

        return MacOsAudioCapture(sample_rate=sample_rate)
    return UnsupportedAudioCapture(sample_rate, sys.platform)


class UnsupportedAudioCapture:
    def __init__(self, sample_rate: int, platform: str) -> None:
        self.sample_rate = sample_rate
        self._platform = platform

    def list_devices(self) -> list[dict[str, str]]:
        return []

    def start(
        self,
        callback: AudioCallback,
        *,
        microphone_id: str | None = None,
        loopback_id: str | None = None,
        mic_only: bool = False,
    ) -> None:
        del callback, microphone_id, loopback_id, mic_only
        raise NotImplementedError(
            f"Captura de áudio ainda não existe em {self._platform}. O app oficial é Windows."
        )

    def stop(self) -> None:
        return None

    def probe(self) -> dict[str, bool | str]:
        return {
            "microphone": False,
            "loopback": False,
            "supported": False,
            "message": f"Captura de áudio ainda não existe em {self._platform}. O app oficial é Windows.",
        }
