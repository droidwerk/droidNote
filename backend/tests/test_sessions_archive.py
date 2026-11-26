from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.application.retention import RetentionService
from app.application.sessions import OLD_DIRS_KEY
from app.core.config import session_recording_path
from app.domain.models import Chat, ChatCitation, ChatMessage, Session, TaskItem, TranscriptSegment, UserNote
from app.infrastructure.persistence.sqlite import SqliteStore, new_id
from tests.conftest import auth


async def _make(store: SqliteStore, title: str, text: str = "orçamento aprovado") -> Session:
    session = Session(id=new_id(), title=title, started_at=datetime.now(tz=UTC), ended_at=None, status="stopped")
    await store.create_session(session)
    await store.add_segment(
        TranscriptSegment(id=new_id(), session_id=session.id, start_ms=0, end_ms=900, text=text)
    )
    return session


async def _bulk(client: AsyncClient, action: str, ids: list[str]) -> dict:
    res = await client.post("/sessions/bulk", headers=auth(), json={"ids": ids, "action": action})
    assert res.status_code == 200, res.text
    return res.json()


async def _ids(client: AsyncClient, scope: str | None = None) -> list[str]:
    params = {"scope": scope} if scope else {}
    res = await client.get("/sessions", headers=auth(), params=params)
    assert res.status_code == 200
    return [item["id"] for item in res.json()]


@pytest.mark.asyncio
async def test_archive_trash_restore_scopes_and_counts(client: AsyncClient, app) -> None:
    store: SqliteStore = app.state.container.store
    a, b, c = [await _make(store, name) for name in ("A", "B", "C")]

    out = await _bulk(client, "archive", [a.id, b.id, "nope", a.id])
    assert out == {"done": [a.id, b.id], "failed": [{"id": "nope", "reason": "missing"}]}
    assert await _ids(client) == [c.id]
    assert set(await _ids(client, "archived")) == {a.id, b.id}

    await _bulk(client, "trash", [b.id])
    assert await _ids(client, "archived") == [a.id]
    assert await _ids(client, "trash") == [b.id]
    counts = await client.get("/sessions/counts", headers=auth())
    assert counts.json() == {"archived": 1, "trash": 1}

    assert (await client.get(f"/sessions/{b.id}", headers=auth())).status_code == 404
    trashed = await client.get(f"/sessions/{b.id}", headers=auth(), params={"include": "trash"})
    assert trashed.status_code == 200
    assert trashed.json()["session"]["deleted_at"] is not None
    assert trashed.json()["session"]["archived_at"] is not None
    # Arquivar o que está na lixeira não vale; repetir trash/restore é inofensivo.
    assert (await _bulk(client, "archive", [b.id]))["failed"] == [{"id": b.id, "reason": "missing"}]
    assert (await _bulk(client, "trash", [b.id]))["done"] == [b.id]

    await _bulk(client, "restore", [b.id])
    await _bulk(client, "unarchive", [a.id, b.id])
    assert set(await _ids(client)) == {a.id, b.id, c.id}
    assert (await client.get("/sessions/counts", headers=auth())).json() == {"archived": 0, "trash": 0}


@pytest.mark.asyncio
async def test_delete_moves_to_trash_and_purge_removes_audio(client: AsyncClient, app) -> None:
    container = app.state.container
    store: SqliteStore = container.store
    session = await _make(store, "Com áudio")
    wav = session_recording_path(container.settings, session.id)
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" * 20)
    sidecar = wav.with_suffix(".wav.part")
    sidecar.write_bytes(b"x")

    assert (await client.delete(f"/sessions/{session.id}", headers=auth())).status_code == 204
    assert await store.get_session(session.id) is None
    assert len(await store.list_segments(session.id)) == 1
    assert wav.exists()

    live = await _make(store, "Fora da lixeira")
    out = await _bulk(client, "purge", [live.id, session.id])
    assert out == {"done": [session.id], "failed": [{"id": live.id, "reason": "not_trashed"}]}
    assert await store.get_session(session.id, include_trash=True) is None
    assert await store.list_segments(session.id) == []
    assert not wav.exists() and not sidecar.exists()

    # ?purge=true não pula a lixeira: fora dela é 409 not_trashed, como no bulk.
    refused = await client.delete(f"/sessions/{live.id}", headers=auth(), params={"purge": "true"})
    assert refused.status_code == 409 and refused.json()["detail"] == "not_trashed"
    assert await store.get_session(live.id) is not None
    assert (await client.delete(f"/sessions/{live.id}", headers=auth())).status_code == 204
    assert (await client.delete(f"/sessions/{live.id}", headers=auth(), params={"purge": "true"})).status_code == 204
    assert await store.get_session(live.id, include_trash=True) is None
    assert (await client.delete(f"/sessions/{live.id}", headers=auth())).status_code == 404


