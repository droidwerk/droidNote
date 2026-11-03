from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.infrastructure.documents.readers import DocumentError
from app.infrastructure.documents.web import (
    cues_from_words,
    extract_html_text,
    normalize_url,
    parse_json3,
    parse_timedtext_xml,
    parse_vtt,
    pick_caption_language,
    read_url,
    youtube_id,
)
from tests.conftest import auth

HTML = """<!doctype html><html><head><title>Guia de Cache - Docs</title></head><body>
<nav><a href="/">Início</a><a href="/docs">Docs</a></nav>
<main><h1>Guia de Cache</h1><p>O cache guarda respostas para não recalcular.</p>
<h2>Invalidação</h2><p>A parte difícil é saber quando a entrada envelheceu.</p>
<pre>cache.set(key, value, ttl=60)</pre></main>
<script>alert(1)</script><footer>Rodapé 2026</footer></body></html>"""

JSON3 = json.dumps({"events": [
    {"tStartMs": 0, "segs": [{"utf8": "Uma fila é FIFO."}]},
    {"tStartMs": 65000, "segs": [{"utf8": "Quem chega primeiro sai primeiro."}]},
]})

VTT = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.500 align:start position:0%
All right, so<00:00:01.500><c> here</c><c> we</c><c> are</c>

00:00:03.500 --> 00:00:03.510 align:start position:0%
All right, so here we are

