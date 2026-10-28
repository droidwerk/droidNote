from __future__ import annotations

from app.application.summarize import parse_summary_json


def test_parse_summary_json_extracts_blocks() -> None:
    raw = """
    aqui vai o json
    {
      "highlights": ["A", "B"],
      "decisions": ["C"],
      "action_items": [{"text": "D", "owner": "Eva"}, "E"]
    }
    extra
    """
    parsed = parse_summary_json(raw)
    assert parsed["highlights"] == ["A", "B"]
    assert parsed["decisions"] == ["C"]
    assert parsed["action_items"][0].text == "D"
    assert parsed["action_items"][0].owner == "Eva"
    assert parsed["action_items"][1].text == "E"


def test_parse_summary_json_handles_garbage() -> None:
    parsed = parse_summary_json("not json")
    assert parsed["highlights"] == []
    assert parsed["decisions"] == []
    assert parsed["action_items"] == []


def test_parse_summary_json_drops_repeated_lines() -> None:
    raw = """{
      "overview": "Reunião sobre o projeto.",
      "topics": [{"title": "Projeto", "points": ["Reunião sobre o projeto.", "Prazo em março (01:10)", "prazo em março"]}],
      "highlights": ["X", "x.", "Y"],
      "decisions": ["Fechar piloto", "Fechar piloto (02:00)"],
      "open_items": ["Orçamento", "Orçamento"]
    }"""
    parsed = parse_summary_json(raw)
    assert parsed["topics"][0].points == ["Prazo em março (01:10)"]
    assert parsed["highlights"] == ["X", "Y"]
    assert parsed["decisions"] == ["Fechar piloto"]
    assert parsed["open_items"] == ["Orçamento"]
