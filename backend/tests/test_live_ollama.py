"""Aceite ao vivo do chat contra o Ollama local (gemma4:e4b). Opt-in: DROIDNOTE_LIVE_OLLAMA=1.

Dados fictícios só. Banco temporário em tmp_path. Fora da suíte padrão (pulado sem a variável).
Como rodar: docs/technology/ai/chat-modes.md, seção "Live check".
"""
from __future__ import annotations

import os
import random
import re
from datetime import UTC, datetime, timedelta

import pytest

from app.application.chat import ChatService
from app.domain.models import Session, TranscriptSegment
from app.infrastructure.llm.ollama_manager import OllamaManager
from app.infrastructure.persistence.sqlite import SqliteStore, new_id

pytestmark = pytest.mark.skipif(
    os.environ.get("DROIDNOTE_LIVE_OLLAMA") != "1", reason="live Ollama check: set DROIDNOTE_LIVE_OLLAMA=1"
)

OLLAMA_URL = os.environ.get("DROIDNOTE_LIVE_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("DROIDNOTE_LIVE_OLLAMA_MODEL", "gemma4:e4b")
TITLE = "Sprint review and indexing session"

BUGS = [
    (12 * 60 + 4, "bug no login: quando a senha tem acento o formulario da erro 500. Vou corrigir isso hoje no validador de senha."),
    (31 * 60 + 8, "outro bug: o relatorio mensal exporta o PDF com as datas trocadas, dia e mes invertidos. Preciso corrigir o formato da data."),
    (47 * 60 + 12, "encontrei um erro no upload de fotos: arquivo acima de 10 MB trava a tela sem mensagem. Vou corrigir com um limite e um aviso."),
    (58 * 60 + 0, "ultimo bug: as notificacoes por e-mail estao saindo duplicadas para cada cliente. Vou corrigir a fila de envio."),
]
DECISION = (40 * 60, "Decidimos entao: a versao 3.2 sai na sexta-feira, sem o modulo novo de relatorios, que fica para a 3.3.")
# Um padrão por bug plantado, na ordem de BUGS.
# Pega o bug ou a correção dita no mesmo trecho (o modelo às vezes cita só "Vou corrigir a fila de envio").
BUG_HITS = [
    r"login|senha|acento",
    r"pdf|relat[oó]rio|data",
    r"upload|foto|10 ?mb|limite e (um )?aviso",
    r"notifica|e-?mail|duplicad|fila de envio",
]

LECTURE = [
    "Um indice B-tree guarda as chaves ordenadas em paginas, e a busca desce da raiz ate a folha em poucos saltos.",
    "A seletividade de uma coluna e a fracao de linhas distintas; coluna com alta seletividade e boa candidata a indice.",
    "No indice composto a ordem das colunas importa: a regra do prefixo mais a esquerda decide se o indice e usado.",
    "Um indice cobrindo tem todas as colunas que a consulta precisa, entao o banco nem visita a tabela.",
    "Cada indice extra deixa a escrita mais lenta, porque todo INSERT e UPDATE tambem atualiza o indice.",
    "O plano de execucao, que se ve com EXPLAIN, mostra se a consulta fez varredura completa ou busca por indice.",
    "Indice hash so serve para igualdade; para intervalo, como datas entre duas pontas, use B-tree.",
    "Funcao aplicada na coluna, tipo LOWER(email), impede o uso do indice comum; entra o indice por expressao.",
    "Estatisticas desatualizadas fazem o otimizador escolher o plano errado; rode ANALYZE depois de carga grande.",
    "Fragmentacao acontece quando paginas ficam meio vazias depois de muitos DELETE; reindexar recupera espaco.",
]
CHATTER_ANA = [
    "Eu revisei a tela de cadastro ontem e o fluxo ficou mais simples para o cliente.",
    "Concordo, vale olhar o tempo de resposta da busca antes da demonstracao.",
    "Eu posso preparar o roteiro de testes da semana e mandar no canal do time.",
    "Na minha visao o painel de vendas precisa de um filtro por regiao.",
    "Eu conversei com o suporte e eles pediram um atalho para exportar a planilha.",
    "Faz sentido, eu anoto isso na pauta da proxima reuniao.",
    "Eu testei no celular e a navegacao lateral abriu normal.",
    "Pode deixar que eu atualizo a documentacao do endpoint de pedidos.",
]
CHATTER_CARLA = [
    "Pessoal, vamos manter o foco no cronograma da entrega.",
    "O cliente piloto pediu uma reuniao de acompanhamento na semana que vem.",
    "Eu preciso do status de cada frente ate quinta.",
    "A equipe de design mandou as telas novas do painel.",
    "Bruno, segue com a parte de indices que ajuda a gente na consulta lenta.",
]

# Citação por tempo, etiqueta interna do contexto ou linha de rótulo copiada.
LEAKS = re.compile(r"\[\d{1,2}:\d{2}\]|\[(search|focused lecture|user speech)\]|" + re.escape(TITLE) + r" ·")
PROMPT_LINE = re.compile(r"^```prompt[ \t]*$", re.M)
# Títulos do plano de 6 partes (pt ou en): problema, o que sabemos, causas, plano, perguntas em aberto.
OUTLINE = [
    r"problema|problem\b",
    r"o que (j[aá] )?sabemos|what we know",
    r"causas|causes",
    r"\bplano\b|\bplan\b",
    r"perguntas|quest[oõ]es|d[uú]vidas|open questions",
]


def _segments(session_id: str, ids: dict[str, str]) -> list[TranscriptSegment]:
    rnd = random.Random(7)
    planted = {t: ("ana", txt) for t, txt in BUGS}
    planted[DECISION[0]] = ("carla", DECISION[1])
    segs = []
    for i in range(900):  # 60 min, um trecho a cada 4 s
        start = i * 4
        who = text = None
        for t in list(planted):
            if t <= start < t + 4:
                who, text = planted.pop(t)
        if who is None:
            r = rnd.random()
            if r < 0.42:
                who, text = "ana", rnd.choice(CHATTER_ANA) + " " + rnd.choice(CHATTER_ANA)
            elif r < 0.85:
                who, text = "bruno", rnd.choice(LECTURE)
            else:
                who, text = "carla", rnd.choice(CHATTER_CARLA)
        segs.append(TranscriptSegment(
            id=new_id(), session_id=session_id, start_ms=start * 1000, end_ms=start * 1000 + 3500, text=text,
            language="pt", speaker_id=ids[who], source="mic" if who == "ana" else "loopback",
        ))
    assert not planted
    return segs


@pytest.fixture
def llm() -> OllamaManager:
    return OllamaManager(OLLAMA_URL, OLLAMA_MODEL)


@pytest.fixture
async def meeting(tmp_path):
    store = SqliteStore(tmp_path / "meeting.db")
    await store.initialize()
    ids = {k: (await store.create_person(n)).id for k, n in
           [("ana", "Ana Costa"), ("bruno", "Bruno Lima"), ("carla", "Carla Mendes")]}
    await store.set_setting("self_person_id", ids["ana"])
    now = datetime.now(tz=UTC)
    sess = Session(id=new_id(), title=TITLE, started_at=now - timedelta(hours=2),
                   ended_at=now - timedelta(hours=1), status="stopped", language="pt")
    await store.create_session(sess)
    for s in _segments(sess.id, ids):
        await store.add_segment(s)
    yield store, sess.id
    if hasattr(store, "close"):
        await store.close()


async def _ask(svc: ChatService, msg: str, **kw):
    chat, m, _ = await svc.ask(msg, on_token=lambda _t: None, ui_language="pt", **kw)
    assert not LEAKS.search(m.content), m.content
    return chat, m.content


def _bugs_found(answer: str) -> int:
    low = answer.lower()
    return sum(bool(re.search(p, low)) for p in BUG_HITS)


async def test_q1_bugs_i_reported(llm, meeting) -> None:
    store, sid = meeting
    _, ans = await _ask(ChatService(llm, store), "Quais foram os bugs que eu relatei nessa conversa?", session_id=sid)
    assert _bugs_found(ans) >= 3, ans


async def test_q2_everything_i_said_i_would_fix(llm, meeting) -> None:
    store, sid = meeting
    _, ans = await _ask(ChatService(llm, store), "Quero uma lista de tudo o que eu falei que ia corrigir", session_id=sid)
    assert _bugs_found(ans) >= 3, ans


async def test_q3_flashcards_answers_below_rule(llm, meeting) -> None:
    store, sid = meeting
    _, ans = await _ask(
        ChatService(llm, store),
        "Crie flashcards para revisar este conteudo: uma tabela com as colunas Pergunta e Resposta.",
        session_id=sid, command="flashcards", style="study",
    )
    parts = re.split(r"^\s*---\s*$", ans, flags=re.M)
    assert len(parts) >= 2, ans
    above, below = "---".join(parts[:-1]), parts[-1]
    assert not re.search(r"\|\s*respostas?\s*\|", above, re.I), ans  # tabela sem coluna de resposta
    assert re.search(r"^\s*1[.)]", below, re.M), ans


async def test_q4_solve_without_source_says_conversa(llm, tmp_path) -> None:
    empty = SqliteStore(tmp_path / "empty.db")
    await empty.initialize()
    _, ans = await _ask(ChatService(llm, empty), "como resolvo o problema de cache do servidor X?", style="solve")
    assert "```" not in ans and not re.search(r"\bplano\b|\bplan\b", ans, re.I), ans
    assert "conversa" in ans.lower(), ans


async def test_q5_solve_plan_then_follow_up(llm, meeting) -> None:
    store, sid = meeting
    svc = ChatService(llm, store)
    chat, plan = await _ask(svc, "Como resolvo o bug das notificacoes por e-mail duplicadas?", session_id=sid, style="solve")
    low = plan.lower()
    assert all(re.search(p, low) for p in OUTLINE), plan
    assert PROMPT_LINE.search(plan), plan  # 6ª parte

    _, follow = await _ask(svc, "E como eu testo essa correcao antes de subir?", session_id=sid, style="solve", chat_id=chat.id)
    headings = [ln for ln in follow.splitlines() if re.match(r"\s*(#+|\d+[.)]\s*\*\*|\*\*)", ln)]
    repeated = sum(any(re.search(p, h.lower()) for h in headings) for p in OUTLINE[1:])
    assert repeated <= 1, follow  # sem refazer o esqueleto
    if "```prompt" in follow:
        assert PROMPT_LINE.search(follow), follow
    for text in (plan, follow):  # teto de citações por linha (bullet, prosa, bloco prompt)
        assert all(len(re.findall(r"\[\d{1,2}\]", ln)) <= 3 for ln in text.splitlines()), text
