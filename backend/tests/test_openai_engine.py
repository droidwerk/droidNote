from __future__ import annotations

import pytest

from app.application.setup import migrate_cloud_asr_setting
from app.infrastructure.asr.openai_engine import (
    CLOUD_ASR_MODELS,
    DEFAULT_CLOUD_ASR_MODEL,
    OpenAIWhisperEngine,
    normalize_cloud_asr_model,
    samples_to_wav_bytes,
)
from app.infrastructure.asr.router import AsrRouter
from app.infrastructure.asr.whisper_engine import WhisperEngine
from app.infrastructure.persistence.sqlite import SqliteStore


def test_samples_to_wav_has_header() -> None:
    payload = samples_to_wav_bytes([0.1, -0.1, 0.0], 16_000)
    assert payload[:4] == b"RIFF"
    assert b"WAVE" in payload[:16]


def _fake_client(captured: dict[str, object], payload: dict[str, object]):
    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return payload

    class FakeClient:
        def __init__(self, timeout: float, verify: str | bool = True) -> None:
            captured["timeout"] = timeout
            captured["verify"] = verify

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, headers: dict[str, str], data: dict[str, object], files: dict) -> FakeResponse:
            captured["url"] = url
            captured["auth"] = headers["Authorization"]
            captured["data"] = dict(data)
            captured["file_name"] = files["file"][0]
            return FakeResponse()

    return FakeClient


def test_openai_engine_posts_wav_with_gpt_transcribe(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "app.infrastructure.asr.openai_engine.httpx.Client",
        _fake_client(captured, {"text": "Olá mundo", "languages": [{"code": "pt"}]}),
    )
    engine = OpenAIWhisperEngine(api_key="sk-test-key")
    assert engine.model == "gpt-transcribe"
    text, language = engine.transcribe_window([0.2] * 320, 16_000, language="pt")
    assert text == "Olá mundo"
    assert language == "pt"
    assert captured["url"].endswith("/v1/audio/transcriptions")
    assert captured["auth"] == "Bearer sk-test-key"
    assert captured["file_name"] == "audio.wav"
    data = captured["data"]
    assert data["model"] == "gpt-transcribe"
    # gpt-transcribe recebe a lista `languages[]`; mandar `language` junto é recusado pela API.
    assert data["languages[]"] == ["pt"]
    assert "language" not in data
    assert "prompt" not in data
    assert "response_format" not in data


def test_gpt_transcribe_auto_language_comes_from_response(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "app.infrastructure.asr.openai_engine.httpx.Client",
        _fake_client(captured, {"text": "Hola a todos", "languages": [{"code": "es"}]}),
    )
    engine = OpenAIWhisperEngine(api_key="sk-test-key", model="gpt-transcribe")
    text, language = engine.transcribe_window([0.2] * 320, 16_000, language="auto")
    assert text == "Hola a todos"
    assert language == "es"
    assert "languages[]" not in captured["data"]
    assert "language" not in captured["data"]

    # Lista vazia = a OpenAI não reconheceu o idioma.
    monkeypatch.setattr(
        "app.infrastructure.asr.openai_engine.httpx.Client",
        _fake_client(captured, {"text": "Hmm", "languages": []}),
    )
    _, language = engine.transcribe_window([0.2] * 320, 16_000, language=None)
    assert language is None


def test_gpt_transcribe_window_is_one_timed_piece(monkeypatch) -> None:
    """Sem tempo nem falante na resposta: a janela inteira é um trecho só e o
    motor de voz local continua dizendo quem falou."""
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "app.infrastructure.asr.openai_engine.httpx.Client",
        _fake_client(captured, {"text": "Fechado. Entao vamos."}),
    )
    engine = OpenAIWhisperEngine(api_key="sk-test-key", model="gpt-transcribe")
    pieces, language = engine.transcribe_words([0.1] * 16_000 * 5, 16_000, language="pt")
    assert pieces == [(0.0, 5.0, "Fechado. Entao vamos.")]
    assert language == "pt"
    assert "response_format" not in captured["data"]

    monkeypatch.setattr(
        "app.infrastructure.asr.openai_engine.httpx.Client",
        _fake_client(captured, {"text": ""}),
    )
    pieces, _ = engine.transcribe_words([0.0] * 16_000, 16_000, language="pt")
    assert pieces == []


def test_openai_not_ready_without_key() -> None:
    engine = OpenAIWhisperEngine(api_key="")
    assert engine.is_ready() is False


def test_catalog_offers_only_current_models() -> None:
    ids = [model_id for model_id, _ in CLOUD_ASR_MODELS]
    assert ids == ["gpt-transcribe"]
    assert DEFAULT_CLOUD_ASR_MODEL == "gpt-transcribe"


@pytest.mark.parametrize(
    "legacy",
    [
        "gpt-4o-transcribe",
        "gpt-4o-mini-transcribe",
        "gpt-4o-mini-transcribe-2025-12-15",
        "gpt-4o-transcribe-diarize",
        "gpt-4o-transcribe-2026-01-01",
        "whisper-1",
        "",
        "  ",
        None,
    ],
)
def test_legacy_cloud_models_map_to_gpt_transcribe(legacy: str | None) -> None:
    assert normalize_cloud_asr_model(legacy) == "gpt-transcribe"
    assert OpenAIWhisperEngine(api_key="sk", model=legacy or "").model == "gpt-transcribe"


def test_unknown_cloud_model_is_kept() -> None:
    assert normalize_cloud_asr_model(" gpt-transcribe-2027-01-01 ") == "gpt-transcribe-2027-01-01"


@pytest.mark.asyncio
async def test_saved_legacy_model_is_migrated_on_load(tmp_path) -> None:
    store = SqliteStore(tmp_path / "droidnote.db")
    await store.initialize()
    await store.set_setting("asr_cloud_model", "gpt-4o-mini-transcribe")

    saved = await store.get_setting("asr_cloud_model")
    resolved = await migrate_cloud_asr_setting(store, saved, "gpt-transcribe")
    assert resolved == "gpt-transcribe"
    assert await store.get_setting("asr_cloud_model") == "gpt-transcribe"

    # Sem nada salvo: fica o padrão e nada é gravado.
    fresh = SqliteStore(tmp_path / "fresh.db")
    await fresh.initialize()
    assert await migrate_cloud_asr_setting(fresh, None, "gpt-transcribe") == "gpt-transcribe"
    assert await fresh.get_setting("asr_cloud_model") is None


def test_router_openai_does_not_touch_local(tmp_path, monkeypatch) -> None:
    from app.infrastructure.asr import whisper_engine

    monkeypatch.setattr(whisper_engine, "whisper_search_roots", lambda primary: [primary])
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
