# Memória da série: a pasta manda

## O que mudou

`BriefService.for_session` (backend/app/application/brief.py) passa as pastas da reunião
para `build` (argumento `folder_ids`). Quando a reunião está em ao menos uma pasta:

- só entra na série a reunião anterior que divide uma pasta com ela;
- título e pessoas deixam de bastar; uma reunião com as mesmas pessoas em outra pasta não entra;
- o motivo exibido é sempre `"folder"`, mesmo que título ou pessoas também batam;
- a ordem continua a mesma: mais recente primeiro, sem ata nem tarefas no fim, no máximo 3.

Reunião sem pasta e o caminho do calendário (`for_title`) seguem exatamente como antes.

As pastas de todas as sessões vêm numa consulta só (`SqliteStore.tags_by_session_ids`, já existente).

## Contrato

`reason` em `RelatedMeetingOut` e na memória da série: `"folder" | "title" | "people" | "both"`.
O texto do pedido da ata agora diz "mesma pasta, mesmo título ou mesmas pessoas".

## Por quê

Pasta é escolha explícita do usuário. "Elevai - Refinamentos" ligava a uma reunião sem relação
só por ter as mesmas pessoas e perdia uma reunião da própria pasta com título diferente.

## Como rodar

```
cd backend
uv run pytest -q tests/test_mindmap_memory.py -k folder
```