@pytest.mark.asyncio
async def test_live_recording_is_refused(client: AsyncClient, app) -> None:
    container = app.state.container
    session = await _make(container.store, "Gravando")
    container.capture.state.recording = True
    container.capture.state.session_id = session.id
    try:
        out = await _bulk(client, "trash", [session.id])
        assert out == {"done": [], "failed": [{"id": session.id, "reason": "live"}]}
        res = await client.delete(f"/sessions/{session.id}", headers=auth())
        assert res.status_code == 409
    finally:
        container.capture.state.recording = False
        container.capture.state.session_id = None
    assert await container.store.get_session(session.id) is not None


@pytest.mark.asyncio
async def test_search_keeps_archived_and_hides_trash(client: AsyncClient, app) -> None:
    store: SqliteStore = app.state.container.store
    archived = await _make(store, "Arquivada", "zebralunar arquivada")
    trashed = await _make(store, "Lixo", "zebralunar lixeira")
    await store.add_user_note(
        UserNote(id=new_id(), session_id=trashed.id, at_ms=0, text="zebralunar nota", created_at=datetime.now(tz=UTC))
    )
    await _bulk(client, "archive", [archived.id])
    await _bulk(client, "trash", [trashed.id])

    found = (await client.get("/sessions/search", headers=auth(), params={"q": "zebralunar"})).json()
    assert {item["session_id"] for item in found["segments"]} == {archived.id}
    assert found["notes"] == []
    # O chat lê `list_sessions()` e `search`: arquivada entra, lixeira não.
    assert {item.id for item in await store.list_sessions()} >= {archived.id}
    assert trashed.id not in {item.id for item in await store.list_sessions()}


@pytest.mark.asyncio
async def test_bulk_validation_and_auth(client: AsyncClient) -> None:
    bad = await client.post("/sessions/bulk", headers=auth(), json={"ids": ["x"], "action": "nuke"})
    assert bad.status_code == 422
    empty = await client.post("/sessions/bulk", headers=auth(), json={"ids": [], "action": "trash"})
    assert empty.status_code == 422
    scope = await client.get("/sessions", headers=auth(), params={"scope": "everything"})
    assert scope.status_code == 422
    anon = await client.post("/sessions/bulk", json={"ids": ["x"], "action": "trash"})
    assert anon.status_code == 401


@pytest.mark.asyncio
async def test_retention_purges_trash_after_30_days(tmp_path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    await store.initialize()
    folder = tmp_path / "rec"
    folder.mkdir()
    old = await _make(store, "Velha")
    recent = await _make(store, "Recente")
    now = datetime.now(tz=UTC)
    await store.set_session_deleted(old.id, now - timedelta(days=31))
    await store.set_session_deleted(recent.id, now - timedelta(days=29))
    for session in (old, recent):
        (folder / f"{session.id}.wav").write_bytes(b"RIFF")
    service = RetentionService(store, lambda session_id: folder / f"{session_id}.wav")

    assert (await service.run(dry_run=True)).trash_purged == 1
    assert (folder / f"{old.id}.wav").exists()
    assert (await service.run()).trash_purged == 1
    assert await store.get_session(old.id, include_trash=True) is None
    assert not (folder / f"{old.id}.wav").exists()
    assert await store.get_session(recent.id, include_trash=True) is not None
    assert (folder / f"{recent.id}.wav").exists()


@pytest.mark.asyncio
async def test_archived_at_migration_is_idempotent(tmp_path) -> None:
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT NOT NULL, started_at TEXT NOT NULL,"
            " ended_at TEXT, status TEXT NOT NULL, language TEXT, deleted_at TEXT)"
        )
        db.execute("INSERT INTO sessions VALUES ('s1', 'Antiga', '2026-01-01T00:00:00+00:00', NULL, 'stopped', NULL, NULL)")
    store = SqliteStore(path)
    await store.initialize()
    await store.initialize()
    session = await store.get_session("s1")
    assert session is not None and session.archived_at is None
    assert await store.session_counts() == {"archived": 0, "trash": 0}


