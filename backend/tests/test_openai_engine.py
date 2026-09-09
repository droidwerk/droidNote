from __future__ import annotations

from app.infrastructure.asr.openai_engine import OpenAIWhisperEngine, samples_to_wav_bytes
from app.infrastructure.asr.router import AsrRouter
from app.infrastructure.asr.whisper_engine import WhisperEngine


def test_samples_to_wav_has_header() -> None:
    payload = samples_to_wav_bytes([0.1, -0.1, 0.0], 16_000)
    assert payload[:4] == b"RIFF"
    assert b"WAVE" in payload[:16]


def test_openai_engine_posts_wav(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {"text": "Olá mundo"}

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            captured["timeout"] = timeout

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, headers: dict[str, str], data: dict[str, str], files: dict) -> FakeResponse:
            captured["url"] = url
            captured["auth"] = headers["Authorization"]
            captured["model"] = data["model"]
            captured["language"] = data.get("language")
            captured["file_name"] = files["file"][0]
            return FakeResponse()

    monkeypatch.setattr("app.infrastructure.asr.openai_engine.httpx.Client", FakeClient)
    engine = OpenAIWhisperEngine(api_key="sk-test-key", model="whisper-1")
    text, language = engine.transcribe_window([0.2] * 320, 16_000, language="pt")
    assert text == "Olá mundo"
    assert language == "pt"
    assert captured["url"].endswith("/v1/audio/transcriptions")
    assert captured["auth"] == "Bearer sk-test-key"
    assert captured["language"] == "pt"
    assert captured["file_name"] == "audio.wav"


def test_openai_not_ready_without_key() -> None:
    engine = OpenAIWhisperEngine(api_key="")
    assert engine.is_ready() is False


def test_router_openai_does_not_touch_local(tmp_path) -> None:
    local = WhisperEngine("small", tmp_path / "models")
    openai = OpenAIWhisperEngine(api_key="sk-abc")
    router = AsrRouter(local, openai, provider="openai")
    assert router.is_ready() is True
    assert router.device == "api"
    router.set_provider("neste_pc")
    assert router.provider == "neste_pc"
    assert router.is_ready() is False
    router.set_provider("openai")
    assert router.is_ready() is True
