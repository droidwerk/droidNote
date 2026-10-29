from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from types import SimpleNamespace

from app.application.brief import BriefService
from app.application.chat import ChatService
from app.application.mindmap import MindMapService, build_map, split_stamp, to_markdown
from app.application.memory import MemoryService, match_task
from app.application.summarize import SummarizeService
from app.application.tasks import TaskService
from app.domain.models import ActionItem, Session, Summary, TranscriptSegment
from app.infrastructure.persistence.sqlite import SqliteStore, new_id
from tests.conftest import auth
from tests.fakes import FakeLlm


class _RecordingLlm(FakeLlm):
    def __init__(self, payload: str | None = None) -> None:
        super().__init__(payload)
        self.prompts: list[str] = []

    async def generate_json(self, prompt: str, *, system: str | None = None) -> str:
        self.prompts.append(prompt)
        return await super().generate_json(prompt, system=system)

    async def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        self.prompts.append(prompt)
        return await super().generate_text(prompt, system=system)


async def _ready() -> SimpleNamespace:
    return SimpleNamespace(summarize_ready=True, llm=SimpleNamespace(message=""))


async def _store(tmp_path) -> SqliteStore:
    store = SqliteStore(tmp_path / "db.sqlite")
    await store.initialize()
    return store


async def _session(store: SqliteStore, title: str, *, days_ago: float = 0, language: str = "pt") -> Session:
    started = datetime.now(tz=UTC) - timedelta(days=days_ago)
    session = Session(
        id=new_id(),
        title=title,
        started_at=started,
        ended_at=started + timedelta(minutes=30),
        status="stopped",
        language=language,
    )
    await store.create_session(session)
    return session


async def _speech(store: SqliteStore, session_id: str, lines: list[tuple[int, str]]) -> list[TranscriptSegment]:
    out = []
    for start, text in lines:
        segment = TranscriptSegment(
            id=new_id(), session_id=session_id, start_ms=start, end_ms=start + 4_000, text=text, language="pt"
        )
        await store.add_segment(segment)
        out.append(segment)
    return out


async def _summary(
    store: SqliteStore,
    session_id: str,
    *,
    decisions: list[str] = (),
    open_items: list[str] = (),
    actions: list[str] = (),
    overview: str = "Reunião.",
) -> Summary:
    summary = Summary(
        id=new_id(),
        session_id=session_id,
        highlights=[],
        decisions=list(decisions),
        action_items=[ActionItem(text=item, owner="Ana") for item in actions],
        raw_text="{}",
        created_at=datetime.now(tz=UTC),
        overview=overview,
        open_items=list(open_items),
    )
    await store.save_summary(summary)
    return summary


# ------------------------------------------------------------ mapa mental


def test_split_stamp_reads_the_last_time_mark() -> None:
    assert split_stamp("Fechar o piloto (12:40)") == ("Fechar o piloto", 760_000)
    assert split_stamp("Sem marca") == ("Sem marca", None)
    assert split_stamp("Duas (01:00) marcas (1:02:03)") == ("Duas marcas", 3_723_000)


async def test_mindmap_is_built_from_minutes_and_keeps_edits(tmp_path) -> None:
    store = await _store(tmp_path)
    session = await _session(store, "Kickoff Atlas")
    await _summary(
        store,
        session.id,
        decisions=["Migrar para Postgres (12:10)"],
        open_items=["Definir SLA (20:00)"],
        actions=["Criar tabela (13:00)"],
    )
    await TaskService(store).sync_from_summary(session.id, [ActionItem("Criar tabela", "Ana")])
    service = MindMapService(store)

    first = await service.get(session.id)
    root = first.data["nodeData"]
    assert first.origin == "auto" and root["topic"] == "Kickoff Atlas"
    branches = [child["topic"] for child in root["children"]]
    assert branches == ["Decisões", "Ações", "Pendências"]
    decision = root["children"][0]["children"][0]
    assert decision["topic"] == "Migrar para Postgres"
    assert decision["metadata"] == {"kind": "decision", "at_ms": 730_000}
    assert decision["tags"] == ["12:10"]
    task = root["children"][1]["children"][0]
    assert task["metadata"]["kind"] == "task" and task["metadata"]["task_id"]
    assert "- Migrar para Postgres (12:10)" in to_markdown(first.data)

    # A pessoa edita: a edição fica, mesmo quando a ata muda.
    edited = dict(first.data)
    edited["nodeData"] = dict(root, children=root["children"][:1] + [{"id": "mine", "topic": "Meu ramo", "children": []}])
    saved = await service.save(session.id, edited)
    assert saved.origin == "edited"
    await _summary(store, session.id, decisions=["Outra decisão"], overview="Mudou.")
    assert (await service.get(session.id)).origin == "edited"
    # Refazer da ata volta ao automático com a ata nova.
    rebuilt = await service.reset(session.id)
    assert rebuilt.origin == "auto"
    assert rebuilt.data["nodeData"]["children"][0]["children"][0]["topic"] == "Outra decisão"


