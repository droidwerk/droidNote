from __future__ import annotations

from app.application.speakers import peel_speaker_prefix
from app.domain.models import Person


def test_peel_speaker_prefix_colon() -> None:
    ana = Person(id="ana", name="Ana")
    bruno = Person(id="bruno", name="Bruno")
    text, speaker = peel_speaker_prefix("Ana: olá equipe", [ana, bruno])
    assert speaker == "ana"
    assert text == "olá equipe"


def test_peel_speaker_prefix_dash() -> None:
    ana = Person(id="ana", name="Ana")
    text, speaker = peel_speaker_prefix("Ana - bom dia", [ana])
    assert speaker == "ana"
    assert text == "bom dia"


def test_peel_speaker_prefix_ignores_partial_name() -> None:
    ana = Person(id="ana", name="Ana")
    text, speaker = peel_speaker_prefix("Análise do projeto", [ana])
    assert speaker is None
    assert text == "Análise do projeto"


def test_peel_speaker_prefix_prefers_longest_name() -> None:
    ana = Person(id="ana", name="Ana")
    ana_costa = Person(id="costa", name="Ana Costa")
    text, speaker = peel_speaker_prefix("Ana Costa: pronto", [ana, ana_costa])
    assert speaker == "costa"
    assert text == "pronto"
