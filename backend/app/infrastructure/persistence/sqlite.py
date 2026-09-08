from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import aiosqlite

from app.core.secrets import DPAPI_PREFIX, SECRET_SETTING_KEYS, protect_setting, unprotect_setting
from app.domain.models import (
    ActionItem,
    Person,
    Session,
    Summary,
    SummaryTopic,
    Tag,
    TranscriptSegment,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,
    language TEXT,
    capture_mode TEXT NOT NULL DEFAULT 'meeting',
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS segments (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    text TEXT NOT NULL,
    language TEXT,
    speaker_id TEXT,
    source TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_participants (
    session_id TEXT NOT NULL,
    person_id TEXT NOT NULL,
    PRIMARY KEY (session_id, person_id),
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (person_id) REFERENCES people(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    text,
    content='segments',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
    INSERT INTO segments_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
    INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', old.rowid, old.text);
END;

CREATE TRIGGER IF NOT EXISTS segments_au AFTER UPDATE ON segments BEGIN
    INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', old.rowid, old.text);
    INSERT INTO segments_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    highlights_json TEXT NOT NULL,
    decisions_json TEXT NOT NULL,
    action_items_json TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE
);

CREATE TABLE IF NOT EXISTS session_tags (
    session_id TEXT NOT NULL,
    tag_id TEXT NOT NULL,
    PRIMARY KEY (session_id, tag_id),
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (tag_id) REFERENCES tags(id)
);
"""


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _dump_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


class SqliteStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    async def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(SCHEMA)
            await _ensure_column(db, "segments", "speaker_id", "TEXT")
            await _ensure_column(db, "segments", "source", "TEXT")
            await _ensure_column(db, "summaries", "overview", "TEXT")
            await _ensure_column(db, "summaries", "topics_json", "TEXT")
            await _ensure_column(db, "summaries", "open_items_json", "TEXT")
            await _ensure_column(db, "summaries", "language", "TEXT")
            await _ensure_column(db, "summaries", "notes_markdown", "TEXT")
            await _ensure_column(db, "sessions", "capture_mode", "TEXT")
            await db.execute("DROP TABLE IF EXISTS memory_messages")
            await db.execute("DROP TABLE IF EXISTS memory_threads")
            await db.commit()

    async def create_session(self, session: Session) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO sessions (id, title, started_at, ended_at, status, language, capture_mode, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    session.id,
                    session.title,
                    _dump_dt(session.started_at),
                    _dump_dt(session.ended_at),
                    session.status,
                    session.language,
                    session.capture_mode,
                ),
            )
            await db.commit()

    async def get_session(self, session_id: str) -> Session | None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM sessions WHERE id = ? AND deleted_at IS NULL",
                (session_id,),
            )
            row = await cur.fetchone()
            return _row_to_session(row) if row else None

    async def list_sessions(self) -> list[Session]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM sessions WHERE deleted_at IS NULL ORDER BY started_at DESC"
            )
            rows = await cur.fetchall()
            return [_row_to_session(row) for row in rows]

    async def update_session(self, session: Session) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                UPDATE sessions
                SET title = ?, ended_at = ?, status = ?, language = ?, capture_mode = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (
                    session.title,
                    _dump_dt(session.ended_at),
                    session.status,
                    session.language,
                    session.capture_mode,
                    session.id,
                ),
            )
            await db.commit()

    async def delete_session(self, session_id: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM session_tags WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM session_participants WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM segments WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM summaries WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await db.commit()

    async def add_segment(self, segment: TranscriptSegment) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO segments (id, session_id, start_ms, end_ms, text, language, speaker_id, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    segment.id,
                    segment.session_id,
                    segment.start_ms,
                    segment.end_ms,
                    segment.text,
                    segment.language,
                    segment.speaker_id,
                    segment.source,
                ),
            )
            await db.commit()

    async def list_segments(self, session_id: str) -> list[TranscriptSegment]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM segments WHERE session_id = ? ORDER BY start_ms ASC",
                (session_id,),
            )
            rows = await cur.fetchall()
            return [_row_to_segment(row) for row in rows]

    async def search(self, query: str, session_id: str | None = None) -> list[TranscriptSegment]:
        sql = """
            SELECT segments.*
            FROM segments_fts
            JOIN segments ON segments.rowid = segments_fts.rowid
            JOIN sessions ON sessions.id = segments.session_id
            WHERE segments_fts MATCH ? AND sessions.deleted_at IS NULL
        """
        params: list[str] = [query]
        if session_id:
            sql += " AND segments.session_id = ?"
            params.append(session_id)
        sql += " ORDER BY segments.start_ms ASC LIMIT 200"
        try:
            async with aiosqlite.connect(self._path) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute(sql, params)
                rows = await cur.fetchall()
                return [_row_to_segment(row) for row in rows]
        except Exception:
            return await self._like_search(query, session_id)

    async def _like_search(self, query: str, session_id: str | None = None) -> list[TranscriptSegment]:
        sql = """
            SELECT segments.*
            FROM segments
            JOIN sessions ON sessions.id = segments.session_id
            WHERE segments.text LIKE ? AND sessions.deleted_at IS NULL
        """
        params: list[str] = [f"%{query}%"]
        if session_id:
            sql += " AND segments.session_id = ?"
            params.append(session_id)
        sql += " ORDER BY segments.start_ms ASC LIMIT 200"
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            return [_row_to_segment(row) for row in rows]

    async def save_summary(self, summary: Summary) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM summaries WHERE session_id = ?", (summary.session_id,))
            await db.execute(
                """
                INSERT INTO summaries
                (id, session_id, highlights_json, decisions_json, action_items_json, raw_text,
                 created_at, overview, topics_json, open_items_json, language, notes_markdown)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.id,
                    summary.session_id,
                    json.dumps(summary.highlights, ensure_ascii=False),
                    json.dumps(summary.decisions, ensure_ascii=False),
                    json.dumps(
                        [
                            {"text": i.text, "owner": i.owner, "due": i.due}
                            for i in summary.action_items
                        ],
                        ensure_ascii=False,
                    ),
                    summary.raw_text,
                    _dump_dt(summary.created_at),
                    summary.overview,
                    json.dumps(
                        [{"title": t.title, "points": t.points} for t in summary.topics],
                        ensure_ascii=False,
                    ),
                    json.dumps(summary.open_items, ensure_ascii=False),
                    summary.language,
                    summary.notes_markdown,
                ),
            )
            await db.commit()

    async def get_summary(self, session_id: str) -> Summary | None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM summaries WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            )
            row = await cur.fetchone()
            return _row_to_summary(row) if row else None

    async def get_setting(self, key: str) -> str | None:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = await cur.fetchone()
            stored = str(row[0]) if row else None
        if stored and key in SECRET_SETTING_KEYS and not stored.startswith(DPAPI_PREFIX):
            await self.set_setting(key, stored)
            return stored
        return unprotect_setting(key, stored)

    async def set_setting(self, key: str, value: str) -> None:
        stored = protect_setting(key, value)
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, stored),
            )
            await db.commit()

    async def list_people(self) -> list[Person]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT id, name FROM people ORDER BY name COLLATE NOCASE ASC")
            rows = await cur.fetchall()
            return [_row_to_person(row) for row in rows]

    async def get_person(self, person_id: str) -> Person | None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT id, name FROM people WHERE id = ?", (person_id,))
            row = await cur.fetchone()
            return _row_to_person(row) if row else None

    async def create_person(self, name: str) -> Person:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Nome vazio")
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id, name FROM people WHERE lower(name) = lower(?)",
                (cleaned,),
            )
            existing = await cur.fetchone()
            if existing:
                return _row_to_person(existing)
            person = Person(id=new_id(), name=cleaned)
            await db.execute("INSERT INTO people (id, name) VALUES (?, ?)", (person.id, person.name))
            await db.commit()
            return person

    async def delete_person(self, person_id: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE segments SET speaker_id = NULL WHERE speaker_id = ?",
                (person_id,),
            )
            await db.execute("DELETE FROM session_participants WHERE person_id = ?", (person_id,))
            await db.execute("DELETE FROM people WHERE id = ?", (person_id,))
            await db.commit()

    async def list_people_by_ids(self, person_ids: Sequence[str]) -> list[Person]:
        ids = [item for item in person_ids if item]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"SELECT id, name FROM people WHERE id IN ({placeholders})",
                ids,
            )
            rows = await cur.fetchall()
            by_id = {row["id"]: _row_to_person(row) for row in rows}
            return [by_id[item] for item in ids if item in by_id]

    async def list_session_participants(self, session_id: str) -> list[Person]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT people.id, people.name
                FROM session_participants
                JOIN people ON people.id = session_participants.person_id
                WHERE session_participants.session_id = ?
                ORDER BY people.name COLLATE NOCASE ASC
                """,
                (session_id,),
            )
            rows = await cur.fetchall()
            return [_row_to_person(row) for row in rows]

    async def set_session_participants(self, session_id: str, person_ids: Sequence[str]) -> None:
        unique: list[str] = []
        seen: set[str] = set()
        for item in person_ids:
            if not item or item in seen:
                continue
            seen.add(item)
            unique.append(item)
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM session_participants WHERE session_id = ?", (session_id,))
            await db.executemany(
                "INSERT INTO session_participants (session_id, person_id) VALUES (?, ?)",
                [(session_id, person_id) for person_id in unique],
            )
            await db.commit()

    async def get_segment(self, segment_id: str) -> TranscriptSegment | None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM segments WHERE id = ?", (segment_id,))
            row = await cur.fetchone()
            return _row_to_segment(row) if row else None

    async def set_segment_speaker(self, segment_id: str, speaker_id: str | None) -> TranscriptSegment | None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE segments SET speaker_id = ? WHERE id = ?",
                (speaker_id, segment_id),
            )
            await db.commit()
        return await self.get_segment(segment_id)

    async def save_segment(self, segment: TranscriptSegment) -> TranscriptSegment | None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                UPDATE segments
                SET text = ?, language = ?, speaker_id = ?, source = ?
                WHERE id = ?
                """,
                (segment.text, segment.language, segment.speaker_id, segment.source, segment.id),
            )
            await db.commit()
        return await self.get_segment(segment.id)

    async def save_summary_notes(self, session_id: str, notes_markdown: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE summaries SET notes_markdown = ? WHERE session_id = ?",
                (notes_markdown, session_id),
            )
            await db.commit()

    async def list_tags(self) -> list[Tag]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT id, name FROM tags ORDER BY name COLLATE NOCASE ASC")
            rows = await cur.fetchall()
            return [_row_to_tag(row) for row in rows]

    async def create_tag(self, name: str) -> Tag:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Nome vazio")
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id, name FROM tags WHERE lower(name) = lower(?)",
                (cleaned,),
            )
            existing = await cur.fetchone()
            if existing:
                return _row_to_tag(existing)
            tag = Tag(id=new_id(), name=cleaned)
            await db.execute("INSERT INTO tags (id, name) VALUES (?, ?)", (tag.id, tag.name))
            await db.commit()
            return tag

    async def delete_tag(self, tag_id: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM session_tags WHERE tag_id = ?", (tag_id,))
            await db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
            await db.commit()

    async def list_session_tags(self, session_id: str) -> list[Tag]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT tags.id, tags.name
                FROM session_tags
                JOIN tags ON tags.id = session_tags.tag_id
                WHERE session_tags.session_id = ?
                ORDER BY tags.name COLLATE NOCASE ASC
                """,
                (session_id,),
            )
            rows = await cur.fetchall()
            return [_row_to_tag(row) for row in rows]

    async def set_session_tags(self, session_id: str, tag_ids: Sequence[str]) -> list[Tag]:
        unique: list[str] = []
        for item in tag_ids:
            if item and item not in unique:
                unique.append(item)
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM session_tags WHERE session_id = ?", (session_id,))
            for tag_id in unique:
                await db.execute(
                    "INSERT OR IGNORE INTO session_tags (session_id, tag_id) VALUES (?, ?)",
                    (session_id, tag_id),
                )
            await db.commit()
        return await self.list_session_tags(session_id)

    async def tags_by_session_ids(self, session_ids: Sequence[str]) -> dict[str, list[Tag]]:
        result: dict[str, list[Tag]] = {item: [] for item in session_ids}
        ids = [item for item in session_ids if item]
        if not ids:
            return result
        placeholders = ",".join("?" for _ in ids)
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT session_tags.session_id, tags.id, tags.name
                FROM session_tags
                JOIN tags ON tags.id = session_tags.tag_id
                WHERE session_tags.session_id IN ({placeholders})
                ORDER BY tags.name COLLATE NOCASE ASC
                """,
                ids,
            )
            rows = await cur.fetchall()
        for row in rows:
            result.setdefault(str(row["session_id"]), []).append(_row_to_tag(row))
        return result


