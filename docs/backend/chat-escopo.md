# Chat: escopo das chamadas escolhidas

2026-11-13 · wo `chat-scope-selection`

## O que mudou

- `backend/app/application/chat.py` (`_answer`): a chamada em foco é `session_id` do pedido ou o
  primeiro id de `scope.session_ids` (desde `chat-backend-gaps`, o `focus_session_id` salvo não entra mais). Se há foco e o
  escopo veio vazio ("automático", `scope: null`), o escopo passa a ser só essa chamada.
- `_retrieve`: os acertos da busca são filtrados pelo escopo **antes** do corte de 24, para que
  acertos de outras chamadas não expulsem as escolhidas.
- `backend/app/schemas/api.py` (`ChatScopeIn.session_ids`): máximo de 20 ids (era 50).

## Por quê

Com uma chamada escolhida e escopo automático, a busca juntava trechos de todas as chamadas e o
catálogo listava todas. A resposta citava chamadas que o usuário não escolheu.

## Regras

| Pedido | O que a pergunta enxerga |
| --- | --- |
| Sem `session_id` e sem escopo | Todas as chamadas, mesmo que a conversa tenha `focus_session_id` salvo |
| Uma chamada (`session_id` ou `scope.session_ids=[id]`) | Só ela |
| N chamadas em `scope.session_ids` | Só elas; a primeira é a "em foco" (nota completa e memória da série), as demais entram com a nota resumida |
| Escopo amplo (dias, pessoa, etiqueta) sem `session_ids` | O escopo amplo vale |
| Escopo amplo **e** `session_ids` | Interseção dos dois |
| Conversa salva com `focus_session_id` | Não estreita nada. Só o pedido estreita; a tela manda os chips em toda pergunta |

Sempre valem: documentos anexados à conversa, material da chamada em foco e trechos marcados
pelo usuário (`segment_ids`).

## Como rodar

```
cd backend
uv run pytest -q tests/test_chat_scope.py
```

---

# Chat: renomear, parar e tentar de novo

2026-11-13 · wo `chat-backend-gaps`

## O que mudou

| Lacuna | Contrato |
| --- | --- |
| Renomear | `PATCH /chat/{chat_id}` com `{"title": "..."}`. O título é aparado; 1 a 120 caracteres depois de aparar. Resposta 200 com `ChatOut`. Conversa inexistente: 404. Título vazio ou longo: 422. `updated_at` não muda (a lista não reordena). Exige o token, como o resto de `/chat`. |
| Parar | Quando a tela fecha a conexão no meio do streaming de `POST /chat/ask`, o texto que já chegou é gravado como resposta do assistente com `interrupted: true` (campo novo em `ChatMessageOut`, `false` nas demais). Texto parcial vazio: nada é gravado além da pergunta. Conversa nova sem nenhuma mensagem gravada é apagada, como antes; com a pergunta gravada, ela fica. |
| Tentar de novo | Campo novo `retry: bool` (padrão `false`) em `POST /chat/ask`. Com `true`, se a última mensagem da conversa (`chat_id`) é do usuário, com o mesmo texto (aparado) e sem resposta depois, ela é reaproveitada e não se grava outra pergunta. Caso contrário o pedido segue normal. |

## Onde

- `backend/app/api/v1/endpoints/chat.py`: rota `PATCH /chat/{chat_id}` e repasse de `retry`.
- `backend/app/application/chat.py`: `ChatService.rename`; em `_answer`, os tokens são juntados e, em `asyncio.CancelledError`, o parcial é gravado com `asyncio.shield` (a gravação termina mesmo com cancelamento repetido do Starlette); `retry` pula a gravação da pergunta.
- `backend/app/infrastructure/persistence/sqlite.py`: coluna `chat_messages.interrupted INTEGER NOT NULL DEFAULT 0`, criada por `_ensure_column` na abertura do banco (bancos antigos ganham a coluna com 0).
- `backend/app/schemas/api.py`: `ChatRenameIn`, `ChatAskIn.retry`, `ChatMessageOut.interrupted`.

## Por quê

O frontend do Chat (`docs/frontend/chat-exit-beta.md`) não tinha como renomear, perdia a resposta parcial ao parar e duplicava a pergunta ao tentar de novo depois de um erro.

## Como rodar

```
cd backend
uv run pytest -q tests/test_chat_gaps.py
```

O teste `test_client_disconnect_mid_stream_saves_partial` chama a app ASGI com `spec_version` 2.3 (a do uvicorn) e manda `http.disconnect` depois do primeiro token.

## Rodada de correção (csq-revisor-diff)

- **Chips gravados na conversa**: coluna `chats.scope_session_ids` (texto JSON, padrão `'[]'`, criada por
  `_ensure_column`). Cada pergunta grava exatamente `scope.session_ids` do pedido (lista vazia quando
  `scope` é `null` ou vazio). `ChatOut` ganhou `scope_session_ids: list[str]`, em `GET /chat`,
  `GET /chat/{id}`, `PATCH /chat/{id}` e no evento `done`.
- **Sem fallback silencioso**: o `focus_session_id` salvo não estreita mais a busca. Ele continua no
  `ChatOut` (é a chamada de onde a conversa nasceu), mas só o pedido define o que a pergunta enxerga.
- **Id da conversa logo no início**: o primeiro evento SSE de `POST /chat/ask` é
  `data: {"chat_id": "<id>"}`, enviado assim que a conversa existe (nova ou a do `chat_id`) e antes
  de qualquer `token`. Depois vêm `{"token": "..."}`, e por fim `{"done": true, "chat": ..., "message": ..., "citations": [...]}`
  ou `{"error": "..."}`. Exceções: validação que falha antes da conversa existir (pergunta vazia,
  imagem grande demais, modelo sem visão, `chat_id` inexistente) manda só `{"error": ...}`. Se a
  conversa nova for parada antes de a pergunta ser gravada, ela é apagada e o id recebido deixa
  de existir (`GET /chat/{id}` responde 404).
