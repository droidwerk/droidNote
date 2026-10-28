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
    Chat,
    ChatCitation,
    ChatMessage,
    NoteTemplate,
    Person,
    Session,
    Summary,
    SummaryTopic,
    Tag,
    TaskItem,
    TranscriptSegment,
    UserNote,
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

CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    focus_session_id TEXT
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES chats(id)
);

CREATE TABLE IF NOT EXISTS segment_voices (
    segment_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    dim INTEGER NOT NULL,
    embedding BLOB NOT NULL,
    frames BLOB NOT NULL,
    frame_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS session_voices (
    session_id TEXT NOT NULL,
    cluster TEXT NOT NULL,
    person_id TEXT,
    PRIMARY KEY (session_id, cluster)
);

CREATE TABLE IF NOT EXISTS session_notes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    at_ms INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    body TEXT NOT NULL,
    capture_mode TEXT,
    builtin INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    text TEXT NOT NULL,
    owner TEXT,
    due TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    done_at TEXT,
    origin TEXT NOT NULL DEFAULT 'ai',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS voiceprints (
    person_id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    embedding BLOB NOT NULL,
    samples INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_segments_session ON segments(session_id, start_ms);
CREATE INDEX IF NOT EXISTS idx_segment_voices_session ON segment_voices(session_id);
CREATE INDEX IF NOT EXISTS idx_session_notes_session ON session_notes(session_id, at_ms);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
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
            await _ensure_column(db, "sessions", "template_id", "TEXT")
            await _ensure_column(db, "sessions", "transcript_purged_at", "TEXT")
            await _ensure_column(db, "segments", "speaker_cluster", "TEXT")
            await _ensure_column(db, "segments", "speaker_confidence", "REAL")
            await _ensure_column(db, "segments", "speaker_locked", "INTEGER NOT NULL DEFAULT 0")
            await db.executescript(INDEXES)
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("DROP TABLE IF EXISTS memory_messages")
            await db.execute("DROP TABLE IF EXISTS memory_threads")
            await db.commit()

    async def create_session(self, session: Session) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO sessions (id, title, started_at, ended_at, status, language, capture_mode, template_id, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    session.id,
                    session.title,
                    _dump_dt(session.started_at),
                    _dump_dt(session.ended_at),
                    session.status,
                    session.language,
                    session.capture_mode,
                    session.template_id,
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
                SET title = ?, ended_at = ?, status = ?, language = ?, capture_mode = ?, template_id = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (
                    session.title,
                    _dump_dt(session.ended_at),
                    session.status,
                    session.language,
                    session.capture_mode,
                    session.template_id,
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
            await db.execute("DELETE FROM segment_voices WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM session_voices WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM session_notes WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM tasks WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await db.commit()

    async def add_segment(self, segment: TranscriptSegment) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO segments (id, session_id, start_ms, end_ms, text, language, speaker_id, source,
                                      speaker_cluster, speaker_confidence, speaker_locked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    segment.speaker_cluster,
                    segment.speaker_confidence,
                    1 if segment.speaker_locked else 0,
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
            await db.execute("UPDATE session_voices SET person_id = NULL WHERE person_id = ?", (person_id,))
            await db.execute("DELETE FROM voiceprints WHERE person_id = ?", (person_id,))
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
                SET text = ?, language = ?, speaker_id = ?, source = ?,
                    speaker_cluster = ?, speaker_confidence = ?, speaker_locked = ?
                WHERE id = ?
                """,
                (
                    segment.text,
                    segment.language,
                    segment.speaker_id,
                    segment.source,
                    segment.speaker_cluster,
                    segment.speaker_confidence,
                    1 if segment.speaker_locked else 0,
                    segment.id,
                ),
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

    async def list_chats(self) -> list[Chat]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM chats ORDER BY updated_at DESC"
            )
            rows = await cur.fetchall()
            return [_row_to_chat(row) for row in rows]

    async def get_chat(self, chat_id: str) -> Chat | None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,))
            row = await cur.fetchone()
            return _row_to_chat(row) if row else None

    async def save_chat(self, chat: Chat) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO chats (id, title, created_at, updated_at, focus_session_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    updated_at = excluded.updated_at,
                    focus_session_id = excluded.focus_session_id
                """,
                (
                    chat.id,
                    chat.title,
                    _dump_dt(chat.created_at),
                    _dump_dt(chat.updated_at),
                    chat.focus_session_id,
                ),
            )
            await db.commit()

    async def delete_chat(self, chat_id: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM chat_messages WHERE chat_id = ?", (chat_id,))
            await db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            await db.commit()

    async def list_chat_messages(self, chat_id: str) -> list[ChatMessage]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM chat_messages WHERE chat_id = ? ORDER BY created_at ASC",
                (chat_id,),
            )
            rows = await cur.fetchall()
            return [_row_to_chat_message(row) for row in rows]

    async def add_chat_message(self, message: ChatMessage) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO chat_messages (id, chat_id, role, content, citations_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.chat_id,
                    message.role,
                    message.content,
                    json.dumps(
                        [
                            {
                                "session_id": item.session_id,
                                "session_title": item.session_title,
                                "segment_id": item.segment_id,
                                "start_ms": item.start_ms,
                                "excerpt": item.excerpt,
                            }
                            for item in message.citations
                        ],
                        ensure_ascii=False,
                    ),
                    _dump_dt(message.created_at),
                ),
            )
            await db.commit()

    async def get_segments_by_ids(self, ids: Sequence[str]) -> list[TranscriptSegment]:
        wanted = [item for item in ids if item]
        if not wanted:
            return []
        placeholders = ",".join("?" for _ in wanted)
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"SELECT * FROM segments WHERE id IN ({placeholders})",
                wanted,
            )
            rows = await cur.fetchall()
            mapped = [_row_to_segment(row) for row in rows]
            by_id = {item.id: item for item in mapped}
            return [by_id[item] for item in wanted if item in by_id]

    # --- Notas do usuário ----------------------------------------------------

    async def add_user_note(self, note: UserNote) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO session_notes (id, session_id, at_ms, text, created_at) VALUES (?, ?, ?, ?, ?)",
                (note.id, note.session_id, note.at_ms, note.text, _dump_dt(note.created_at)),
            )
            await db.commit()

    async def list_user_notes(self, session_id: str) -> list[UserNote]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM session_notes WHERE session_id = ? ORDER BY at_ms ASC, created_at ASC",
                (session_id,),
            )
            rows = await cur.fetchall()
        return [
            UserNote(
                id=row["id"],
                session_id=row["session_id"],
                at_ms=int(row["at_ms"]),
                text=row["text"],
                created_at=_parse_dt(row["created_at"]) or datetime.now(tz=UTC),
            )
            for row in rows
        ]

    async def update_user_note(self, session_id: str, note_id: str, text: str) -> bool:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "UPDATE session_notes SET text = ? WHERE id = ? AND session_id = ?",
                (text, note_id, session_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def delete_user_note(self, session_id: str, note_id: str) -> bool:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "DELETE FROM session_notes WHERE id = ? AND session_id = ?", (note_id, session_id)
            )
            await db.commit()
            return cur.rowcount > 0

    # --- Templates e receitas -------------------------------------------------

    async def list_templates(self, kind: str | None = None) -> list[NoteTemplate]:
        sql = "SELECT * FROM templates"
        params: list[str] = []
        if kind:
            sql += " WHERE kind = ?"
            params.append(kind)
        sql += " ORDER BY builtin DESC, position ASC, name COLLATE NOCASE ASC"
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
        return [_row_to_template(row) for row in rows]

    async def get_template(self, template_id: str) -> NoteTemplate | None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
            row = await cur.fetchone()
        return _row_to_template(row) if row else None

    async def save_template(self, template: NoteTemplate) -> NoteTemplate:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO templates (id, kind, name, body, capture_mode, builtin, position, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    kind = excluded.kind, name = excluded.name, body = excluded.body,
                    capture_mode = excluded.capture_mode, builtin = excluded.builtin,
                    position = excluded.position
                """,
                (
                    template.id,
                    template.kind,
                    template.name,
                    template.body,
                    template.capture_mode,
                    1 if template.builtin else 0,
                    template.position,
                    _dump_dt(datetime.now(tz=UTC)),
                ),
            )
            await db.commit()
        return template

    async def delete_template(self, template_id: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM templates WHERE id = ? AND builtin = 0", (template_id,))
            await db.execute("UPDATE sessions SET template_id = NULL WHERE template_id = ?", (template_id,))
            await db.commit()

    # --- Central de tarefas -------------------------------------------------

    async def list_tasks(self, *, session_id: str | None = None) -> list[TaskItem]:
        sql = "SELECT * FROM tasks"
        params: list[str] = []
        if session_id:
            sql += " WHERE session_id = ?"
            params.append(session_id)
        sql += " ORDER BY done ASC, created_at DESC"
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
        return [_row_to_task(row) for row in rows]

    async def get_task(self, task_id: str) -> TaskItem | None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = await cur.fetchone()
        return _row_to_task(row) if row else None

    async def save_task(self, task: TaskItem) -> TaskItem:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO tasks (id, session_id, text, owner, due, done, done_at, origin, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text = excluded.text, owner = excluded.owner, due = excluded.due,
                    done = excluded.done, done_at = excluded.done_at
                """,
                (
                    task.id,
                    task.session_id,
                    task.text,
                    task.owner,
                    task.due,
                    1 if task.done else 0,
                    _dump_dt(task.done_at),
                    task.origin,
                    _dump_dt(task.created_at),
                ),
            )
            await db.commit()
        return task

    async def delete_task(self, task_id: str) -> bool:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            await db.commit()
            return cur.rowcount > 0

    async def delete_session_tasks(self, session_id: str, *, origin: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM tasks WHERE session_id = ? AND origin = ?", (session_id, origin))
            await db.commit()

    async def sessions_with_summary(self) -> list[str]:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute("SELECT DISTINCT session_id FROM summaries")
            return [str(row[0]) for row in await cur.fetchall()]

    # --- Retenção -------------------------------------------------------------

    async def purge_transcript(self, session_id: str) -> None:
        """Apaga a fala e as vozes da sessão; ata, notas e tarefas ficam."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM segments WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM segment_voices WHERE session_id = ?", (session_id,))
            await db.execute(
                "UPDATE sessions SET transcript_purged_at = ? WHERE id = ?",
                (_dump_dt(datetime.now(tz=UTC)), session_id),
            )
            await db.commit()

    # --- Motor de voz -----------------------------------------------------

    async def save_segment_voice(
        self,
        segment_id: str,
        session_id: str,
        *,
        dim: int,
        embedding: bytes,
        frames: bytes,
        frame_count: int,
    ) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO segment_voices (segment_id, session_id, dim, embedding, frames, frame_count)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(segment_id) DO UPDATE SET
                    dim = excluded.dim, embedding = excluded.embedding,
                    frames = excluded.frames, frame_count = excluded.frame_count
                """,
                (segment_id, session_id, dim, embedding, frames, frame_count),
            )
            await db.commit()

    async def list_segment_voices(self, session_id: str) -> list[tuple[str, int, bytes, bytes, int]]:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                """
                SELECT segment_voices.segment_id, segment_voices.dim, segment_voices.embedding,
                       segment_voices.frames, segment_voices.frame_count
                FROM segment_voices
                JOIN segments ON segments.id = segment_voices.segment_id
                WHERE segment_voices.session_id = ?
                ORDER BY segments.start_ms ASC
                """,
                (session_id,),
            )
            rows = await cur.fetchall()
        return [(str(r[0]), int(r[1]), bytes(r[2]), bytes(r[3]), int(r[4])) for r in rows]

    async def update_segment_voices(
        self,
        rows: Sequence[tuple[str, str | None, float | None, str | None]],
    ) -> None:
        """(segment_id, voz, confiança, pessoa). Trecho travado mantém a pessoa."""
        if not rows:
            return
        async with aiosqlite.connect(self._path) as db:
            await db.executemany(
                """
                UPDATE segments
                SET speaker_cluster = ?,
                    speaker_confidence = ?,
                    speaker_id = CASE WHEN speaker_locked = 1 THEN speaker_id ELSE ? END
                WHERE id = ?
                """,
                [(cluster, confidence, person, segment_id) for segment_id, cluster, confidence, person in rows],
            )
            await db.commit()

    async def assign_cluster_person(self, session_id: str, cluster: str, person_id: str | None) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO session_voices (session_id, cluster, person_id) VALUES (?, ?, ?)
                ON CONFLICT(session_id, cluster) DO UPDATE SET person_id = excluded.person_id
                """,
                (session_id, cluster, person_id),
            )
            await db.execute(
                """
                UPDATE segments SET speaker_id = ?
                WHERE session_id = ? AND speaker_cluster = ? AND speaker_locked = 0
                """,
                (person_id, session_id, cluster),
            )
            await db.commit()

    async def list_session_voices(self, session_id: str) -> dict[str, str | None]:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "SELECT cluster, person_id FROM session_voices WHERE session_id = ?",
                (session_id,),
            )
            rows = await cur.fetchall()
        return {str(r[0]): (str(r[1]) if r[1] else None) for r in rows}

    async def replace_session_voices(self, session_id: str, links: dict[str, str | None]) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM session_voices WHERE session_id = ?", (session_id,))
            await db.executemany(
                "INSERT INTO session_voices (session_id, cluster, person_id) VALUES (?, ?, ?)",
                [(session_id, cluster, person) for cluster, person in links.items()],
            )
            await db.commit()

    async def list_voiceprints(self, model: str) -> dict[str, tuple[int, bytes, int]]:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "SELECT person_id, dim, embedding, samples FROM voiceprints WHERE model = ?",
                (model,),
            )
            rows = await cur.fetchall()
        return {str(r[0]): (int(r[1]), bytes(r[2]), int(r[3])) for r in rows}

    async def voiceprint_people(self) -> set[str]:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute("SELECT person_id FROM voiceprints")
            rows = await cur.fetchall()
        return {str(r[0]) for r in rows}

    async def save_voiceprint(self, person_id: str, *, model: str, dim: int, embedding: bytes, samples: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO voiceprints (person_id, model, dim, embedding, samples, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(person_id) DO UPDATE SET
                    model = excluded.model, dim = excluded.dim, embedding = excluded.embedding,
                    samples = excluded.samples, updated_at = excluded.updated_at
                """,
                (person_id, model, dim, embedding, samples, _dump_dt(datetime.now(tz=UTC))),
            )
            await db.commit()

    async def delete_voiceprint(self, person_id: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM voiceprints WHERE person_id = ?", (person_id,))
            await db.commit()

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
        template_id=row["template_id"] if "template_id" in keys else None,
        transcript_purged_at=_parse_dt(row["transcript_purged_at"]) if "transcript_purged_at" in keys else None,
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
        speaker_cluster=row["speaker_cluster"] if "speaker_cluster" in keys else None,
        speaker_confidence=(
            float(row["speaker_confidence"])
            if "speaker_confidence" in keys and row["speaker_confidence"] is not None
            else None
        ),
        speaker_locked=bool(row["speaker_locked"]) if "speaker_locked" in keys else False,
    )


