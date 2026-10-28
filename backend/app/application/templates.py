"""Templates de nota e atalhos do chat.

Template de nota: define as seções de "topics" da ata. A IA segue a ordem e
deixa de fora o que a conversa não cobriu.
Atalho: uma pergunta salva para o chat ("escreva o e-mail de retorno").

Os embutidos são regravados a cada arranque (para receberem melhorias); os da
pessoa nunca são tocados. O nome exibido dos embutidos vem do i18n da UI pelo id.
"""

from __future__ import annotations

from app.domain.models import NoteTemplate
from app.infrastructure.persistence.sqlite import new_id

BUILTINS: tuple[NoteTemplate, ...] = (
    NoteTemplate(
        id="tpl-one-on-one",
        kind="note",
        name="1:1",
        capture_mode="meeting",
        position=1,
        builtin=True,
        body=(
            "Como a pessoa está\n"
            "Progresso desde a última conversa\n"
            "Bloqueios e pedidos de ajuda\n"
            "Feedback (dado e recebido)\n"
            "Carreira e desenvolvimento\n"
            "Próximos passos"
        ),
    ),
    NoteTemplate(
        id="tpl-sales",
        kind="note",
        name="Vendas / discovery",
        capture_mode="meeting",
        position=2,
        builtin=True,
        body=(
            "Contexto do cliente\n"
            "Dor e problema principal\n"
            "Solução atual e alternativas avaliadas\n"
            "Decisores, orçamento e prazo\n"
            "Resistências levantadas\n"
            "Próximos passos combinados"
        ),
    ),
    NoteTemplate(
        id="tpl-standup",
        kind="note",
        name="Daily / standup",
        capture_mode="meeting",
        position=3,
        builtin=True,
        body=(
            "Uma seção por pessoa, com o nome dela no título: o que fez, o que vai fazer, bloqueios\n"
            "Bloqueios que precisam de alguém de fora\n"
            "Combinados da equipe"
        ),
    ),
    NoteTemplate(
        id="tpl-interview",
        kind="note",
        name="Entrevista de candidato",
        capture_mode="meeting",
        position=4,
        builtin=True,
        body=(
            "Trajetória e experiência relatada\n"
            "Respostas técnicas (o que foi perguntado e o que a pessoa respondeu)\n"
            "Sinais de colaboração e comunicação citados na conversa\n"
            "Perguntas feitas pelo candidato\n"
            "Pontos a verificar na próxima etapa"
        ),
    ),
    NoteTemplate(
        id="tpl-project",
        kind="note",
        name="Reunião de projeto",
        capture_mode="meeting",
        position=5,
        builtin=True,
        body="Status por frente\nRiscos e dependências\nDecisões tomadas\nPendências e responsáveis",
    ),
    NoteTemplate(
        id="tpl-brainstorm",
        kind="note",
        name="Brainstorm",
        capture_mode="meeting",
        position=6,
        builtin=True,
        body="Problema em discussão\nIdeias levantadas, agrupadas por tema\nPrós e contras citados\nIdeias escolhidas para seguir",
    ),
    NoteTemplate(
        id="tpl-lecture",
        kind="note",
        name="Aula",
        capture_mode="lecture",
        position=7,
        builtin=True,
        body="Tema da aula\nConceitos e definições\nExemplos dados\nFórmulas, datas e nomes citados\nDúvidas e pontos para revisar",
    ),
    NoteTemplate(
        id="rcp-follow-up",
        kind="recipe",
        name="E-mail de retorno",
        position=1,
        builtin=True,
        body=(
            "Escreva um e-mail curto de retorno desta conversa para os participantes: agradecimento em uma linha, "
            "o que foi decidido, próximos passos com responsável e prazo. Só com o que foi dito."
        ),
    ),
    NoteTemplate(
        id="rcp-objections",
        kind="recipe",
        name="Resistências e respostas",
        position=2,
        builtin=True,
        body=(
            "Liste as objeções, dúvidas ou resistências levantadas nesta conversa, quem levantou, como foram "
            "respondidas e quais ficaram sem resposta. Cite o momento de cada uma."
        ),
    ),
    NoteTemplate(
        id="rcp-decisions",
        kind="recipe",
        name="Decisões e responsáveis",
        position=3,
        builtin=True,
        body="Monte uma tabela com cada decisão tomada, quem decidiu, o que muda e o próximo passo. Cite o momento.",
    ),
    NoteTemplate(
        id="rcp-exec-brief",
        kind="recipe",
        name="Resumo para quem não estava",
        position=4,
        builtin=True,
        body="Resuma em 5 bullets para alguém que não estava: o que foi discutido, o que mudou e o que esperam dessa pessoa.",
    ),
    NoteTemplate(
        id="rcp-study",
        kind="recipe",
        name="Perguntas de revisão",
        position=5,
        builtin=True,
        body=(
            "Crie 8 perguntas de revisão sobre esta aula, com a resposta curta logo abaixo de cada uma e o momento "
            "da aula em que o assunto aparece."
        ),
    ),
    NoteTemplate(
        id="rcp-risks",
        kind="recipe",
        name="Riscos e pontos de atenção",
        position=6,
        builtin=True,
        body="Quais riscos, prazos apertados, dependências ou sinais de alerta apareceram nesta conversa? Cite o momento.",
    ),
)


class TemplateService:
    def __init__(self, store: object) -> None:
        self._store = store

    async def ensure_builtins(self) -> None:
        for template in BUILTINS:
            await self._store.save_template(template)  # type: ignore[attr-defined]

    async def list(self, kind: str | None = None) -> list[NoteTemplate]:
        return await self._store.list_templates(kind)  # type: ignore[attr-defined]

    async def get(self, template_id: str) -> NoteTemplate | None:
        return await self._store.get_template(template_id)  # type: ignore[attr-defined]

    async def create(self, *, kind: str, name: str, body: str, capture_mode: str | None) -> NoteTemplate:
        template = NoteTemplate(
            id=new_id(),
            kind="recipe" if kind == "recipe" else "note",
            name=name.strip(),
            body=body.strip(),
            capture_mode=capture_mode or None,
            builtin=False,
            position=100,
        )
        if not template.name or not template.body:
            raise ValueError("Nome e conteúdo são obrigatórios")
        return await self._store.save_template(template)  # type: ignore[attr-defined]

    async def update(self, template_id: str, *, name: str | None, body: str | None, capture_mode: str | None) -> NoteTemplate:
        current = await self.get(template_id)
        if current is None:
            raise KeyError(template_id)
        if current.builtin:
            raise PermissionError(template_id)
        from dataclasses import replace

        updated = replace(
            current,
            name=(name or current.name).strip(),
            body=(body or current.body).strip(),
            capture_mode=capture_mode if capture_mode is not None else current.capture_mode,
        )
        return await self._store.save_template(updated)  # type: ignore[attr-defined]

    async def delete(self, template_id: str) -> None:
        current = await self.get(template_id)
        if current is None:
            raise KeyError(template_id)
        if current.builtin:
            raise PermissionError(template_id)
        await self._store.delete_template(template_id)  # type: ignore[attr-defined]
