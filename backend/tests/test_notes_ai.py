from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.application.notes import expand_note
from app.application.summarize import user_notes_instructions
from app.domain.models import Session, TranscriptSegment, UserNote
from app.infrastructure.persistence.sqlite import SqliteStore, new_id
from tests.conftest import auth


class _Llm:
    def __init__(self) -> None:
        self.prompt = ""
        self.system = ""

    async def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        self.prompt, self.system = prompt, system or ""
        return "  Ana disse que o plano anual ficou caro.  "


def test_note_kinds_steer_the_summary() -> None:
    text = user_notes_instructions([(61_000, "preço caro", "question"), (90_000, "fechar piloto", "decision"), (5_000, "livre", None)])
    assert "[01:01] [DÚVIDA] preço caro" in text
    assert "[01:30] [DECISÃO] fechar piloto" in text
    assert "[00:05] livre" in text
    assert "[TAREFA] em \"action_items\"" in text


async def test_expand_note_reads_only_the_moment_around_it(tmp_path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    await store.initialize()
    session = Session(id=new_id(), title="Venda", started_at=datetime.now(tz=UTC) - timedelta(hours=1), ended_at=None, status="stopped")
    await store.create_session(session)
    ana = await store.create_person("Ana")
    for at, text, who in [(10_000, "bom dia a todos", None), (300_000, "achei caro o anual", ana.id), (320_000, "dá para parcelar?", None), (900_000, "tchau", None)]:
        await store.add_segment(
            TranscriptSegment(id=new_id(), session_id=session.id, start_ms=at, end_ms=at + 2_000, text=text, speaker_id=who)
        )
    note = UserNote(id=new_id(), session_id=session.id, at_ms=330_000, text="preço", created_at=datetime.now(tz=UTC), kind="question")
    llm = _Llm()
    result = await expand_note(llm, store, note, "en")
    assert result == "Ana disse que o plano anual ficou caro."
    assert "Ana: achei caro o anual" in llm.prompt
    assert "dá para parcelar?" in llm.prompt
    assert "bom dia" not in llm.prompt and "tchau" not in llm.prompt
    assert "Marked as: question" in llm.prompt
    assert "Write in English" in llm.system


async def test_note_kind_endpoints(client: AsyncClient, app) -> None:
    store = app.state.container.store
    session = Session(id=new_id(), title="S", started_at=datetime.now(tz=UTC), ended_at=None, status="recording")
    await store.create_session(session)
    created = await client.post(f"/sessions/{session.id}/notes", headers=auth(), json={"text": "fechar piloto", "kind": "decision"})
    assert created.json()["kind"] == "decision"
    note_id = created.json()["id"]
    retagged = await client.patch(f"/sessions/{session.id}/notes/{note_id}", headers=auth(), json={"kind": "task"})
    assert retagged.json()[0]["kind"] == "task" and retagged.json()[0]["text"] == "fechar piloto"
    cleared = await client.patch(f"/sessions/{session.id}/notes/{note_id}", headers=auth(), json={"kind": None})
    assert cleared.json()[0]["kind"] is None
    bad = await client.post(f"/sessions/{session.id}/notes", headers=auth(), json={"text": "x", "kind": "random"})
    assert bad.status_code == 422


async def test_auto_summary_after_stop(app) -> None:
    from types import SimpleNamespace

    from app.api.v1.endpoints.capture import auto_summarize

    container = app.state.container
    store = container.store
    session = Session(id=new_id(), title="Daily", started_at=datetime.now(tz=UTC), ended_at=None, status="stopped")
    await store.create_session(session)
    await store.add_segment(TranscriptSegment(id=new_id(), session_id=session.id, start_ms=0, end_ms=900, text="vamos fechar"))
    queue = await container.bus.subscribe()

    async def not_ready():
        return SimpleNamespace(summarize_ready=False)

    container.setup.status = not_ready
    await auto_summarize(container, session.id)
    assert queue.get_nowait() == {"type": "summary", "status": "skipped", "reason": "engine", "session_id": session.id}
    assert await store.get_summary(session.id) is None

    async def ready():
        return SimpleNamespace(summarize_ready=True)

    container.setup.status = ready
    await auto_summarize(container, session.id)
    events = [queue.get_nowait()["status"] for _ in range(2)]
    assert events == ["start", "done"]
    assert await store.get_summary(session.id) is not None
    # Já tem ata: não gera de novo sozinha.
    await auto_summarize(container, session.id)
    assert queue.get_nowait()["type"] == "tasks"
    assert queue.empty()

    await store.set_setting("auto_summary", "0")
    other = Session(id=new_id(), title="X", started_at=datetime.now(tz=UTC), ended_at=None, status="stopped")
    await store.create_session(other)
    await store.add_segment(TranscriptSegment(id=new_id(), session_id=other.id, start_ms=0, end_ms=900, text="oi"))
    await auto_summarize(container, other.id)
    assert await store.get_summary(other.id) is None
