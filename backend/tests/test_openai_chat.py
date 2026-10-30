from __future__ import annotations

import pytest

from app.application.setup import migrate_cloud_llm_setting
from app.infrastructure.llm.openai_chat import (
    CLOUD_LLM_MODELS,
    DEFAULT_CLOUD_LLM_MODEL,
    OpenAIChatEngine,
    normalize_cloud_llm_model,
    request_tuning,
)
from app.infrastructure.persistence.sqlite import SqliteStore


def test_catalog_offers_only_current_models() -> None:
    assert [model_id for model_id, _ in CLOUD_LLM_MODELS] == ["gpt-6-luna", "gpt-5.6-luna", "gpt-5.6-terra"]
    assert DEFAULT_CLOUD_LLM_MODEL == "gpt-6-luna"


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        ("gpt-4o-mini", "gpt-6-luna"),
        ("gpt-4.1-mini", "gpt-6-luna"),
        ("gpt-4.1-nano", "gpt-6-luna"),
        ("gpt-4o-2024-11-20", "gpt-6-luna"),
        ("gpt-4o", "gpt-5.6-terra"),
        ("gpt-4.1", "gpt-5.6-terra"),
        ("", "gpt-6-luna"),
        (None, "gpt-6-luna"),
        (" gpt-5.6-luna ", "gpt-5.6-luna"),
        ("gpt-6.1-sol", "gpt-6.1-sol"),
    ],
)
def test_legacy_note_models_map_to_current_ones(legacy: str | None, expected: str) -> None:
    assert normalize_cloud_llm_model(legacy) == expected
    engine = OpenAIChatEngine(api_key="sk", model=legacy or "")
    assert engine.model == expected
    engine.set_model("gpt-4o-mini")
    assert engine.model == "gpt-6-luna"


def test_request_tuning_per_model_family() -> None:
    # Modelos que respondem direto: sem raciocínio e determinísticos, como o gpt-4o era.
    assert request_tuning("gpt-6-luna") == {"reasoning_effort": "none", "temperature": 0}
    assert request_tuning("gpt-5.6-terra") == {"reasoning_effort": "none", "temperature": 0}
    # Modelos que sempre raciocinam recusam temperature.
    assert request_tuning("gpt-6.1-sol") == {"reasoning_effort": "low"}
    assert request_tuning("gpt-4o-mini") == {"temperature": 0}


def test_build_body_sends_json_mode_and_tuning() -> None:
    engine = OpenAIChatEngine(api_key="sk", model="gpt-6-luna")
    body = engine.build_body("transcrição", system="sys", json_mode=True)
    assert body["model"] == "gpt-6-luna"
    assert body["reasoning_effort"] == "none"
    assert body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    text_body = engine.build_body("x", system="sys", json_mode=False)
    assert "response_format" not in text_body


def _fake_async_client(calls: list[dict[str, object]], responses: list[tuple[int, dict[str, object]]]):
    class FakeResponse:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        def __init__(self, timeout: float, verify: str | bool = True) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, headers: dict[str, str], json: dict[str, object]) -> FakeResponse:
            calls.append(dict(json))
            status, payload = responses[min(len(calls) - 1, len(responses) - 1)]
            return FakeResponse(status, payload)

    return FakeClient


@pytest.mark.asyncio
async def test_rejected_tuning_param_is_dropped_and_retried(monkeypatch) -> None:
    """A OpenAI recusou `temperature` para este modelo: repete sem ele em vez de perder a ata."""
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.infrastructure.llm.openai_chat.httpx.AsyncClient",
        _fake_async_client(
            calls,
            [
                (400, {"error": {"message": "Unsupported value: 'temperature' does not support 0 with this model."}}),
                (200, {"choices": [{"message": {"content": '{"ok": true}'}}]}),
            ],
        ),
    )
    engine = OpenAIChatEngine(api_key="sk-test", model="gpt-6-luna")
    assert await engine.generate_json("oi") == '{"ok": true}'
    assert len(calls) == 2
    assert "temperature" in calls[0]
    assert "temperature" not in calls[1]
    assert calls[1]["reasoning_effort"] == "none"
    assert calls[1]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_other_400_errors_surface_without_retry(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.infrastructure.llm.openai_chat.httpx.AsyncClient",
        _fake_async_client(calls, [(400, {"error": {"message": "context_length_exceeded"}})]),
    )
    engine = OpenAIChatEngine(api_key="sk-test", model="gpt-6-luna")
    with pytest.raises(RuntimeError, match="context_length_exceeded"):
        await engine.generate_text("oi")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_saved_legacy_note_model_is_migrated_on_load(tmp_path) -> None:
    store = SqliteStore(tmp_path / "droidnote.db")
    await store.initialize()
    await store.set_setting("llm_cloud_model", "gpt-4o")

    saved = await store.get_setting("llm_cloud_model")
    assert await migrate_cloud_llm_setting(store, saved, "gpt-6-luna") == "gpt-5.6-terra"
    assert await store.get_setting("llm_cloud_model") == "gpt-5.6-terra"

    fresh = SqliteStore(tmp_path / "fresh.db")
    await fresh.initialize()
    assert await migrate_cloud_llm_setting(fresh, None, "gpt-6-luna") == "gpt-6-luna"
    assert await fresh.get_setting("llm_cloud_model") is None
