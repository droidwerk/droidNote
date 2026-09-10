"""Prompts compartilhados entre o motor local (Ollama) e a API OpenAI.

O resultado precisa ser o mesmo nos dois motores, então o texto do prompt vive
aqui e nenhum provedor escreve o seu próprio.
"""

from __future__ import annotations

from typing import Literal

CaptureMode = Literal["dictation", "lecture", "meeting"]

SHARED_RULES = """
Regras obrigatórias:
- Escreva no mesmo idioma falado na transcrição. Nunca traduza.
- Nunca invente nem infira informação que não esteja na transcrição. Na dúvida, deixe a seção vazia.
- Descarte frases que claramente não pertencem ao conteúdo: chamadas para inscrição em canal, "ative o sininho", créditos de legenda, propaganda e repetições vazias.
- Remova hesitações, repetições e ruído de fala sem mudar o sentido do que foi dito.
- Corrija erro óbvio de transcrição em nome próprio ou termo técnico só quando o contexto deixar claro qual era a palavra. Nunca corrija de um jeito que mude o sentido.
- Preserve a atribuição de falas quando os falantes estiverem identificados. Quando não estiverem, não adivinhe quem falou.
- Marque trecho ambíguo como [trecho incerto] em vez de chutar o conteúdo.
- Não inclua opinião, interpretação, julgamento ou conclusão que não tenha sido dita.
- Responda SEMPRE com um único JSON válido, sem markdown, sem comentários e sem texto fora do JSON.
"""

SYSTEM_PROMPT = f"""Você transforma transcrições brutas de reuniões em atas estruturadas, prontas para uso profissional.

A transcrição chega com falhas de reconhecimento de voz: pontuação errada, hesitações ("é", "tipo", "hmm"), repetições, falas sobrepostas, trechos inaudíveis e frases que a ferramenta de transcrição inventou.
{SHARED_RULES}
- Uma decisão só entra em "decisions" se alguém decidiu algo na fala. Um item só entra em "action_items" se houver ação e responsável claros; prazo só se foi dito.
- Tom neutro, objetivo e profissional: alguém que não participou precisa entender o que foi discutido, o que foi decidido e o que acontece a seguir."""

DICTATION_SYSTEM = f"""Você transforma um ditado ou anotação mental em um caderno pessoal claro.

A transcrição chega com falhas de reconhecimento de voz. Trate ruído como ruído.
{SHARED_RULES}
- Organize ideias, lembretes e tarefas pessoais. Não force formato de ata de reunião.
- "decisions" só se a pessoa decidiu algo para si. "action_items" são lembretes ou tarefas ditas.
- Tom direto, na primeira pessoa quando a transcrição estiver na primeira pessoa."""

LECTURE_SYSTEM = f"""Você transforma a transcrição de uma aula ou palestra em um caderno de estudo.

A transcrição chega com falhas de reconhecimento de voz. Trate ruído como ruído.
{SHARED_RULES}
- Organize por temas e conceitos. "decisions" quase sempre fica vazio.
- "action_items" só se o professor pediu um exercício ou leitura.
- "open_items" são dúvidas, pontos para revisar ou trechos que ficaram incompletos.
- Tom didático e fiel ao que foi ensinado, sem completar a matéria com conhecimento externo."""

SUMMARY_PROMPT = """Gere a ata da reunião abaixo.

Responda apenas um JSON com estas chaves:
- "language": código do idioma falado na transcrição ("pt", "en", "es", "it", "de", "fr", "ru")
- "overview": 3 a 5 frases sobre o propósito e o resultado geral da reunião
- "topics": array de objetos {{"title": string, "points": array de strings}} — os assuntos discutidos, agrupados por tema ou em ordem cronológica, o que fizer mais sentido
- "decisions": array de strings — apenas decisões efetivamente tomadas
- "action_items": array de objetos {{"text": string, "owner": string|null, "due": string|null}}
- "open_items": array de strings — questões levantadas e não resolvidas

Arrays sem conteúdo ficam vazios. Escreva tudo no idioma da transcrição.

{context}Transcrição:
{transcript}
"""