async def test_mindmap_refine_keeps_leaves_by_ref_and_restores_forgotten_ones(tmp_path) -> None:
    store = await _store(tmp_path)
    session = await _session(store, "Aula de grafos")
    await _summary(store, session.id, decisions=["Usar Dijkstra (05:00)", "Evitar pesos negativos (06:00)"])
    plan = json.dumps({"root": {"topic": "x", "ref": None, "children": [
        {"topic": "Algoritmos", "ref": None, "children": [{"topic": "Dijkstra", "ref": "n2", "children": []}]},
    ]}})
    service = MindMapService(store, _RecordingLlm(plan))
    refined = await service.refine(session.id)
    root = refined.data["nodeData"]
    assert refined.origin == "ai" and root["topic"] == "Aula de grafos"
    group = root["children"][0]
    assert group["topic"] == "Algoritmos" and group["metadata"]["kind"] == "ai"
    kept = group["children"][0]
    assert kept["id"] == "n2" and kept["topic"] == "Dijkstra" and kept["metadata"]["at_ms"] == 300_000
    # A folha esquecida pela IA (06:00) volta num ramo no fim.
    lost = root["children"][-1]["children"]
    assert [item["topic"] for item in lost] == ["Evitar pesos negativos"]


async def test_mindmap_endpoints(client: AsyncClient, app) -> None:
    container = app.state.container
    container.setup.status = _ready
    store: SqliteStore = container.store
    session = await _session(store, "Daily")
    await _summary(store, session.id, decisions=["Decisão A (00:10)"])
    first = await client.get(f"/sessions/{session.id}/mindmap", headers=auth())
    assert first.status_code == 200 and first.json()["origin"] == "auto"
    data = first.json()["data"]
    data["nodeData"]["children"].append({"id": "mine", "topic": "Ideia minha", "children": []})
    saved = await client.put(f"/sessions/{session.id}/mindmap", headers=auth(), json={"data": data})
    assert saved.status_code == 200 and saved.json()["origin"] == "edited"
    assert "Ideia minha" in saved.json()["markdown"]
    reset = await client.post(f"/sessions/{session.id}/mindmap/reset", headers=auth())
    assert reset.json()["origin"] == "auto"
    bad = await client.put(f"/sessions/{session.id}/mindmap", headers=auth(), json={"data": {"x": 1}})
    assert bad.status_code == 422


# --------------------------------------------------------------- memória

MEMORY_JSON = json.dumps(
    {
        "language": "pt",
        "resolved": [{"item": "Criar tabela de clientes", "how": "Tabela criada e revisada."}],
        "still_open": ["Definir SLA"],
        "changed": [{"before": "Migrar para Postgres", "now": "Migração adiada para o Q1"}],
        "new_items": ["Contratar DBA"],
        "watch": ["Cobrar o SLA"],
    }
)


async def _series(store: SqliteStore) -> tuple[Session, Session]:
    previous = await _session(store, "Daily dados · 20/10", days_ago=7)
    await _summary(
        store,
        previous.id,
        decisions=["Migrar para Postgres (12:10)"],
        open_items=["Definir SLA", "Criar tabela de clientes"],
        actions=["Criar tabela de clientes"],
    )
    await TaskService(store).sync_from_summary(previous.id, [ActionItem("Criar tabela de clientes", "Ana")])
    current = await _session(store, "Daily dados · 27/10")
    return previous, current