def new_id() -> str:
    return str(uuid4())


def _row_to_session(row: aiosqlite.Row) -> Session:
    keys = row.keys()
    mode = row["capture_mode"] if "capture_mode" in keys and row["capture_mode"] else "meeting"
    if mode not in {"dictation", "lecture", "meeting"}:
        mode = "meeting"
    return Session(
        id=row["id"],
        title=row["title"],
        started_at=_parse_dt(row["started_at"]) or datetime.now(tz=UTC),
        ended_at=_parse_dt(row["ended_at"]),
        status=row["status"],
        language=row["language"],
        capture_mode=mode,
    )


def _row_to_segment(row: aiosqlite.Row) -> TranscriptSegment:
    keys = row.keys()
    return TranscriptSegment(
        id=row["id"],
        session_id=row["session_id"],
        start_ms=int(row["start_ms"]),
        end_ms=int(row["end_ms"]),
        text=row["text"],
        language=row["language"],
        speaker_id=row["speaker_id"] if "speaker_id" in keys else None,
        source=row["source"] if "source" in keys else None,
    )


def _row_to_person(row: aiosqlite.Row) -> Person:
    return Person(id=row["id"], name=row["name"])


def _row_to_tag(row: aiosqlite.Row) -> Tag:
    return Tag(id=row["id"], name=row["name"])