@pytest.mark.asyncio
async def test_purge_busy_file_keeps_rows(client: AsyncClient, app, monkeypatch) -> None:
    from pathlib import Path

    container = app.state.container
    store: SqliteStore = container.store
    session = await _make(store, "Presa")
    wav = session_recording_path(container.settings, session.id)
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF" * 20)
    await store.set_session_deleted(session.id, datetime.now(tz=UTC) - timedelta(days=31))

    def locked(self, missing_ok=False):  # o Windows segura o .wav
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "unlink", locked)
    assert (await _bulk(client, "purge", [session.id]))["failed"] == [{"id": session.id, "reason": "busy"}]
    res = await client.delete(f"/sessions/{session.id}", headers=auth(), params={"purge": "true"})
    assert res.status_code == 409 and res.json()["detail"] == "busy"
    service = RetentionService(store, lambda session_id: session_recording_path(container.settings, session_id))
    assert (await service.run()).trash_purged == 0
    assert await store.get_session(session.id, include_trash=True) is not None
    assert len(await store.list_segments(session.id)) == 1


@pytest.mark.asyncio
async def test_purge_drops_chat_citations_and_old_folder_audio(client: AsyncClient, app, tmp_path) -> None:
    container = app.state.container
    store: SqliteStore = container.store
    gone = await _make(store, "Some")
    kept = await _make(store, "Fica")
    now = datetime.now(tz=UTC)
    await store.save_chat(Chat(id="c1", title="Chat", created_at=now, updated_at=now))
    cites = [
        ChatCitation(session_id=gone.id, session_title="Some", excerpt="segredo da reunião"),
        ChatCitation(session_id=kept.id, session_title="Fica", excerpt="pode ficar"),
        ChatCitation(session_id="", session_title="", document_id="d1", document_name="doc.pdf"),
    ]
    await store.add_chat_message(
        ChatMessage(id="m1", chat_id="c1", role="assistant", content="ok", created_at=now, citations=cites)
    )
    old = tmp_path / "old-rec"
    old.mkdir()
    (old / f"{gone.id}.wav").write_bytes(b"RIFF")
    await store.set_setting(OLD_DIRS_KEY, f'["{old.as_posix()}"]')

    await _bulk(client, "trash", [gone.id])
    assert (await _bulk(client, "purge", [gone.id]))["done"] == [gone.id]
    left = (await store.list_chat_messages("c1"))[0].citations
    assert [(item.session_id, item.document_id) for item in left] == [(kept.id, None), ("", "d1")]
    assert not (old / f"{gone.id}.wav").exists()


@pytest.mark.asyncio
async def test_trashed_session_routes_and_tasks_hide_it(client: AsyncClient, app) -> None:
    store: SqliteStore = app.state.container.store
    trashed = await _make(store, "Lixo")
    await store.save_task(
        TaskItem(id=new_id(), text="tarefa da lixeira", session_id=trashed.id, created_at=datetime.now(tz=UTC))
    )
    assert any(item["session_id"] == trashed.id for item in (await client.get("/tasks", headers=auth())).json())
    await _bulk(client, "trash", [trashed.id])
    for path in ("audio", "export", "export?format=docx", "search?q=orçamento"):
        assert (await client.get(f"/sessions/{trashed.id}/{path}", headers=auth())).status_code == 404, path
    assert all(item["session_id"] != trashed.id for item in (await client.get("/tasks", headers=auth())).json())
