from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.conftest import auth


@pytest.mark.asyncio
async def test_settings_persist_language_and_provider(client: AsyncClient) -> None:
    saved = await client.put(
        "/setup/settings",
        headers=auth(),
        json={
            "language": "pt",
            "provider": "openai",
            "asr_cloud_model": "gpt-4o-mini-transcribe",
            "asr_api_key": "sk-live-secret-key",
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["language"] == "pt"
    assert body["provider"] == "openai"
    assert body["asr_cloud_model"] == "gpt-4o-mini-transcribe"
    assert body["has_api_key"] is True
    assert body["api_key_hint"] == "-key"
    assert "asr_api_key" not in body

    listed = await client.get("/setup/settings", headers=auth())
    assert listed.json()["provider"] == "openai"

    cleared = await client.put(
        "/setup/settings",
        headers=auth(),
        json={"asr_api_key": ""},
    )
    assert cleared.status_code == 200
    assert cleared.json()["has_api_key"] is False
    assert cleared.json()["api_key_hint"] == ""


@pytest.mark.asyncio
async def test_api_key_is_not_plaintext_in_sqlite(client: AsyncClient, app) -> None:
    saved = await client.put(
        "/setup/settings",
        headers=auth(),
        json={"asr_api_key": "sk-live-secret-key"},
    )
    assert saved.status_code == 200
    import aiosqlite

    async with aiosqlite.connect(app.state.container.settings.db_path) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key = ?", ("asr_api_key",))
        row = await cur.fetchone()
    assert row is not None
    assert "sk-live-secret-key" not in str(row[0])
    stored = await app.state.container.store.get_setting("asr_api_key")
    assert stored == "sk-live-secret-key"


@pytest.mark.asyncio
async def test_settings_persist_recordings_dir(client: AsyncClient, app) -> None:
    folder = app.state.container.settings.data_dir / "gravacoes"
    saved = await client.put(
        "/setup/settings",
        headers=auth(),
        json={"recordings_dir": str(folder)},
    )
    assert saved.status_code == 200
    assert Path(saved.json()["recordings_dir"]) == folder.resolve()
    listed = await client.get("/setup/settings", headers=auth())
    assert Path(listed.json()["recordings_dir"]) == folder.resolve()


@pytest.mark.asyncio
async def test_people_crud_and_segment_speaker(client: AsyncClient, app) -> None:
    created = await client.post("/people", headers=auth(), json={"name": "Ana"})
    assert created.status_code == 201
    ana = created.json()
    assert ana["name"] == "Ana"

    listed = await client.get("/people", headers=auth())
    assert any(item["id"] == ana["id"] for item in listed.json())

    started = await client.post(
        "/capture/start",
        headers=auth(),
        json={"mic_only": True, "participant_ids": [ana["id"]]},
    )
    assert started.status_code == 200
    session_id = started.json()["session_id"]
    await client.post("/capture/stop", headers=auth())

    from app.domain.models import TranscriptSegment
    from app.infrastructure.persistence.sqlite import new_id

    segment = TranscriptSegment(
        id=new_id(),
        session_id=session_id,
        start_ms=0,
        end_ms=1000,
        text="Olá",
        language="pt",
    )
    await app.state.container.store.add_segment(segment)

    patched = await client.patch(
        f"/sessions/{session_id}/segments/{segment.id}",
        headers=auth(),
        json={"speaker_id": ana["id"]},
    )
    assert patched.status_code == 200
    assert patched.json()["speaker_id"] == ana["id"]

    detail = await client.get(f"/sessions/{session_id}", headers=auth())
    assert detail.json()["participants"][0]["name"] == "Ana"
    assert detail.json()["segments"][0]["speaker_id"] == ana["id"]

    async def fake_json(prompt: str) -> str:
        del prompt
        return '{"assignments": []}'

    app.state.container.speakers._llm.generate_json = fake_json  # type: ignore[method-assign]

    async def ready_status():
        from app.domain.models import SetupComponentStatus

        return SetupComponentStatus(status="ready", progress=100, message="ok")

    app.state.container.llm.status_component = ready_status  # type: ignore[method-assign]
    assigned = await client.post(f"/sessions/{session_id}/speakers/assign", headers=auth())
    assert assigned.status_code == 200

    deleted = await client.delete(f"/people/{ana['id']}", headers=auth())
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_patch_segment_text(client: AsyncClient, app) -> None:
    ana = (await client.post("/people", headers=auth(), json={"name": "Ana"})).json()
    started = await client.post(
        "/capture/start",
        headers=auth(),
        json={"mic_only": True, "participant_ids": [ana["id"]]},
    )
    session_id = started.json()["session_id"]
    await client.post("/capture/stop", headers=auth())

    from app.domain.models import TranscriptSegment
    from app.infrastructure.persistence.sqlite import new_id

    segment = TranscriptSegment(
        id=new_id(),
        session_id=session_id,
        start_ms=0,
        end_ms=1000,
        text="Olá",
        language="pt",
        speaker_id=ana["id"],
    )
    await app.state.container.store.add_segment(segment)
    patched = await client.patch(
        f"/sessions/{session_id}/segments/{segment.id}",
        headers=auth(),
        json={"text": "Texto editado"},
    )
    assert patched.status_code == 200
    assert patched.json()["text"] == "Texto editado"
    assert patched.json()["speaker_id"] == ana["id"]
    assert patched.json()["speaker_name"] == "Ana"


@pytest.mark.asyncio
async def test_assign_heuristic_single_person_and_forward(client: AsyncClient, app) -> None:
    ana = (await client.post("/people", headers=auth(), json={"name": "Ana"})).json()
    started = await client.post(
        "/capture/start",
        headers=auth(),
        json={"mic_only": True, "participant_ids": [ana["id"]]},
    )
    session_id = started.json()["session_id"]
    await client.post("/capture/stop", headers=auth())

    from app.domain.models import TranscriptSegment
    from app.infrastructure.persistence.sqlite import new_id

    first = TranscriptSegment(
        id=new_id(),
        session_id=session_id,
        start_ms=0,
        end_ms=1000,
        text="Olá",
        language="pt",
    )
    second = TranscriptSegment(
        id=new_id(),
        session_id=session_id,
        start_ms=2000,
        end_ms=3000,
        text="Seguindo",
        language="pt",
    )
    await app.state.container.store.add_segment(first)
    await app.state.container.store.add_segment(second)

    assigned = await client.post(f"/sessions/{session_id}/speakers/assign", headers=auth())
    assert assigned.status_code == 200
    body = assigned.json()
    assert all(item["speaker_id"] == ana["id"] for item in body)
    assert all(item["speaker_name"] == "Ana" for item in body)
