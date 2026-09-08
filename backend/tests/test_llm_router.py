from __future__ import annotations

import pytest

from app.application.prompts import SUMMARY_PROMPT, SYSTEM_PROMPT
from app.infrastructure.llm.ollama_manager import OllamaManager
from app.infrastructure.llm.openai_chat import OpenAIChatEngine
from app.infrastructure.llm.router import LlmRouter, normalize_provider


def build_router(provider: str = "neste_pc") -> LlmRouter:
    return LlmRouter(
        OllamaManager("http://127.0.0.1:11434", "qwen3:8b"),
        OpenAIChatEngine(api_key="", model="gpt-4o-mini"),
        provider=provider,
    )


def test_local_payload_carries_the_shared_system_prompt() -> None:
    prompt = SUMMARY_PROMPT.format(context="", transcript="oi")
    payload = OllamaManager("http://x", "qwen3:8b").build_payload(prompt, stream=False)
    assert payload["system"] == SYSTEM_PROMPT
    assert payload["prompt"] == prompt
    assert payload["format"] == "json"
    assert payload["think"] is False


def test_provider_switch_moves_notes_to_the_cloud_engine() -> None:
    router = build_router()
    assert router.model == "qwen3:8b"
    router.set_provider("openai")
    assert router.is_cloud
    assert router.model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_cloud_engine_without_key_reports_missing() -> None:
    router = build_router("openai")
    component = await router.status_component()
    assert component.status == "missing"
    router.set_api_key("sk-test")
    assert (await router.status_component()).status == "ready"


def test_normalize_provider_accepts_legacy_aliases() -> None:
    assert normalize_provider("cloud") == "openai"
    assert normalize_provider("") == "neste_pc"
