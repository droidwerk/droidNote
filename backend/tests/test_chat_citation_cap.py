"""Teto de 3 [n] por linha na resposta do chat. Função pura, sem LLM."""

from __future__ import annotations

import re

from app.application.chat import _cap_citations

CITE = re.compile(r"\[(\d{1,2})\]")
EXCERPTS = ["fala sobre clima e futebol"] * 25


def test_line_with_25_cites_keeps_3_most_relevant() -> None:
    excerpts = list(EXCERPTS)
    excerpts[6] = "a fila de envio duplica e-mail"  # [7]
    excerpts[11] = "notificacoes por e-mail duplicadas na fila"  # [12]
    excerpts[19] = "corrigir a fila"  # [20]
    cites = "".join(f" [{n}]" for n in range(1, 26))
    out = _cap_citations(f"- Corrigir a fila de e-mail duplicado{cites}.", excerpts)
    assert [int(n) for n in CITE.findall(out)] == [7, 12, 20]
    assert out == "- Corrigir a fila de e-mail duplicado [7] [12] [20]."


def test_three_or_fewer_unchanged_and_ties_keep_order() -> None:
    line = "Texto [1] [2][3]."
    assert _cap_citations(line, EXCERPTS) == line
    assert CITE.findall(_cap_citations("x [5] [4] [3] [2] [1]", EXCERPTS)) == ["5", "4", "3"]


def test_code_block_lines_capped_inline_code_untouched() -> None:
    text = "```prompt\nRevise a fila [1] [2] [3] [4] [5]\n```\nUse `a[1] [2] [3] [4]` aqui [9]."
    lines = _cap_citations(text, EXCERPTS).split("\n")
    assert len(CITE.findall(lines[1])) == 3
    assert lines[3] == "Use `a[1] [2] [3] [4]` aqui [9]."
