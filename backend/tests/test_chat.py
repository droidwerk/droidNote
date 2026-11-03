from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.domain.models import Session, TranscriptSegment
from app.infrastructure.asr.whisper_engine import _segment_is_speech
from app.infrastructure.persistence.sqlite import SqliteStore, new_id
from tests.conftest import auth


class _Seg:
    def __init__(self, no_speech: float, logprob: float) -> None:
        self.no_speech_prob = no_speech
        self.avg_logprob = logprob


def test_segment_quality_gates_drop_silence_hallucinations() -> None:
    assert _segment_is_speech(_Seg(0.9, -0.2)) is False
    assert _segment_is_speech(_Seg(0.1, -1.5)) is False
    assert _segment_is_speech(_Seg(0.2, -0.4)) is True


@pytest.mark.asyncio
async def test_chat_uses_transcripts_and_stays_generalist(client: AsyncClient, app) -> None:
    store: SqliteStore = app.state.container.store
    session = Session(
        id=new_id(),
        title="Aula de grafos",
        started_at=datetime.now(tz=UTC),
        ended_at=None,
        status="stopped",
        language="pt",
        capture_mode="lecture",
    )
    await store.create_session(session)
    await store.add_segment(
        TranscriptSegment(
            id=new_id(),
            session_id=session.id,
            start_ms=12_000,
            end_ms=20_000,
            text="Dijkstra encontra o caminho mais curto em um grafo com pesos positivos.",
            language="pt",
        )
    )

    listed = await client.get("/chat", headers=auth())
    assert listed.status_code == 200
    assert listed.json() == []

    chunks: list[str] = []
    async with client.stream(
        "POST",
        "/chat/ask",
        headers=auth(),
        json={"message": "O que é Dijkstra nesta aula?", "session_id": session.id},
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line:
                chunks.append(line)

    payload = "\n".join(chunks)
    assert "data:" in payload
    assert "Dijkstra" in payload or "grafo" in payload.lower() or "Sobre:" in payload

    after = await client.get("/chat", headers=auth())
    assert after.status_code == 200
    assert len(after.json()) == 1
    chat_id = after.json()[0]["id"]
    detail = await client.get(f"/chat/{chat_id}", headers=auth())
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["citations"]
    assert messages[1]["citations"][0]["session_title"] == "Aula de grafos"


@pytest.mark.asyncio
async def test_chat_answers_in_ui_language_not_transcript_language(
    client: AsyncClient, app
) -> None:
    """Idioma da ferramenta manda na resposta; o idioma da transcrição não."""
    container = app.state.container
    container.settings.language = "pt"
    container.settings.ui_language = "en"
    llm = container.chat._llm

    async with client.stream(
        "POST", "/chat/ask", headers=auth(), json={"message": "O que é Dijkstra?"}
    ) as response:
        assert response.status_code == 200
        async for _ in response.aiter_lines():
            pass
    assert "Write every reply in English" in (llm.last_system or "")

    # O cliente pode mandar o idioma junto e ele ganha do settings do backend.
    async with client.stream(
        "POST",
        "/chat/ask",
        headers=auth(),
        json={"message": "O que é Dijkstra?", "ui_language": "es"},
    ) as response:
        assert response.status_code == 200
        async for _ in response.aiter_lines():
            pass
    assert "Write every reply in Spanish" in (llm.last_system or "")


async def _lecture(store: SqliteStore, title: str, text: str, *, days_ago: int = 0) -> Session:
    from datetime import timedelta

    session = Session(
        id=new_id(),
        title=title,
        started_at=datetime.now(tz=UTC) - timedelta(days=days_ago),
        ended_at=None,
        status="stopped",
        language="pt",
        capture_mode="lecture",
    )
    await store.create_session(session)
    await store.add_segment(
        TranscriptSegment(id=new_id(), session_id=session.id, start_ms=5_000, end_ms=9_000, text=text, language="pt")
    )
    return session


@pytest.mark.asyncio
async def test_chat_numbers_excerpts_and_applies_style(client: AsyncClient, app) -> None:
    """Cada trecho do contexto ganha [n]; o estilo escolhido entra no system prompt."""
    store: SqliteStore = app.state.container.store
    llm = app.state.container.chat._llm
    await _lecture(store, "Aula de limites", "O limite de uma função descreve o valor de que ela se aproxima.")
    async with client.stream(
        "POST",
        "/chat/ask",
        headers=auth(),
        json={"message": "O que é limite?", "style": "study", "grounded": True},
    ) as response:
        assert response.status_code == 200
        async for _ in response.aiter_lines():
            pass
    assert "[1] [search] Aula de limites" in llm.last_prompt
    assert "Reply mode: study" in (llm.last_system or "")
    assert "Sources only" in (llm.last_system or "")
    assert "[3]" in (llm.last_system or "")  # instrução de citar com número


@pytest.mark.asyncio
async def test_chat_solve_mode_targets_agent_and_fast_mode_trims_context(client: AsyncClient, app) -> None:
    store: SqliteStore = app.state.container.store
    llm = app.state.container.chat._llm
    for index in range(40):
        await _lecture(store, f"Reunião técnica {index}", f"O bug {index} aparece ao salvar o formulário " + "x" * 300)
    async with client.stream(
        "POST", "/chat/ask", headers=auth(), json={"message": "bug formulário", "style": "solve", "solve_target": "claude"}
    ) as response:
        async for _ in response.aiter_lines():
            pass
    assert "Reply mode: problem solver" in (llm.last_system or "")
    assert "Claude Code" in (llm.last_system or "")
    assert "```prompt" in (llm.last_system or "")
    full = len(llm.last_prompt)

    async with client.stream("POST", "/chat/ask", headers=auth(), json={"message": "bug formulário", "style": "fast"}) as response:
        async for _ in response.aiter_lines():
            pass
    assert "Reply mode: quick" in (llm.last_system or "")
    assert len(llm.last_prompt) < full


@pytest.mark.asyncio
async def test_chat_scope_limits_lectures(client: AsyncClient, app) -> None:
    """Escopo por período e por pessoa: só as gravações dentro dele entram no contexto."""
    store: SqliteStore = app.state.container.store
    llm = app.state.container.chat._llm
    old = await _lecture(store, "Aula antiga de derivadas", "A derivada mede a taxa de variação.", days_ago=40)
    new = await _lecture(store, "Aula nova de derivadas", "A derivada mede a inclinação da reta tangente.")
    person = (await client.post("/people", headers=auth(), json={"name": "Docente"})).json()
    await store.set_session_participants(old.id, [person["id"]])

    async with client.stream(
        "POST", "/chat/ask", headers=auth(), json={"message": "derivada", "scope": {"days": 7}}
    ) as response:
        async for _ in response.aiter_lines():
            pass
    assert "Aula nova de derivadas" in llm.last_prompt
    assert "Aula antiga de derivadas" not in llm.last_prompt
    assert "Lectures in scope" in llm.last_prompt

    async with client.stream(
        "POST", "/chat/ask", headers=auth(), json={"message": "derivada", "scope": {"person_id": person["id"]}}
    ) as response:
        async for _ in response.aiter_lines():
            pass
    assert "Aula antiga de derivadas" in llm.last_prompt
    assert "Aula nova de derivadas" not in llm.last_prompt
    assert new.id != old.id


@pytest.mark.asyncio
async def test_chat_images_reach_model_and_are_served(client: AsyncClient, app) -> None:
    import base64

    llm = app.state.container.chat._llm
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()
    async with client.stream(
        "POST",
        "/chat/ask",
        headers=auth(),
        json={"message": "O que está no quadro?", "images": [{"name": "quadro.png", "mime": "image/png", "data": png}]},
    ) as response:
        assert response.status_code == 200
        async for _ in response.aiter_lines():
            pass
    assert len(llm.last_images) == 1 and llm.last_images[0].startswith(b"\x89PNG")
    assert "attached 1 image" in llm.last_prompt
    chat_id = (await client.get("/chat", headers=auth())).json()[0]["id"]
    messages = (await client.get(f"/chat/{chat_id}", headers=auth())).json()["messages"]
    assert messages[0]["images"][0]["name"] == "quadro.png"
    served = await client.get(f"/chat/images/{messages[0]['images'][0]['id']}", headers=auth())
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"

    # Modelo sem visão: erro claro antes de tentar.
    llm.vision = False
    async with client.stream(
        "POST",
        "/chat/ask",
        headers=auth(),
        json={"message": "E agora?", "chat_id": chat_id, "images": [{"name": "q.png", "mime": "image/png", "data": png}]},
    ) as response:
        body = "".join([line async for line in response.aiter_lines()])
    assert "error" in body and "imagens" in body
    llm.vision = True


@pytest.mark.asyncio
async def test_chat_answer_exports_as_markdown_pdf_and_docx(client: AsyncClient, app) -> None:
    llm = app.state.container.chat._llm
    llm.text_reply = "## Resumo\n\n| Item | Nota |\n|---|---|\n| A | 10 |\n\n```chart\n{\"type\":\"bar\",\"labels\":[\"A\"],\"series\":[{\"name\":\"Nota\",\"values\":[10]}]}\n```\n- ponto **forte**"
    try:
        async with client.stream("POST", "/chat/ask", headers=auth(), json={"message": "Faça uma tabela"}) as response:
            async for _ in response.aiter_lines():
                pass
    finally:
        llm.text_reply = None
    chat_id = (await client.get("/chat", headers=auth())).json()[0]["id"]
    messages = (await client.get(f"/chat/{chat_id}", headers=auth())).json()["messages"]
    answer = messages[1]["id"]
    md = await client.get(f"/chat/{chat_id}/messages/{answer}/export?format=markdown", headers=auth())
    assert md.status_code == 200 and md.text.startswith("# Faça uma tabela")
    pdf = await client.get(f"/chat/{chat_id}/messages/{answer}/export?format=pdf", headers=auth())
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    docx = await client.get(f"/chat/{chat_id}/messages/{answer}/export?format=docx", headers=auth())
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    assert "filename=" in docx.headers["content-disposition"]
