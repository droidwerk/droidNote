from __future__ import annotations

from app.core.user_errors import explain


def test_explain_has_four_parts() -> None:
    text = explain(
        "Faltou espaço em disco.",
        severe=True,
        app_will="O download não começou.",
        user_can="Liberar espaço e tentar de novo.",
    )
    assert "Faltou espaço em disco." in text
    assert "impede" in text
    assert "download não começou" in text
    assert "Liberar espaço" in text


def test_explain_mild_is_not_blocking() -> None:
    text = explain(
        "O microfone não apareceu.",
        severe=False,
        app_will="O DroidNote abre mesmo assim.",
        user_can="Ligue o microfone nas configurações do Windows.",
    )
    assert "Não é grave" in text
