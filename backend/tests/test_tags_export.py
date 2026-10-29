from __future__ import annotations

from datetime import UTC, datetime
from wave import open as open_wav

import pytest
from httpx import AsyncClient

from app.domain.models import Session, TranscriptSegment
from app.infrastructure.persistence.sqlite import new_id
from tests.conftest import auth


def _write_wav(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open_wav(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(b"\x00\x00" * 1600)


@pytest.mark.asyncio
async def test_tags_and_session_filter(client: AsyncClient, app) -> None:
    store = app.state.container.store
    aula = await client.post("/tags", headers=auth(), json={"name": "Aulas"})
    clientes = await client.post("/tags", headers=auth(), json={"name": "Clientes"})
    assert aula.status_code == 201
    assert clientes.status_code == 201
    aula_id = aula.json()["id"]

    session = Session(
        id=new_id(),
        title="Aula de segunda",
        started_at=datetime.now(tz=UTC),
        ended_at=None,
        status="stopped",
        language="pt",
    )
    other = Session(
        id=new_id(),
        title="Cliente sexta",
        started_at=datetime.now(tz=UTC),
        ended_at=None,
        status="stopped",
        language="pt",
    )
    await store.create_session(session)
    await store.create_session(other)
    assigned = await client.put(
        f"/sessions/{session.id}/tags",
        headers=auth(),
        json={"tag_ids": [aula_id]},
    )
    assert assigned.status_code == 200
    assert assigned.json()[0]["name"] == "Aulas"

    listed = await client.get("/sessions", headers=auth(), params={"tag_id": aula_id})
    titles = [item["title"] for item in listed.json()]
    assert titles == ["Aula de segunda"]

    deleted = await client.delete(f"/tags/{aula_id}", headers=auth())
    assert deleted.status_code == 204

    remaining_tags = await client.get("/tags", headers=auth())
    assert [item["name"] for item in remaining_tags.json()] == ["Clientes"]

    session_after_delete = await client.get(f"/sessions/{session.id}", headers=auth())
    assert session_after_delete.status_code == 200
    assert session_after_delete.json()["session"]["tags"] == []


@pytest.mark.asyncio
async def test_export_pdf_and_docx_and_audio(client: AsyncClient, app) -> None:
    store = app.state.container.store
    session = Session(
        id=new_id(),
        title="Reunião de prazos",
        started_at=datetime.now(tz=UTC),
        ended_at=None,
        status="stopped",
        language="pt",
    )
    await store.create_session(session)
    await store.add_segment(
        TranscriptSegment(
            id=new_id(),
            session_id=session.id,
            start_ms=0,
            end_ms=2000,
            text="Vamos entregar na sexta",
            language="pt",
        )
    )
    pdf = await client.get(f"/sessions/{session.id}/export", headers=auth(), params={"format": "pdf"})
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    docx = await client.get(f"/sessions/{session.id}/export", headers=auth(), params={"format": "docx"})
    assert docx.status_code == 200
    assert docx.content[:2] == b"PK"

    missing = await client.get(f"/sessions/{session.id}/audio", headers=auth())
    assert missing.status_code == 404

    path = app.state.container.settings.resolve_recordings_dir() / f"{session.id}.wav"
    _write_wav(path)
    audio = await client.get(f"/sessions/{session.id}/audio", headers=auth())
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/wav")

    detail = await client.get(f"/sessions/{session.id}", headers=auth())
    assert detail.json()["session"]["has_audio"] is True


def test_parse_markdown_blocks_from_minutes() -> None:
    from app.application.export import parse_markdown

    blocks = parse_markdown("# Título\n\n## Resumo\n\nUma frase.\nOutra.\n\n### Assunto\n- Ponto `01:10`\n  - Sub\n- [ ] Tarefa (02:00)\n")
    assert [(b.kind, b.level) for b in blocks] == [("title", 0), ("h2", 0), ("p", 0), ("h3", 0), ("li", 0), ("li", 1), ("li", 0)]
    assert blocks[2].text == "Uma frase. Outra."
    assert blocks[6].text == "Tarefa (02:00)"


async def test_pdf_and_docx_exports_render_minutes_markdown(client, app) -> None:
    from datetime import UTC, datetime

    from app.domain.models import ActionItem, Session, Summary, TranscriptSegment
    from app.infrastructure.persistence.sqlite import new_id
    from tests.conftest import auth

    store = app.state.container.store
    session = Session(id=new_id(), title="Reunião 29/10/2026 17:08", started_at=datetime.now(tz=UTC), ended_at=None, status="stopped")
    await store.create_session(session)
    await store.add_segment(TranscriptSegment(id=new_id(), session_id=session.id, start_ms=1_000, end_ms=3_000, text="Olá <todos> & bem-vindos."))
    await store.save_summary(
        Summary(
            id=new_id(), session_id=session.id, highlights=[], decisions=["Fechar o piloto (00:01)"],
            action_items=[ActionItem(text="Enviar proposta", owner="Ana")], raw_text="{}", created_at=datetime.now(tz=UTC),
            notes_markdown="# Reunião\n\n## Resumo\n\nTexto **forte**.\n\n### Assunto\n- Ponto `00:01`\n",
        )
    )
    pdf = await client.get(f"/sessions/{session.id}/export?format=pdf", headers=auth())
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert "filename=" in pdf.headers["content-disposition"]
    docx = await client.get(f"/sessions/{session.id}/export?format=docx", headers=auth())
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