async def test_memory_before_minutes_is_deterministic_and_after_uses_ai_once(tmp_path) -> None:
    store = await _store(tmp_path)
    previous, current = await _series(store)
    llm = _RecordingLlm(MEMORY_JSON)
    service = MemoryService(llm, store, BriefService(store))

    before = await service.recall(current.id)
    assert before.mode == "before" and not before.generated
    assert [item.session_id for item in before.thread] == [previous.id]
    assert before.still_open == ["Definir SLA", "Criar tabela de clientes"]
    assert before.watch == ["Migrar para Postgres"]
    assert [task.text for task in before.pending] == ["Criar tabela de clientes"]
    # Sem ata ainda, comparar não chama a IA.
    assert (await service.compare(current.id)).mode == "before"
    assert llm.prompts == []

    await _summary(store, current.id, decisions=["Migração adiada para o Q1"], overview="Fizemos a tabela.")
    pending = await service.recall(current.id)
    assert pending.mode == "after" and not pending.generated

    after = await service.compare(current.id)
    assert after.generated and after.mode == "after"
    assert after.resolved[0].item == "Criar tabela de clientes"
    assert after.resolved[0].task_id == before.pending[0].id
    assert after.changed[0].now == "Migração adiada para o Q1"
    assert after.new_items == ["Contratar DBA"]
    assert len(llm.prompts) == 1
    assert "Migrar para Postgres" in llm.prompts[0] and "Fizemos a tabela." in llm.prompts[0]

    # Mesmas atas: resultado guardado, nenhuma chamada nova.
    again = await service.compare(current.id)
    assert again.generated and len(llm.prompts) == 1
    assert (await service.recall(current.id)).generated

    # Ata regenerada: a memória antiga aparece como desatualizada até comparar de novo.
    await _summary(store, current.id, decisions=["Outra decisão"], overview="Mudou.")
    stale = await service.recall(current.id)
    assert stale.generated and stale.stale
    fresh = await service.compare(current.id)
    assert not fresh.stale and len(llm.prompts) == 2


def test_match_task_tolerates_wording_differences() -> None:
    from app.domain.models import TaskItem

    now = datetime.now(tz=UTC)
    tasks = [
        TaskItem(id="t1", text="Criar tabela de clientes", created_at=now),
        TaskItem(id="t2", text="Enviar proposta para a Bia", created_at=now),
    ]
    assert match_task("criar a tabela de clientes (12:40)", tasks) == "t1"
    assert match_task("Proposta enviada para a Bia", tasks) == "t2"
    assert match_task("Comprar café", tasks) is None


async def test_memory_endpoint_and_minutes_prompt_carry_the_series(client: AsyncClient, app) -> None:
    container = app.state.container
    container.setup.status = _ready  # não depende de um Ollama de verdade na máquina
    store: SqliteStore = container.store
    previous, current = await _series(store)
    await _speech(store, current.id, [(1_000, "A tabela de clientes ficou pronta ontem.")])
    llm = _RecordingLlm()
    memory = MemoryService(_RecordingLlm(MEMORY_JSON), store, BriefService(store))
    container.memory = memory
    container.summarize = SummarizeService(llm, store, TaskService(store), memory=memory)

    first = await client.get(f"/sessions/{current.id}/memory", headers=auth())
    assert first.status_code == 200
    assert first.json()["mode"] == "before"
    assert [item["session_id"] for item in first.json()["thread"]] == [previous.id]
    assert first.json()["pending"][0]["session_title"] == previous.title

    # A ata da reunião atual recebe as decisões e pendências anteriores da série.
    await container.summarize.summarize(current.id)
    assert "Reuniões anteriores desta mesma série" in llm.prompts[-1]
    assert "pendência: Definir SLA" in llm.prompts[-1]

    compared = await client.post(f"/sessions/{current.id}/memory", headers=auth())
    assert compared.status_code == 200
    body = compared.json()
    assert body["generated"] and body["mode"] == "after"
    assert body["resolved"][0]["task_id"] == first.json()["pending"][0]["id"]
    assert body["watch"] == ["Cobrar o SLA"]


async def test_chat_context_includes_earlier_meetings_of_the_series(tmp_path) -> None:
    store = await _store(tmp_path)
    previous, current = await _series(store)
    await _speech(store, current.id, [(1_000, "Hoje falamos do SLA.")])
    llm = _RecordingLlm()
    memory = MemoryService(_RecordingLlm(MEMORY_JSON), store, BriefService(store))
    chat = ChatService(llm, store, memory=memory)
    await chat.ask("O que mudou desde a última reunião?", session_id=current.id)
    prompt = llm.prompts[-1]
    assert "Earlier meetings in the same series" in prompt
    assert previous.title in prompt
    assert "open: Definir SLA" in prompt