00:00:03.510 --> 00:01:05.000
in front of the elephants
[Music]
"""


def test_normalize_and_youtube_id() -> None:
    assert normalize_url("exemplo.com/docs") == "https://exemplo.com/docs"
    with pytest.raises(DocumentError):
        normalize_url("ftp://x")
    assert youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10") == "dQw4w9WgXcQ"
    assert youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube_id("https://exemplo.com/watch?v=abc") is None


def test_html_text_keeps_body_and_drops_chrome() -> None:
    title, text = extract_html_text(HTML)
    assert title == "Guia de Cache - Docs"
    assert "# Guia de Cache" in text and "## Invalidação" in text
    assert "cache.set(key, value, ttl=60)" in text
    assert "alert(1)" not in text and "Rodapé" not in text and "Início" not in text


def _fake_fetch(url: str, headers=None):
    return HTML, "text/html; charset=utf-8"


class FakeYoutubeDL:
    """O que read_youtube usa do yt_dlp.YoutubeDL, sem rede: grava a faixa pedida na pasta de saída."""

    calls: list[dict] = []
    subtitles: dict[str, dict[str, str]] = {}  # lang -> {ext: corpo}
    automatic: dict[str, dict[str, str]] = {}
    duration = 70
    audio_bytes: bytes | None = None
    fail: Exception | None = None

    def __init__(self, params: dict) -> None:
        self.params = dict(params)
        type(self).calls.append(dict(params))  # cópia: read_youtube muda params depois

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url: str, download: bool = False) -> dict:
        if self.fail:
            raise self.fail
        info = {
            "id": "dQw4w9WgXcQ",
            "title": "Aula de filas",
            "duration": self.duration,
            "subtitles": {lang: [{"ext": ext, "url": f"https://yt.test/{lang}.{ext}"} for ext in exts] for lang, exts in self.subtitles.items()},
            "automatic_captions": {lang: [{"ext": ext, "url": f"https://yt.test/{lang}.{ext}"} for ext in exts] for lang, exts in self.automatic.items()},
        }
        if download and self.params.get("format") and not self.params.get("skip_download"):
            out = Path(str(self.params["outtmpl"]).replace("%(ext)s", "m4a"))
            out.write_bytes(self.audio_bytes or b"")
        return info

    def sanitize_info(self, info: dict, remove_private: bool = False) -> dict:
        return dict(info)

    def process_ie_result(self, info: dict, download: bool = True) -> dict:
        (lang,) = self.params["subtitleslangs"]
        lang = lang.replace("\\", "")
        tracks = {**self.automatic, **self.subtitles}
        bodies = tracks.get(lang) or {}
        chosen = next((ext for ext in self.params["subtitlesformat"].split("/") if ext in bodies), None)
        info = dict(info)
        if chosen:
            path = Path(str(self.params["outtmpl"]).replace("%(id)s", info["id"]).replace("%(ext)s", f"{lang}.{chosen}"))
            path.write_text(bodies[chosen], encoding="utf-8")
            info["requested_subtitles"] = {lang: {"ext": chosen, "filepath": str(path)}}
        else:
            info["requested_subtitles"] = {}
        return info


@pytest.fixture
def fake_ydl():
    FakeYoutubeDL.calls = []
    FakeYoutubeDL.subtitles = {}
    FakeYoutubeDL.automatic = {}
    FakeYoutubeDL.duration = 70
    FakeYoutubeDL.audio_bytes = None
    FakeYoutubeDL.fail = None
    return FakeYoutubeDL


def test_read_url_page_with_fake_fetch() -> None:
    name, kind, pieces, pages = read_url("https://exemplo.com/docs/cache", fetch=_fake_fetch)
    assert kind == "web" and name == "Guia de Cache - Docs" and pages == 1
    assert any("não recalcular" in piece.text for piece in pieces)


def test_read_url_youtube_prefers_manual_portuguese_json3(fake_ydl) -> None:
    fake_ydl.subtitles = {"pt": {"json3": JSON3, "vtt": VTT}, "en": {"json3": "{}"}}
    fake_ydl.automatic = {"en-orig": {"vtt": VTT}, "pt-en": {"vtt": VTT}}
    name, kind, pieces, pages = read_url("https://youtu.be/dQw4w9WgXcQ", youtube=fake_ydl)
    assert kind == "youtube" and name == "Aula de filas"
    assert pieces[0].text.startswith("[00:00] Uma fila é FIFO.")
    assert pages == 2  # último trecho no minuto 1
    # Só os metadados primeiro (nada baixado), depois uma faixa só, em json3.
    assert fake_ydl.calls[0]["skip_download"] is True and "writesubtitles" not in fake_ydl.calls[0]
    assert len(fake_ydl.calls) == 1


def test_read_url_youtube_falls_back_to_automatic_vtt(fake_ydl) -> None:
    fake_ydl.automatic = {"en-orig": {"vtt": VTT}, "en": {"vtt": VTT}}
    name, kind, pieces, pages = read_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ", youtube=fake_ydl)
    assert kind == "youtube"
    assert pieces[0].text.startswith("[00:01] All right, so here we are in front of the elephants")
    assert "[Music]" not in pieces[0].text


def test_read_url_youtube_without_captions_raises(fake_ydl) -> None:
    with pytest.raises(DocumentError, match="no_captions"):
        read_url("https://youtu.be/dQw4w9WgXcQ", youtube=fake_ydl)
    assert len(fake_ydl.calls) == 1  # sem transcritor, o áudio não é baixado


def test_read_url_youtube_without_captions_transcribes_audio(fake_ydl, monkeypatch) -> None:
    import app.infrastructure.documents.web as web

    fake_ydl.audio_bytes = b"not really audio"
    decoded: list[str] = []

    def fake_decode(path: Path, transcribe):
        decoded.append(Path(path).name)
        return web.cues_from_words(transcribe([0.0] * 16_000, 16_000))

    monkeypatch.setattr(web, "_cues_from_audio", fake_decode)

    def transcribe(samples, sample_rate):
        assert sample_rate == 16_000
        return [(0.0, 0.4, "Olá"), (0.5, 1.0, "turma."), (30.0, 30.5, "Hoje"), (30.6, 31.0, "filas.")]

    name, kind, pieces, pages = read_url("https://youtu.be/dQw4w9WgXcQ", youtube=fake_ydl, transcribe=transcribe)
    assert kind == "youtube" and decoded == ["audio.m4a"]
    assert pieces[0].text == "[00:00] Olá turma. Hoje filas."
    audio_call = fake_ydl.calls[-1]
    assert audio_call["format"].startswith("bestaudio[ext=m4a]") and "skip_download" not in audio_call


def test_read_url_youtube_too_long_for_audio_fallback(fake_ydl) -> None:
    fake_ydl.duration = 31 * 60
    with pytest.raises(DocumentError, match="no_captions"):
        read_url("https://youtu.be/dQw4w9WgXcQ", youtube=fake_ydl, transcribe=lambda s, r: [])
    assert len(fake_ydl.calls) == 1


def test_read_url_youtube_maps_yt_dlp_errors(fake_ydl) -> None:
    fake_ydl.fail = RuntimeError("ERROR: [youtube] abc: Video unavailable")
    with pytest.raises(DocumentError, match="url_unreachable"):
        read_url("https://youtu.be/dQw4w9WgXcQ", youtube=fake_ydl)
    fake_ydl.fail = RuntimeError("ERROR: Sign in to confirm you're not a bot")
    with pytest.raises(DocumentError, match="no_captions"):
        read_url("https://youtu.be/dQw4w9WgXcQ", youtube=fake_ydl)


def test_pick_caption_language() -> None:
    assert pick_caption_language(["en", "en-orig", "pt-en", "de", "pt"], {"en", "de"}) == "pt"
    assert pick_caption_language(["en", "en-orig", "de"], {"en", "de"}) == "en"
    assert pick_caption_language(["pt-orig", "pt", "en", "es"], set()) == "pt-orig"
    assert pick_caption_language(["ja-orig", "ja", "pt", "en"], set()) == "pt"
    assert pick_caption_language(["pt-BR", "pt-en"], {"pt-BR"}) == "pt-BR"
    assert pick_caption_language(["ja-orig", "ja"], set()) == "ja-orig"


def test_parsers() -> None:
    raw = json.dumps({"events": [{"tStartMs": 10, "segs": [{"utf8": "[Música]"}]}, {"tStartMs": 20, "segs": [{"utf8": "oi"}]}]})
    assert parse_json3(raw) == [(0.02, "oi")]
    assert parse_vtt(VTT) == [(1.0, "All right, so here we are"), (3.51, "in front of the elephants")]
    srv3 = '<timedtext><body><p t="1500" d="2000">Olá <s>turma</s></p><p t="125000">Fim</p></body></timedtext>'
    assert parse_timedtext_xml(srv3) == [(1.5, "Olá turma"), (125.0, "Fim")]
    ttml = '<tt><body><p begin="00:01:05.250" end="00:01:07.000">Um &amp; dois</p></body></tt>'
    assert parse_timedtext_xml(ttml) == [(65.25, "Um & dois")]


def test_cues_from_words_cuts_on_sentence_and_span() -> None:
    words = [(0.0, 0.3, "Olá"), (0.4, 0.8, "turma."), (6.0, 6.3, "Hoje"), (6.4, 7.0, "filas."), (8.0, 40.0, "longo")]
    assert cues_from_words(words) == [(0.0, "Olá turma. Hoje filas."), (8.0, "longo")]


@pytest.mark.asyncio
async def test_url_endpoint_attaches_document_and_rejects_bad_links(client: AsyncClient, app, monkeypatch) -> None:
    import app.infrastructure.documents.web as web

    monkeypatch.setattr(web, "_default_fetch", _fake_fetch)
    created = await client.post("/documents/url", headers=auth(), json={"url": "exemplo.com/docs/cache"})
    assert created.status_code == 201
    body = created.json()
    assert body["kind"] == "web" and body["name"] == "Guia de Cache - Docs" and body["chunks"] >= 1

    bad = await client.post("/documents/url", headers=auth(), json={"url": "ftp://nada"})
    assert bad.status_code == 422 and bad.json()["detail"] == "url_invalid"


@pytest.mark.asyncio
async def test_url_endpoint_youtube_with_fake_yt_dlp(client: AsyncClient, app, monkeypatch, fake_ydl) -> None:
    import app.infrastructure.documents.web as web

    fake_ydl.subtitles = {"pt-BR": {"json3": JSON3}}
    monkeypatch.setattr(web, "_default_youtube", fake_ydl)
    created = await client.post("/documents/url", headers=auth(), json={"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["kind"] == "youtube" and body["name"] == "Aula de filas" and body["pages"] == 2

    # Sem legenda e com o motor de voz pronto: o áudio (falso) passa pelo FakeAsr do app.
    fake_ydl.subtitles = {}
    fake_ydl.audio_bytes = b"not really audio"
    monkeypatch.setattr(web, "_cues_from_audio", lambda path, transcribe: web.cues_from_words(transcribe([0.0] * 16_000, 16_000)))
    spoken = await client.post("/documents/url", headers=auth(), json={"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert spoken.status_code == 201, spoken.text
    assert spoken.json()["kind"] == "youtube"

    # Motor de voz ainda não instalado: erro claro, sem baixar áudio.
    app.state.container.setup.asr.ready = False
    calls_before = len(fake_ydl.calls)
    missing = await client.post("/documents/url", headers=auth(), json={"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert missing.status_code == 422 and missing.json()["detail"] == "no_captions"
    assert len(fake_ydl.calls) == calls_before + 1


def test_reader_refuses_loopback_and_credentials_in_url() -> None:
    """O leitor de links não pode virar porta para o próprio backend/Ollama nem levar senha na URL."""
    for url in ("http://127.0.0.1:8765/health", "http://localhost:11434/api/tags", "http://[::1]:8777/", "http://169.254.169.254/latest", "https://user:pass@exemplo.com/"):
        with pytest.raises(DocumentError):
            normalize_url(url)
    assert normalize_url("https://pt.wikipedia.org/wiki/X").startswith("https://pt.wikipedia.org")
