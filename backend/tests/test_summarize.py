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