def _row_to_template(row: aiosqlite.Row) -> NoteTemplate:
    kind = row["kind"] if row["kind"] in {"note", "recipe"} else "note"
    return NoteTemplate(
        id=row["id"],
        kind=kind,
        name=row["name"],
        body=row["body"],
        capture_mode=row["capture_mode"],
        builtin=bool(row["builtin"]),
        position=int(row["position"] or 0),
    )


def _row_to_task(row: aiosqlite.Row) -> TaskItem:
    origin = row["origin"] if row["origin"] in {"ai", "manual"} else "ai"
    return TaskItem(
        id=row["id"],
        session_id=row["session_id"],
        text=row["text"],
        owner=row["owner"],
        due=row["due"],
        done=bool(row["done"]),
        done_at=_parse_dt(row["done_at"]),
        origin=origin,
        created_at=_parse_dt(row["created_at"]) or datetime.now(tz=UTC),
    )


def _row_to_person(row: aiosqlite.Row) -> Person:
    return Person(id=row["id"], name=row["name"])


def _row_to_tag(row: aiosqlite.Row) -> Tag:
    return Tag(id=row["id"], name=row["name"])


def _row_to_chat(row: aiosqlite.Row) -> Chat:
    return Chat(
        id=row["id"],
        title=row["title"],
        created_at=_parse_dt(row["created_at"]) or datetime.now(tz=UTC),
        updated_at=_parse_dt(row["updated_at"]) or datetime.now(tz=UTC),
        focus_session_id=row["focus_session_id"] or None,
    )


def _row_to_chat_message(row: aiosqlite.Row) -> ChatMessage:
    raw = json.loads(row["citations_json"] or "[]")
    citations: list[ChatCitation] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            session_id = str(item.get("session_id") or "")
            if not session_id:
                continue
            citations.append(
                ChatCitation(
                    session_id=session_id,
                    session_title=str(item.get("session_title") or ""),
                    segment_id=str(item["segment_id"]) if item.get("segment_id") else None,
                    start_ms=int(item.get("start_ms") or 0),
                    excerpt=str(item.get("excerpt") or ""),
                )
            )
    role = row["role"] if row["role"] in {"user", "assistant"} else "assistant"
    return ChatMessage(
        id=row["id"],
        chat_id=row["chat_id"],
        role=role,
        content=row["content"],
        created_at=_parse_dt(row["created_at"]) or datetime.now(tz=UTC),
        citations=citations,
    )


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