async def _ensure_column(db: aiosqlite.Connection, table: str, name: str, decl: str) -> None:
    cur = await db.execute(f"PRAGMA table_info({table})")
    columns = [item[1] for item in await cur.fetchall()]
    if name not in columns:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def _row_to_summary(row: aiosqlite.Row) -> Summary:
    items_raw = json.loads(row["action_items_json"] or "[]")
    items = [
        ActionItem(
            text=str(item.get("text") or ""),
            owner=item.get("owner"),
            due=item.get("due"),
        )
        for item in items_raw
        if isinstance(item, dict)
    ]
    topics = [
        SummaryTopic(
            title=str(item.get("title") or ""),
            points=[str(point) for point in item.get("points") or []],
        )
        for item in json.loads(_column(row, "topics_json") or "[]")
        if isinstance(item, dict)
    ]
    return Summary(
        id=row["id"],
        session_id=row["session_id"],
        highlights=list(json.loads(row["highlights_json"] or "[]")),
        decisions=list(json.loads(row["decisions_json"] or "[]")),
        action_items=items,
        raw_text=row["raw_text"],
        created_at=_parse_dt(row["created_at"]) or datetime.now(tz=UTC),
        overview=_column(row, "overview") or "",
        topics=topics,
        open_items=list(json.loads(_column(row, "open_items_json") or "[]")),
        language=_column(row, "language"),
        notes_markdown=_column(row, "notes_markdown") or "",
    )


def _column(row: aiosqlite.Row, name: str) -> str | None:
    if name not in row.keys():
        return None
    value = row[name]
    return str(value) if value is not None else None
