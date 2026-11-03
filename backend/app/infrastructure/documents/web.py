"""Páginas da web e vídeos do YouTube como fonte do chat.

Página: baixa o HTML e tira o texto do corpo (sem script, estilo, menus).
YouTube: o yt-dlp lê o título e as legendas do vídeo (as automáticas também),
com a marca de tempo de cada trecho; nada de vídeo é baixado. Sem legenda,
e com o motor de voz pronto, baixa só o áudio (até AUDIO_MAX_SECONDS) e
transcreve com o mesmo Whisper das gravações. Fora disso dá erro claro.

Só a leitura usa a rede; o texto fica no banco local como qualquer documento.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from app import __version__
from app.core.net_tls import ssl_verify
from app.infrastructure.documents.readers import CHUNK_OVERLAP, CHUNK_SIZE, DocumentError, Piece

MAX_BYTES = 6 * 1024 * 1024
TIMEOUT = httpx.Timeout(connect=10.0, read=25.0, write=10.0, pool=10.0)
# Agente honesto: nome, versão e endereço do projeto. Sites como a Wikipédia recusam
# programas que se apresentam como navegador e pedem exatamente este formato.
USER_AGENT = f"DroidNote/{__version__} (local meeting notes app; +https://github.com/droidwerk/droidNote)"
_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}
_SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "iframe", "svg", "template"}

log = logging.getLogger("droidnote.web")

Fetcher = Callable[[str, dict[str, str] | None], tuple[str, str]]
# (amostras float32 a 16 kHz, taxa) -> [(início, fim, palavra)]: o contrato de AsrPort.transcribe_words.
Transcriber = Callable[[Sequence[float], int], list[tuple[float, float, str]]]
# Fábrica de yt_dlp.YoutubeDL (injetável nos testes, que não tocam a rede).
YoutubeFactory = Callable[[dict], object]

AUDIO_SAMPLE_RATE = 16_000
AUDIO_MAX_SECONDS = 30 * 60
# Legendas em ordem de preferência: português (inclui pt-BR e a faixa "-orig"
# das automáticas), depois inglês. Qualquer outra língua só se não houver essas.
SUB_LANGS = ["pt.*", "en.*"]
SUB_FORMATS = "json3/srv3/vtt/best"


def normalize_url(raw: str) -> str:
    cleaned = (raw or "").strip()
    if cleaned and not re.match(r"^[a-z][a-z0-9+.-]*://", cleaned, re.I):
        cleaned = "https://" + cleaned
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DocumentError("url_invalid")
    if parsed.username or parsed.password:
        raise DocumentError("url_invalid")
    _refuse_local_target(parsed.hostname or "")
    return cleaned


def _refuse_local_target(host: str) -> None:
    """O leitor roda com os acessos deste PC: não serve para espiar o próprio backend,
    o Ollama ou endereços de metadados (169.254.x.x). Rede local (intranet) continua permitida."""
    import ipaddress
    import socket

    name = host.strip("[]").lower()
    if name in {"localhost", "localhost.localdomain"} or name.endswith(".localhost"):
        raise DocumentError("url_invalid")
    candidates: list[str] = []
    try:
        candidates.append(str(ipaddress.ip_address(name)))
    except ValueError:
        try:
            candidates = [info[4][0] for info in socket.getaddrinfo(name, None)]
        except OSError:
            return  # sem DNS agora: a leitura em si vai falhar com url_unreachable
    for raw in candidates:
        address = ipaddress.ip_address(raw.split("%")[0])
        if address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast:
            raise DocumentError("url_invalid")


def youtube_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    if host not in _YT_HOSTS:
        return None
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
    elif parsed.path.startswith(("/shorts/", "/live/", "/embed/")):
        candidate = parsed.path.split("/")[2] if len(parsed.path.split("/")) > 2 else ""
    else:
        candidate = (parse_qs(parsed.query).get("v") or [""])[0]
    return candidate if re.fullmatch(r"[A-Za-z0-9_-]{6,}", candidate or "") else None


def _default_fetch(url: str, headers: dict[str, str] | None = None) -> tuple[str, str]:
    """(texto, content-type). Lê no máximo MAX_BYTES."""
    request_headers = {"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8", **(headers or {})}
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True, verify=ssl_verify(), headers=request_headers) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise DocumentError("too_large")
                    chunks.append(chunk)
                content_type = response.headers.get("content-type", "")
                encoding = response.encoding or "utf-8"
        return b"".join(chunks).decode(encoding, errors="replace"), content_type
    except DocumentError:
        raise
    except httpx.HTTPError as exc:
        raise DocumentError("url_unreachable") from exc


def read_url(
    url: str,
    fetch: Fetcher | None = None,
    transcribe: Transcriber | None = None,
    youtube: YoutubeFactory | None = None,
) -> tuple[str, str, list[Piece], int]:
    """(nome, tipo, trechos, páginas/minutos) de uma página ou vídeo."""
    fetch = fetch or _default_fetch
    url = normalize_url(url)
    video = youtube_id(url)
    if video:
        title, cues = read_youtube(video, transcribe=transcribe, youtube=youtube)
        pieces = _chunk_cues(cues)
        minutes = (int(cues[-1][0] // 60) + 1) if cues else 1
        return title, "youtube", pieces, minutes
    title, text = read_page(url, fetch)
    pieces = _chunk_text(text, page=None)
    return title, "web", pieces, 1


# ------------------------------------------------------------------ páginas


def read_page(url: str, fetch: Fetcher) -> tuple[str, str]:
    body, content_type = fetch(url, None)
    if "html" not in content_type.lower() and not body.lstrip().lower().startswith(("<!doctype", "<html")):
        text = body.strip()
        if not text:
            raise DocumentError("empty")
        return _name_from_url(url), text
    title, text = extract_html_text(body)
    if not text.strip():
        raise DocumentError("empty")
    return title or _name_from_url(url), text


def extract_html_text(html: str) -> tuple[str, str]:
    """(título, texto) do HTML: só o que a pessoa leria na página."""
    from lxml import html as lxml_html

    try:
        root = lxml_html.fromstring(html)
    except Exception as exc:  # HTML vazio ou irrecuperável
        raise DocumentError("unreadable") from exc
    title_node = root.find(".//title")
    title = " ".join((title_node.text_content() if title_node is not None else "").split())
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        if node.tag.lower() in _SKIP_TAGS:
            node.drop_tree() if node.getparent() is not None else None
    body = root.find(".//body")
    if body is None:
        body = root
    # <article>/<main> quando existem: o resto costuma ser menu e rodapé.
    main = body.find(".//article") if body.find(".//article") is not None else body.find(".//main")
    source = main if main is not None and len(main.text_content().strip()) > 400 else body
    lines: list[str] = []
    for block in source.iter("p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "td", "th", "blockquote", "dd", "dt", "figcaption"):
        text = " ".join(block.text_content().split())
        if text:
            if block.tag.lower() in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                text = f"{'#' * int(block.tag[1])} {text}"
            lines.append(text)
    if not lines:
        lines = [" ".join(source.text_content().split())]
    # Mesma linha repetida (menus duplicados) entra uma vez.
    seen: set[str] = set()
    unique = [line for line in lines if not (line in seen or seen.add(line))]
    return title[:160], "\n".join(unique)


def _name_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/").split("/")[-1]
    return (f"{parsed.netloc}/{path}" if path else parsed.netloc)[:160]


# ------------------------------------------------------------------ youtube


def _default_youtube(opts: dict) -> object:
    import yt_dlp

    return yt_dlp.YoutubeDL(opts)


def _ydl_opts(out_dir: Path, **extra: object) -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _QuietLogger(),
        "noplaylist": True,
        # Nenhum runtime JavaScript externo (deno etc.): legendas e áudio saem sem
        # executar código do player, e o comportamento é o mesmo em toda máquina.
        "js_runtimes": {},
        "socket_timeout": 20,
        "retries": 2,
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "paths": {"home": str(out_dir), "temp": str(out_dir)},
        **extra,
    }


class _QuietLogger:
    """O yt-dlp fala pelo log do app, nunca pelo stdout/stderr do sidecar."""

    def debug(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def info(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def warning(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        log.info("yt-dlp: %s", msg)


def read_youtube(
    video_id: str,
    *,
    transcribe: Transcriber | None = None,
    youtube: YoutubeFactory | None = None,
) -> tuple[str, list[tuple[float, str]]]:
    """(título, [(segundos, fala)]) das legendas do vídeo; sem legenda, do áudio transcrito aqui."""
    factory = youtube or _default_youtube
    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory(prefix="droidnote-yt-") as tmp:
        out_dir = Path(tmp)
        try:
            with factory(_ydl_opts(out_dir, skip_download=True)) as ydl:  # type: ignore[attr-defined]
                # 1) Só os metadados: título, duração e quais legendas existem.
                info = _single_video(ydl.extract_info(url, download=False))  # type: ignore[attr-defined]
                title = (str(info.get("title") or "") or f"YouTube {video_id}")[:160]
                manual = set((info.get("subtitles") or {}).keys())
                langs = sorted(manual | set((info.get("automatic_captions") or {}).keys()))
                cues: list[tuple[float, str]] = []
                if langs:
                    # 2) Uma faixa só: pedir várias de uma vez faz o YouTube limitar (429).
                    lang = pick_caption_language(langs, manual)
                    ydl.params.update(  # type: ignore[attr-defined]
                        writesubtitles=True,
                        writeautomaticsub=True,
                        subtitleslangs=[re.escape(lang)],
                        subtitlesformat=SUB_FORMATS,
                    )
                    written = ydl.process_ie_result(ydl.sanitize_info(info, True), download=True)  # type: ignore[attr-defined]
                    cues = _cues_from_subtitles(_single_video(written))
        except DocumentError:
            raise
        except Exception as exc:
            raise _youtube_error(exc) from exc
        if cues:
            return title, cues
        duration = float(info.get("duration") or 0)
        if transcribe is None or duration <= 0 or duration > AUDIO_MAX_SECONDS:
            raise DocumentError("no_captions")
        log.info("youtube %s has no captions; transcribing %.0fs of audio locally", video_id, duration)
        audio = _download_audio(url, out_dir, factory)
        try:
            cues = _cues_from_audio(audio, transcribe)
        except Exception as exc:  # áudio corrompido ou motor de voz indisponível
            log.warning("youtube %s: audio transcription failed: %s", video_id, exc)
            raise DocumentError("no_captions") from exc
        if not cues:
            raise DocumentError("no_captions")
        return title, cues


def _single_video(info: object) -> dict:
    if not isinstance(info, dict):
        raise DocumentError("no_captions")
    entries = info.get("entries")
    if entries:  # playlist: fica o primeiro vídeo
        first = next((item for item in entries if isinstance(item, dict)), None)
        return first or {}
    return info


def _youtube_error(exc: Exception) -> DocumentError:
    message = str(exc).lower()
    unreachable = ("unavailable", "private video", "removed", "does not exist", "not available",
                   "timed out", "connection", "resolve", "network", "offline")
    if any(word in message for word in unreachable):
        return DocumentError("url_unreachable")
    return DocumentError("no_captions")


def _cues_from_subtitles(info: dict) -> list[tuple[float, str]]:
    requested = info.get("requested_subtitles") or {}
    written = [
        entry
        for entry in requested.values()
        if isinstance(entry, dict) and entry.get("filepath") and Path(str(entry["filepath"])).is_file()
    ]
    for entry in written:
        if cues := _parse_file(entry):
            return cues
    return []


def _parse_file(entry: dict) -> list[tuple[float, str]]:
    path = Path(str(entry["filepath"]))
    ext = str(entry.get("ext") or path.suffix.lstrip("."))
    return parse_captions(path.read_text(encoding="utf-8", errors="replace"), ext)


def pick_caption_language(langs: list[str], manual: set[str]) -> str:
    """Português antes de inglês; feita à mão antes da automática original, e esta antes da traduzida.

    Nomes do yt-dlp: "pt", "pt-BR" (manuais ou automáticas na língua do vídeo),
    "pt-orig" (automática original), "pt-en" (automática traduzida da legenda em inglês).
    """
    available = set(langs)

    def score(lang: str) -> tuple[int, int, int]:
        code = lang.lower()
        orig = code.endswith("-orig")
        base = code[:-5] if orig else code
        parts = base.split("-")
        pref = 2 if parts[0] == "pt" else 1 if parts[0] == "en" else 0
        translated = len(parts) > 1 and parts[1].isalpha() and parts[1].islower() and 2 <= len(parts[1]) <= 3
        if lang in manual:
            kind = 3
        elif orig or (not translated and f"{lang}-orig" in available):
            kind = 2
        elif translated:
            kind = 0
        else:
            kind = 1
        return (pref, kind, 1 if orig else 0)

    return max(langs, key=score)


def parse_captions(raw: str, ext: str) -> list[tuple[float, str]]:
    ext = ext.lower()
    if ext == "json3":
        return parse_json3(raw)
    if ext == "vtt":
        return parse_vtt(raw)
    if ext in {"srv1", "srv2", "srv3", "ttml", "xml"}:
        return parse_timedtext_xml(raw)
    stripped = raw.lstrip()
    if stripped.startswith("{"):
        return parse_json3(raw)
    if stripped.startswith("WEBVTT"):
        return parse_vtt(raw)
    return parse_timedtext_xml(raw)


def parse_json3(raw: str) -> list[tuple[float, str]]:
    try:
        payload = json.loads(raw)
    except ValueError:
        return []
    cues: list[tuple[float, str]] = []
    for event in payload.get("events") or []:
        text = "".join(str(seg.get("utf8") or "") for seg in (event.get("segs") or []))
        text = " ".join(text.split())
        if not text or _is_sound_tag(text):
            continue
        cues.append((float(event.get("tStartMs") or 0) / 1000.0, text))
    return cues


_VTT_TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")


def parse_vtt(raw: str) -> list[tuple[float, str]]:
    """WebVTT. As automáticas do YouTube repetem a linha anterior em cada cue: fica uma vez só."""
    cues: list[tuple[float, str]] = []
    last = ""
    for block in re.split(r"\n\s*\n", raw.replace("\r", "")):
        lines = [line for line in block.split("\n") if line.strip()]
        index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if index is None:
            continue
        match = _VTT_TIME.search(lines[index].split("-->")[0])
        if not match:
            continue
        hours, minutes, seconds, frac = match.groups()
        start = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(frac.ljust(3, "0")) / 1000.0
        text_lines: list[str] = []
        for line in lines[index + 1 :]:
            clean = " ".join(_unescape(re.sub(r"<[^>]+>", "", line)).split())
            if clean and clean != last and not _is_sound_tag(clean):
                text_lines.append(clean)
                last = clean
        if text_lines:
            cues.append((start, " ".join(text_lines)))
    return cues


def parse_timedtext_xml(raw: str) -> list[tuple[float, str]]:
    cues: list[tuple[float, str]] = []
    pattern = r'<(?:text|p)\s+[^>]*?(start|t|begin)="([\d.:]+)"[^>]*>(.*?)</(?:text|p)>'
    for match in re.finditer(pattern, raw, re.S):
        start = _xml_time(match.group(1), match.group(2))
        text = " ".join(_unescape(re.sub(r"<[^>]+>", " ", match.group(3))).split())
        if text and not _is_sound_tag(text):
            cues.append((start, text))
    return cues


def _xml_time(attr: str, value: str) -> float:
    """srv1 <text start="s">, srv3 <p t="ms">, ttml <p begin="hh:mm:ss.mmm">."""
    if ":" in value:
        total = 0.0
        for part in value.split(":"):
            total = total * 60 + float(part or 0)
        return total
    start = float(value)
    return start / 1000.0 if attr == "t" else start


def _unescape(text: str) -> str:
    import html

    return html.unescape(html.unescape(text))


def _is_sound_tag(text: str) -> bool:
    """[Música], [Applause], (risos): marcação de som, não fala."""
    return bool(re.fullmatch(r"[\[(][^\])]{1,40}[\])]", text))


# ------------------------------------------------------------------ áudio (sem legenda)


def _download_audio(url: str, out_dir: Path, factory: YoutubeFactory) -> Path:
    """Só a faixa de áudio (m4a ou webm), sem conversão: o instalador não traz ffmpeg."""
    opts = _ydl_opts(
        out_dir,
        format="bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
        outtmpl=str(out_dir / "audio.%(ext)s"),
        max_filesize=120 * 1024 * 1024,
    )
    try:
        with factory(opts) as ydl:  # type: ignore[attr-defined]
            ydl.extract_info(url, download=True)  # type: ignore[attr-defined]
    except Exception as exc:
        raise _youtube_error(exc) from exc
    files = sorted(path for path in out_dir.glob("audio.*") if path.is_file() and not path.name.endswith(".part"))
    if not files:
        raise DocumentError("no_captions")
    return files[0]


def _cues_from_audio(path: Path, transcribe: Transcriber) -> list[tuple[float, str]]:
    # O PyAV que vem com o faster-whisper decodifica m4a/webm sem ffmpeg instalado.
    from faster_whisper.audio import decode_audio

    samples = decode_audio(str(path), sampling_rate=AUDIO_SAMPLE_RATE)
    words = transcribe(samples, AUDIO_SAMPLE_RATE)
    return cues_from_words(words)


def cues_from_words(words: Sequence[tuple[float, float, str]], span: float = 20.0) -> list[tuple[float, str]]:
    """Palavras com tempo viram frases de até `span` segundos, cortadas na pontuação."""
    cues: list[tuple[float, str]] = []
    current: list[str] = []
    start: float | None = None
    for w_start, w_end, token in words:
        word = str(token).strip()
        if not word:
            continue
        if start is None:
            start = float(w_start)
        current.append(word)
        ends_sentence = word[-1] in ".!?…"
        if (ends_sentence and float(w_end) - start >= span / 4) or float(w_end) - start >= span:
            cues.append((start, " ".join(current)))
            current, start = [], None
    if current and start is not None:
        cues.append((start, " ".join(current)))
    return cues


def _stamp(seconds: float) -> str:
    total = int(seconds)
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{sec:02d}" if hours else f"{minutes:02d}:{sec:02d}"


def _chunk_cues(cues: list[tuple[float, str]]) -> list[Piece]:
    """Agrupa legendas em trechos de ~CHUNK_SIZE caracteres, cada um com a marca de tempo inicial."""
    pieces: list[Piece] = []
    current: list[str] = []
    start: float | None = None
    size = 0
    for seconds, text in cues:
        if start is None:
            start = seconds
        current.append(text)
        size += len(text) + 1
        if size >= CHUNK_SIZE:
            pieces.append(Piece(text=f"[{_stamp(start)}] " + " ".join(current), page=int(start // 60) + 1))
            current, start, size = [], None, 0
    if current and start is not None:
        pieces.append(Piece(text=f"[{_stamp(start)}] " + " ".join(current), page=int(start // 60) + 1))
    return pieces


def _chunk_text(text: str, page: int | None) -> list[Piece]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    return [Piece(text=chunk.strip(), page=page) for chunk in splitter.split_text(text) if chunk.strip()]
