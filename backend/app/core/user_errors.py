from __future__ import annotations


def explain(happened: str, *, severe: bool, app_will: str, user_can: str) -> str:
    """Erro para humano: o que houve, gravidade, o que o app faz, o que fazer."""
    gravity = (
        "Isso impede o DroidNote de continuar agora."
        if severe
        else "Não é grave: o resto do aplicativo segue."
    )
    parts = [happened.strip(), gravity, app_will.strip(), user_can.strip()]
    return " ".join(part for part in parts if part)