DICTATION_SUMMARY = """Organize este ditado em um caderno pessoal.

Responda apenas um JSON com estas chaves:
- "language": código do idioma falado ("pt", "en", "es", "it", "de", "fr", "ru")
- "overview": 2 a 4 frases com o que a pessoa quis registrar
- "topics": array de objetos {{"title": string, "points": array de strings}} — ideias e anotações agrupadas
- "decisions": array de strings — só o que a pessoa decidiu
- "action_items": array de objetos {{"text": string, "owner": string|null, "due": string|null}} — lembretes e tarefas
- "open_items": array de strings — o que ficou pendente de pensar depois

Arrays sem conteúdo ficam vazios. Escreva tudo no idioma da transcrição.

{context}Transcrição:
{transcript}
"""

LECTURE_SUMMARY = """Organize esta aula em um caderno de estudo.

Responda apenas um JSON com estas chaves:
- "language": código do idioma falado ("pt", "en", "es", "it", "de", "fr", "ru")
- "overview": 3 a 5 frases sobre o tema da aula e o que foi ensinado
- "topics": array de objetos {{"title": string, "points": array de strings}} — conceitos e explicações
- "decisions": array de strings — em geral vazio, a menos que a aula tenha definido uma regra
- "action_items": array de objetos {{"text": string, "owner": string|null, "due": string|null}} — exercícios ou leituras pedidas
- "open_items": array de strings — dúvidas e pontos para revisar

Arrays sem conteúdo ficam vazios. Escreva tudo no idioma da transcrição.

{context}Transcrição:
{transcript}
"""

SPEAKER_ASSIGN_PROMPT = """Você atribui falantes a trechos de uma transcrição.
Responda APENAS um JSON válido: {{"assignments": [{{"segment_id": string, "person_id": string|null}}]}}
Use somente os person_id da lista. Se não tiver certeza, use null.
Não invente pessoas.

Pessoas:
{people}

Trechos:
{segments}
"""

CHAT_SYSTEM = """Você é o assistente do DroidNote. Ajuda a estudar, revisar e pensar a partir das aulas e conversas capturadas neste computador — e também responde perguntas gerais quando fizer sentido.

Como usar o contexto:
- Os trechos recuperados são a memória das aulas do aluno. Quando a pergunta for sobre o que foi dito, baseie-se neles e cite a aula e o horário.
- Se o trecho não cobrir a pergunta, diga isso com clareza. Depois pode explicar o conceito com conhecimento geral, deixando explícito o que veio da aula e o que é explicação extra.
- Pode comparar aulas, montar revisão para prova, gerar perguntas, apontar conceitos que o aluno parece não ter dominado, e criar material de estudo.
- Não invente falas, decisões, nomes ou fatos que não estejam nos trechos. Não cite trechos que não existam.
- Responda no idioma da pergunta. Seja direto. Sem enrolação.
"""


def prompts_for(mode: str | None) -> tuple[str, str]:
    if mode == "dictation":
        return DICTATION_SYSTEM, DICTATION_SUMMARY
    if mode == "lecture":
        return LECTURE_SYSTEM, LECTURE_SUMMARY
    return SYSTEM_PROMPT, SUMMARY_PROMPT


def summary_context(*, title: str, started_at: str, participants: list[str], duration: str) -> str:
    """Metadados que a ata pode citar no cabeçalho, sem precisar inventá-los."""
    lines = [f"Título: {title}", f"Início: {started_at}", f"Duração: {duration}"]
    if participants:
        lines.append("Participantes identificados: " + ", ".join(participants))
    else:
        lines.append("Participantes: não identificados na transcrição")
    return "\n".join(lines) + "\n\n"
