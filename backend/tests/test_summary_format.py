from __future__ import annotations

from app.application.summarize import parse_summary_json, render_transcript
from app.domain.models import TranscriptSegment
from app.infrastructure.asr.whisper_engine import filter_transcript


def test_parse_reads_topics_actions_and_language() -> None:
    raw = """{
      "language": "PT-BR",
      "overview": "Alinhamento do fluxo de cadastro.",
      "topics": [{"title": "Esteira", "points": ["Cadastro vai para o compliance"]}],
      "decisions": ["Alinhar o fluxo"],
      "action_items": [
        {"text": "Validar documento", "owner": "Tomás", "due": "não mencionado"},
        {"text": "Sem responsável"}
      ],
      "open_items": ["Documentação do CNPJ"]
    }"""
    parsed = parse_summary_json(raw)
    assert parsed["language"] == "pt-br"
    assert parsed["topics"][0].points == ["Cadastro vai para o compliance"]
    assert parsed["highlights"] == ["Cadastro vai para o compliance"]
    assert parsed["action_items"][0].owner == "Tomás"
    assert parsed["action_items"][0].due is None
    assert parsed["open_items"] == ["Documentação do CNPJ"]


def test_parse_survives_prose_around_the_json() -> None:
    parsed = parse_summary_json('Claro! {"overview": "Ata."} Espero ter ajudado.')
    assert parsed["overview"] == "Ata."
    assert parsed["topics"] == []


def test_transcript_carries_timestamp_and_speaker() -> None:
    segments = [
        TranscriptSegment(
            id="1",
            session_id="s",
            start_ms=63_000,
            end_ms=65_000,
            text="Clico aqui.",
            source="mic",
        ),
        TranscriptSegment(
            id="2",
            session_id="s",
            start_ms=66_000,
            end_ms=68_000,
            text="Ele executa.",
            speaker_id="p1",
            source="loopback",
        ),
    ]
    rendered = render_transcript(segments, {"p1": "Tomás"})
    assert rendered.splitlines() == [
        "[01:03] Você: Clico aqui.",
        "[01:06] Tomás: Ele executa.",
    ]


def test_youtube_hallucinations_never_reach_the_transcript() -> None:
    assert filter_transcript("Inscreva-se no canal e ative o sininho.") == ""
    assert filter_transcript("Legendas pela comunidade Amara.org") == ""
    assert filter_transcript("Thanks for watching!") == ""
    assert filter_transcript("Aprovar o cadastro.") == "Aprovar o cadastro."
