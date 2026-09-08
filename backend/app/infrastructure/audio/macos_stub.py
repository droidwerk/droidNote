from __future__ import annotations

from app.domain.ports import AudioCallback


class MacOsAudioCapture:
    """Porta da fase 2: ScreenCaptureKit. Não implementada no MVP Windows."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate

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
        raise NotImplementedError(
            "Captura de áudio no macOS entra na fase 2 (ScreenCaptureKit)."
        )

    def stop(self) -> None:
        return None

    def probe(self) -> dict[str, bool | str]:
        return {
            "microphone": False,
            "loopback": False,
            "supported": False,
            "message": "macOS ainda não é suportado neste MVP.",
        }
