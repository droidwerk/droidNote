from __future__ import annotations

import glob
import json
import re
import unicodedata
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from app.core.logging import get_logger

from app.domain.models import Session, Summary, TranscriptSegment
from app.domain.ports import SessionRepository

log = get_logger("sessions")

TRASH_DAYS = 30
# Pastas de gravação usadas antes (JSON): apagar de vez procura o áudio nelas também.
OLD_DIRS_KEY = "recordings_dirs_old"

class SessionService:
    def __init__(self, store: SessionRepository) -> None:
        self._store = store

    async def list_sessions(self, scope: str = "all") -> list[Session]:
        return await self._store.list_sessions(scope)

    async def get(self, session_id: str, *, include_trash: bool = False) -> Session:
        session = await self._store.get_session(session_id, include_trash=include_trash)
        if session is None:
            raise KeyError(session_id)
        return session

    async def rename(self, session_id: str, title: str) -> Session:
        session = await self.get(session_id)
        updated = replace(session, title=title.strip())
        await self._store.update_session(updated)
        return updated

    async def apply(
        self,
        session_id: str,
        action: str,
        *,
        recording: Path,
        live_id: str | None = None,
    ) -> str | None:
        """archive | unarchive | trash | restore | purge. None = feito (repetir é inofensivo);
        senão o motivo: missing, live, not_trashed ou busy (o Windows segura o .wav)."""
        if live_id and session_id == live_id:
            return "live"
        session = await self._store.get_session(session_id, include_trash=True)
        if session is None:
            return "missing"
        now = datetime.now(tz=UTC)
        if action in {"archive", "unarchive"}:
            if session.deleted_at:
                return "missing"
            await self._store.set_session_archived(session_id, now if action == "archive" else None)
        elif action == "trash":
            if session.deleted_at is None:
                await self._store.set_session_deleted(session_id, now)
        elif action == "restore":
            if session.deleted_at:
                await self._store.set_session_deleted(session_id, None)
        elif action == "purge":
            if session.deleted_at is None:
                return "not_trashed"
            if not await purge_session(self._store, session_id, recording):
                return "busy"
        else:
            raise ValueError(action)
        return None

    async def segments(self, session_id: str) -> list[TranscriptSegment]:
        await self.get(session_id)
        return await self._store.list_segments(session_id)

    async def search(self, query: str, session_id: str | None = None) -> list[TranscriptSegment]:
        cleaned = query.strip()
        if not cleaned:
            return []
        # Busca da tela: só palavras comuns ("reunião") ainda procuram por elas.
        query = _fts_query(cleaned) or _fts_query(cleaned, stopwords=False)
        if not query:
            return []
        hits = await self._store.search(query, session_id=session_id)
        # O banco corta pelos mais relevantes (bm25); a tela continua em ordem de tempo.
        return sorted(hits, key=lambda item: item.start_ms)

    async def save_note(self, session_id: str, notes_markdown: str) -> Summary:
        await self.get(session_id)
        summary = await self._store.get_summary(session_id)
        if summary is None:
            raise KeyError(session_id)
        updated = replace(summary, notes_markdown=notes_markdown)
        await self._store.save_summary(updated)
        return updated

    async def export_markdown(self, session_id: str, locale: str | None = None, parts: str = "all") -> str:
        """`parts`: all (nota + transcrição), notes (só a nota) ou transcript (só a transcrição)."""
        from app.application.summarize import voice_label
        from app.core.i18n import ui_message

        session = await self.get(session_id)
        segments = await self._store.list_segments(session_id) if parts != "notes" else []
        summary = await self._store.get_summary(session_id) if parts != "transcript" else None
        lines = [
            f"# {session.title}",
            "",
            f"- {ui_message(locale, 'export_start')}: {session.started_at.isoformat()}",
        ]
        if session.ended_at:
            lines.append(f"- {ui_message(locale, 'export_end')}: {session.ended_at.isoformat()}")
        if session.language:
            lines.append(f"- {ui_message(locale, 'export_language')}: {session.language}")
        if parts == "notes" and summary and summary.notes_markdown.strip():
            lines.extend(["", summary.notes_markdown.strip()])
            return "\n".join(lines) + "\n"
        if parts != "notes":
            lines.extend(["", f"## {ui_message(locale, 'export_transcript')}", ""])
        people = {item.id: item.name for item in await self._store.list_people()}
        for segment in segments:
            stamp = _fmt_ms(segment.start_ms)
            lang = f" ({segment.language})" if segment.language else ""
            speaker = ""
            if segment.speaker_id and segment.speaker_id in people:
                speaker = f" {people[segment.speaker_id]}"
            elif segment.speaker_cluster:
                speaker = f" {voice_label(segment.speaker_cluster, segment.language or session.language)}"
            lines.append(f"- [{stamp}]{speaker}{lang} {segment.text}")
        if summary:
            lines.extend(
                ["", f"## {ui_message(locale, 'export_summary')}", "", f"### {ui_message(locale, 'export_highlights')}"]
            )
            lines.extend([f"- {item}" for item in summary.highlights] or ["- —"])
            lines.extend(["", f"### {ui_message(locale, 'export_decisions')}"])
            lines.extend([f"- {item}" for item in summary.decisions] or ["- —"])
            lines.extend(["", f"### {ui_message(locale, 'export_actions')}"])
            if summary.action_items:
                for item in summary.action_items:
                    owner = f" ({item.owner})" if item.owner else ""
                    lines.append(f"- {item.text}{owner}")
            else:
                lines.append("- —")
        return "\n".join(lines) + "\n"


# Palavras que casam com quase todo trecho (pt/en/es) e palavras que só apontam para a própria
# gravação ("nessa conversa", "esse vídeo"): não ajudam a achar o assunto.
_STOPWORDS = frozenset(
    """
    a o as os um uma uns umas de do da dos das no na nos nas em ao aos pelo pela pelos pelas por para pra
    com sem que quem qual quais quando onde como porque pois se ou e mas nem ja nao sim mais menos muito
    muita muitos muitas pouco tudo todo toda todos todas nada algo isso isto esse essa esses essas este
    esta estes estas aquele aquela aquilo nesse nessa neste nesta naquele naquela dele dela deles delas
    eu tu ele ela nos vos eles elas me mim te voce voces lhe meu minha meus minhas seu sua seus suas
    nosso nossa foi foram era eram sou ser estar esta estao estava tem ter tinha ha havia vai vou fazer
    faca faz fiz quero queria gostaria preciso pode poderia sobre entre ate desde apos depois antes
    estou estamos esteve estive referindo refiro falando falar
    ajude ajuda ajudar explique explica explicar resuma resumir resumo liste listar lista diga dizer
    mostre mostrar estudar partir falas fala aqui ali agora entao tambem so apenas cada outro outra
    conversa conversas reuniao reunioes aula aulas video videos chamada chamadas gravacao transcricao
    the an of to in on at for from by with without and or but not no yes is are was were be been
    do does did have has had it its this that these those there here what which who whom whose when
    where why how all any each some more most other such than too very can could should would will
    just about into over after before me my mine myself we our you your he him his she her they them
    their please tell show give explain summarize summary list help study meeting meetings call calls
    lecture lectures transcript conversation
    el la los las un una unos unas del al lo le les mi mis tu tus su sus yo es son fue fueron esto
    eso pero muy sin sobre hay
    """.split()
)


def _fold(token: str) -> str:
    return unicodedata.normalize("NFKD", token).encode("ascii", "ignore").decode()


def _fts_query(raw: str, *, stopwords: bool = True) -> str:
    """Pergunta em linguagem natural -> consulta FTS5: tira palavras comuns e casa prefixo
    ("bugs" acha "bug", "lembretes" acha "lembrete"). Vazio quando não sobra assunto."""
    terms: list[str] = []
    for token in re.findall(r"[A-Za-zÀ-ÿ0-9]{2,}", raw):
        token = token.lower()
        if stopwords and _fold(token) in _STOPWORDS:
            continue
        if len(token) >= 4 and token.endswith("s"):
            token = token[:-1]
        # Minúsculas: "AND"/"OR"/"NOT"/"NEAR" digitados viram palavra, não operador.
        term = f"{token}*" if len(token) >= 3 else token
        if term not in terms:
            terms.append(term)
    return " OR ".join(terms[:16])


async def _old_dirs(store: SessionRepository) -> list[str]:
    try:
        value = json.loads((await store.get_setting(OLD_DIRS_KEY)) or "[]")
    except ValueError:
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


async def remember_recordings_dir(store: SessionRepository, old: Path, new: Path) -> None:
    """Troca de pasta não move o áudio antigo; guarda a pasta para o purge achar."""
    if old.resolve() == new.resolve():
        return
    folders = await _old_dirs(store)
    if str(old) not in folders:
        await store.set_setting(OLD_DIRS_KEY, json.dumps([*folders, str(old)]))


async def purge_session(store: SessionRepository, session_id: str, recording: Path) -> bool:
    """Apaga de vez: primeiro o áudio (`<id>.*` na pasta atual e nas antigas), depois as linhas.
    Arquivo preso: as linhas ficam para a próxima tentativa, nunca sobra áudio sem conversa."""
    pattern = glob.escape(recording.stem) + ".*"
    for folder in dict.fromkeys([recording.parent, *map(Path, await _old_dirs(store))]):
        for path in folder.glob(pattern):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                log.warning("purge could not delete file session=%s", session_id)
                return False
    await store.delete_session(session_id)
    return True


def _fmt_ms(value: int) -> str:
    seconds = max(value, 0) // 1000
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"
