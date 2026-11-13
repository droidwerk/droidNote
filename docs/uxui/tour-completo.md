# Tour completo do DroidNote

Ordem de serviço: `full-tour-script` (R2, aprovada pelo CEO). Documento de desenho. Não altera código.
Substitui o tour atual de 4 passos em `desktop/src/features/onboarding/Onboarding.tsx` (`TOUR`, linhas 103 a 108).

## 1. Problema e objetivo

O tour atual mostra 4 balões e cobre só Ao vivo, Conversas, abas e busca. O app tem muito mais: modos de gravação, Fontes, aviso de gravação, mini console, agenda, pastas, player, Quem falou quando, ata, anotações, contexto, mapa, memória, vozes, perguntas prontas, exportar, tarefas, chat com contexto, comandos, anexos, modos e fontes, preferências.

Objetivo: um tour que mostra o produto inteiro para quem não é técnico, sem atrapalhar.

- Dividido em capítulos, um por área. A pessoa escolhe o que quer ver.
- Cada capítulo pode ser pulado. O tour inteiro pode ser encerrado a qualquer momento com Esc.
- O tour retoma de onde parou.
- Cada tela tem um botão "?" que repete só o capítulo daquela tela.
- Nenhuma tela escura por cima, nenhum clique bloqueado. O balão fica ao lado do item.

## 2. Inventário usado

Lido em `desktop/src` em 2026-11-13. Só entra no tour o que existe no código.

| Área | O que existe | Onde |
|---|---|---|
| Barra lateral | Menu (Ao vivo, Conversas, Tarefas, Chat, Preferências, Ajuda), Recentes por dia, Ver todas, troca Modelos locais / OpenAI, recolher (Ctrl B) | `app/App.tsx:746-814`, `shared/ui/EngineSwitch.tsx` |
| Faixa de status | Estado (gravando ou em espera), privacidade local/nuvem, Buscar em tudo (Ctrl K) | `shared/ui/StatusStrip.tsx` |
| Ao vivo | Tipo (Ditado, Aula, Reunião), idioma da fala, modelo da ata, Fontes (som do PC, só microfone, quem é você, quem está na sala), botão Gravar (Ctrl Shift R), Aviso de gravação, Mini console, Próximas reuniões (agenda), transcrição ao vivo, abas laterais | `pages/LivePage.tsx`, `features/capture/*`, `features/brief/UpcomingPanel.tsx` |
| Conversas | Pastas (criar, renomear, apagar, arrastar), Todas, Sem pasta, busca, ordem, seleção múltipla (mover, apagar) | `pages/LibraryPage.tsx` |
| Conversa | Renomear, pasta, Perguntar, Perguntas prontas, Exportar (ata, transcrição ou tudo), apagar, player, Quem falou quando, transcrição (busca, recolher, corrigir pessoa com 1 a 9), abas Documento (Ata), Anotações, Contexto, Mapa, Memória, Vozes | `pages/SessionPage.tsx` |
| Tarefas | Nova tarefa com responsável, filtros Abertas / Feitas / Todas, filtro por pessoa, busca, marcar feita, link para a conversa de origem | `pages/TasksPage.tsx` |
| Chat | Histórico de chats, Gravações recentes como contexto (várias), Materiais de estudo e comandos com /, Perguntas prontas, anexar arquivo, imagem, link ou YouTube, Opções da resposta (modo Normal, Rápido, Estudar, Resolver; Só fontes; Onde procurar), fontes numeradas, salvar resposta | `pages/ChatPage.tsx`, `features/chat/*` |
| Preferências | Abas Transcrição (Modelos locais ou OpenAI, chave, selo da chave, modelos), Idioma, Aparência (tema), Pessoas e vozes, Reuniões (agenda, aviso, retenção), Templates, Arquivos, Privacidade, Sobre | `pages/SettingsPage.tsx:54-64` |
| Ajuda | Manual, atalhos, dúvidas, refazer o tour, informar problema | `pages/HelpPage.tsx` |

## 3. Estrutura

9 capítulos, 41 passos. Nenhum capítulo passa de 6 passos.

| # | id | Capítulo | Tela | Passos |
|---|---|---|---|---|
| 1 | `basico` | O básico | qualquer | 4 |
| 2 | `preparar` | Antes de gravar | Ao vivo | 4 |
| 3 | `gravar` | Gravar | Ao vivo | 4 |
| 4 | `conversas` | Suas conversas | Conversas | 4 |
| 5 | `conversa` | Dentro de uma conversa | Conversa | 5 |
| 6 | `abas` | Ata e abas | Conversa | 6 |
| 7 | `tarefas` | Tarefas | Tarefas | 3 |
| 8 | `chat` | Chat | Chat | 6 |
| 9 | `preferencias` | Preferências | Preferências | 5 |

Capítulo 5 e 6 precisam de pelo menos uma conversa gravada. Ver seção 6.

## 4. Roteiro passo a passo

Convenções:

- `view`: valor de `View` em `App.tsx:32` para onde o tour navega antes do passo. "manter" = não troca de tela.
- `âncora`: seletor procurado com `document.querySelector`. Quando é `[data-tour="x"]`, o atributo precisa ser adicionado no arquivo indicado.
- `se faltar`: o que fazer quando a âncora não existe na tela.
- Texto final em português. Título com no máximo 5 palavras. Corpo com no máximo 2 frases curtas.

### Capítulo 1. O básico (`basico`)

| id | view | âncora | onde pôr | título | corpo | se faltar |
|---|---|---|---|---|---|---|
| `basico.menu` | manter | `[data-tour="nav"]` | `app/App.tsx:763`, no `<nav className="nav">` | O menu principal | Daqui você vai para cada parte do DroidNote. Clique num nome para trocar de tela. | não ocorre |
| `basico.recentes` | manter | `[data-tour="recent"]` | `app/App.tsx:771`, no `div.sidebar-section` | Conversas recentes | As últimas gravações ficam aqui, separadas por dia. Clique numa para abrir. | Lista vazia: mesma âncora, corpo alternativo `basico.recentesVazio`: "Ainda não há conversas. A primeira aparece aqui quando você Gravar." |
| `basico.busca` | manter | `[data-tour="search"]` | `shared/ui/StatusStrip.tsx:42`, no `button.strip-search` | Buscar em tudo | Clique aqui ou aperte Ctrl K. Ache falas, atas, tarefas e comandos. | não ocorre |
| `basico.motor` | manter | `[data-tour="engine"]` | `shared/ui/EngineSwitch.tsx:14`, no `div.engine-switch` | Modelos locais ou OpenAI | Com Modelos locais, nada sai deste PC. A OpenAI usa a internet e costuma ser mais rápida em PCs simples. | Barra recolhida: a âncora continua visível como ícone. Se não houver retângulo visível, pule. |

### Capítulo 2. Antes de gravar (`preparar`)

| id | view | âncora | onde pôr | título | corpo | se faltar |
|---|---|---|---|---|---|---|
| `preparar.tipo` | `live` | `[data-tour="mode"]` | `pages/LivePage.tsx:317`, no `div.mode-switch` | Reunião, Aula ou Ditado | Reunião e Aula gravam o microfone e o som do PC. Ditado usa só o microfone. | não ocorre |
| `preparar.idioma` | `live` | `[data-tour="capture-language"]` | `features/capture/CaptureLanguageMenu.tsx:47`, no `div.capture-lang-menu` | Idioma da fala | Escolha a língua que as pessoas vão falar. A transcrição fica mais certa. | não ocorre |
| `preparar.modelo` | `live` | `[data-tour="template"]` | `features/templates/TemplatePicker.tsx:18`, no `label.template-picker` | Modelo da ata | Escolha como a ata vai ser escrita. Crie os seus em Preferências, aba Templates. | não ocorre |
| `preparar.fontes` | `live` | `[data-tour="sources"]` | `pages/LivePage.tsx`, função `SourcesMenu`, no `div.sources` | Fontes de som | Clique em Fontes para usar o som do PC ou só o microfone. Ali você também diz quem está na sala. | não ocorre |

Durante uma gravação esses controles ficam desligados. O tour mostra os mesmos passos, com o prefixo no corpo: "Durante a gravação isto fica travado." (chave `tour.lockedNote`).

### Capítulo 3. Gravar (`gravar`)

| id | view | âncora | onde pôr | título | corpo | se faltar |
|---|---|---|---|---|---|---|
| `gravar.botao` | `live` | `[data-tour="record"]` | `features/capture/CaptureDeck.tsx:64`, no `button.reactor` | Gravar | Clique no botão para começar e de novo para parar. Atalho: Ctrl Shift R. | não ocorre |
| `gravar.aviso` | `live` | `[data-tour="consent"]` | `pages/LivePage.tsx:392`, no botão com ícone `shield` | Avise as pessoas | Clique aqui para copiar um aviso de gravação. Cole no chat da reunião antes de começar. | não ocorre |
| `gravar.mini` | `live` | `[data-tour="mini"]` | `pages/LivePage.tsx:395`, no botão com ícone `chip` | Mini console | Abre uma janela pequena, sempre por cima. Dali você anota e pergunta sem sair da reunião. | não ocorre |
| `gravar.agenda` | `live` | `[data-tour="upcoming"]` | `features/brief/UpcomingPanel.tsx`, nos dois retornos: `button.upcoming-connect` (linha 46) e `section.upcoming` (linha 68) | Próximas reuniões | Conecte sua agenda para ver as reuniões do dia. Clique em Gravar ao lado de uma delas. | Gravando ou agenda ainda carregando: pule o passo. |

### Capítulo 4. Suas conversas (`conversas`)

| id | view | âncora | onde pôr | título | corpo | se faltar |
|---|---|---|---|---|---|---|
| `conversas.pastas` | `library` | `[data-tour="folders"]` | `pages/LibraryPage.tsx:189`, no `nav.library-folders` | Pastas | Crie pastas para clientes, aulas ou projetos. Arraste uma conversa até a pasta para mover. | Coluna recolhida: a âncora continua. Corpo igual. |
| `conversas.busca` | `library` | `[data-tour="library-search"]` | `pages/LibraryPage.tsx:316`, no `div.library-toolbar` | Buscar e ordenar | Digite para achar uma conversa pelo nome. Ao lado, escolha a ordem da lista. | não ocorre |
| `conversas.varias` | `library` | `[data-tour="library-select"]` | `pages/LibraryPage.tsx:390`, no `label.library-check` do cabeçalho | Várias de uma vez | Marque as caixas para mover ou apagar várias conversas juntas. | Sem tabela (lista vazia): pule. |
| `conversas.abrir` | `library` | `[data-tour="library-first"]` | `pages/LibraryPage.tsx`, na primeira linha de dados da `div.library-table` (só índice 0) | Abrir uma conversa | Clique numa conversa para ver a ata, a transcrição e o resto. | Lista vazia: âncora `.library-empty`, corpo `conversas.abrirVazio`: "Ainda não há conversas. Clique em Gravar para criar a primeira." |

### Capítulo 5. Dentro de uma conversa (`conversa`)

Antes do primeiro passo, o tour abre a conversa mais recente (ver seção 6.1).

| id | view | âncora | onde pôr | título | corpo | se faltar |
|---|---|---|---|---|---|---|
| `conversa.nome` | `session` | `[data-tour="session-head"]` | `pages/SessionPage.tsx:329`, no `header.page-head` | Nome e pasta | Clique no nome para trocar. No canto direito, escolha a pasta da conversa. | não ocorre |
| `conversa.player` | `session` | `[data-tour="playback"]` | `pages/SessionPage.tsx:427`, na `section.panel.playback` | Ouvir de novo | Toque o áudio da conversa. A faixa Quem falou quando mostra a vez de cada pessoa. | Áudio apagado pela retenção: pule. |
| `conversa.transcricao` | `session` | `[data-tour="transcript"]` | `pages/SessionPage.tsx:442`, na `section.transcript-panel` | A transcrição | Busque uma palavra no campo acima. Clique numa fala e aperte 1 a 9 para dizer quem falou. | não ocorre |
| `conversa.perguntar` | `session` | `[data-tour="session-ask"]` | `pages/SessionPage.tsx:357`, no botão Perguntar | Perguntar sobre ela | Clique em Perguntar para abrir o Chat já nesta conversa. Perguntas prontas traz pedidos comuns. | Botão ausente: pule. |
| `conversa.exportar` | `session` | `[data-tour="export"]` | `pages/SessionPage.tsx:389`, no `div.export-menu` do Exportar | Exportar | Leve a ata, a transcrição ou tudo para PDF, Word ou Markdown. | não ocorre |

### Capítulo 6. Ata e abas (`abas`)

Mesma conversa do capítulo 5. As âncoras já existem: os botões de aba usam `id={tabId("side", id)}` (`pages/SessionPage.tsx:83`). Não precisa adicionar atributo. O tour só aponta para a aba. Não troca a aba aberta.

| id | view | âncora | título | corpo |
|---|---|---|---|---|
| `abas.ata` | `session` | `#side-tab-doc` | A ata | Em Documento fica a ata: resumo, decisões e tarefas. Clique numa marca de tempo para ouvir a fala. |
| `abas.anotacoes` | `session` | `#side-tab-notes` | Suas anotações | Anote enquanto grava. Cada anotação fica presa ao momento e guia a ata. |
| `abas.contexto` | `session` | `#side-tab-context` | Material de apoio | Adicione pauta, slides ou apostila. A ata e o Chat passam a usar os termos de lá. |
| `abas.mapa` | `session` | `#side-tab-mindmap` | Mapa mental | Veja os temas da conversa em ramos. Clique num ramo para ir ao momento. |
| `abas.memoria` | `session` | `#side-tab-memory` | Memória da série | Liga esta conversa a outras parecidas. Mostra o que ficou pendente da última vez. |
| `abas.vozes` | `session` | `#side-tab-voices` | Vozes | Dê um nome a cada voz. Nas próximas conversas, o DroidNote reconhece a pessoa. |

Se faltar: não ocorre, as 6 abas sempre aparecem na conversa. Atenção: em Ao vivo a aba Memória tem id `brief` (`#side-tab-brief`). O capítulo roda só na tela da conversa.

### Capítulo 7. Tarefas (`tarefas`)

| id | view | âncora | onde pôr | título | corpo | se faltar |
|---|---|---|---|---|---|---|
| `tarefas.nova` | `tasks` | `[data-tour="task-new"]` | `pages/TasksPage.tsx:116`, no `form.task-composer` | Nova tarefa | Escreva a tarefa e, se quiser, o responsável. Clique em Adicionar. | não ocorre |
| `tarefas.filtros` | `tasks` | `[data-tour="task-filters"]` | `pages/TasksPage.tsx:143`, no `div.task-filters` | Filtrar | Veja abertas, feitas ou todas. Clique num nome para ver só as tarefas dessa pessoa. | não ocorre |
| `tarefas.lista` | `tasks` | `[data-tour="task-list"]` | `pages/TasksPage.tsx`, em `div.task-groups` e em `div.task-empty` | Marcar como feita | Clique na caixa quando terminar. O nome no topo do grupo abre a conversa de origem. | Lista vazia: mesma âncora em `.task-empty`, corpo `tarefas.listaVazia`: "As tarefas de cada ata aparecem aqui sozinhas." |

### Capítulo 8. Chat (`chat`)

O tour navega com `openChat()` sem foco (`App.tsx:146`). Os passos 1 e 2 dependem da tela vazia do chat (`div.chat-empty`), que só aparece num chat sem mensagens.

| id | view | âncora | onde pôr | título | corpo | se faltar |
|---|---|---|---|---|---|---|
| `chat.contexto` | `chat` | `[data-tour="chat-context"]` | `pages/ChatPage.tsx`, no `div.chat-context-list` | Escolha as gravações | Clique nas gravações que o Chat deve ler. Pode marcar várias. | Chat com mensagens: âncora `[data-tour="chat-new"]` (botão Nova em `div.chat-rail-head`), corpo `chat.contextoNovo`: "Clique em Nova para abrir um chat limpo. Ali você escolhe quais gravações ele lê." Sem nenhuma gravação: pule. |
| `chat.comandos` | `chat` | `[data-tour="chat-study"]` | `pages/ChatPage.tsx`, no `div.chat-context` de Materiais de estudo | Comandos com barra | Clique num atalho para pedir resumo, flashcards ou prova. Ou digite / na caixa de texto. | Ausente: âncora `.chat-composer`, mesmo corpo. |
| `chat.anexar` | `chat` | `[data-tour="chat-attach"]` | `pages/ChatPage.tsx`, no `div.chat-attach-wrap` | Anexar arquivo ou link | Clique aqui para mandar um PDF, uma imagem, uma página da web ou um vídeo do YouTube. | não ocorre |
| `chat.opcoes` | `chat` | `[data-tour="chat-tune"]` | `features/chat/ChatTune.tsx:106`, no `div.chat-tune` | Opções da resposta | Escolha o modo: Normal, Rápido, Estudar ou Resolver. Marque Só fontes para responder só com o que você gravou e anexou. | não ocorre |
| `chat.fontes` | `chat` | `.chat-sources` (a última da tela) | já existe | De onde veio | Cada resposta numera os trechos usados. Clique no número para ouvir a gravação naquele momento. | Sem resposta na tela: âncora `.chat-composer`, corpo `chat.fontesAntes`: "Depois de perguntar, cada resposta mostra os trechos usados. Clique no número para ouvir aquele momento." |
| `chat.historico` | `chat` | `[data-tour="chat-rail"]` | `pages/ChatPage.tsx`, no `aside.chat-rail` | Chats anteriores | Seus chats ficam nesta coluna. Clique num para continuar de onde parou. | não ocorre |

Atenção: `ChatPage.tsx` está sendo editado por outra ordem de serviço agora. Por isso as âncoras do Chat citam classe, não linha. O frontend aplica estes atributos depois que aquela edição terminar.

### Capítulo 9. Preferências (`preferencias`)

As âncoras já existem: `id="settings-tab-<id>"` (`pages/SettingsPage.tsx:400`). O tour não troca a aba aberta.

| id | view | âncora | onde pôr | título | corpo |
|---|---|---|---|---|---|
| `preferencias.abas` | `settings` | `[data-tour="settings-tabs"]` | `pages/SettingsPage.tsx:390`, no `div.settings-tabs` | Suas preferências | Cada aba cuida de uma parte do app. Em Idioma e Aparência você troca a língua e o tema. |
| `preferencias.motor` | `settings` | `#settings-tab-transcription` | já existe | Motor e chave | Em Transcrição você escolhe Modelos locais ou OpenAI. A chave da OpenAI fica só neste PC, cifrada. |
| `preferencias.pessoas` | `settings` | `#settings-tab-people` | já existe | Pessoas e vozes | Cadastre as pessoas e diga quem é você. Isso ajuda a separar quem falou. |
| `preferencias.reunioes` | `settings` | `#settings-tab-meetings` | já existe | Reuniões e retenção | Conecte a agenda, edite o aviso de gravação e escolha quando apagar gravações antigas. |
| `preferencias.templates` | `settings` | `#settings-tab-templates` | já existe | Modelos de ata | Crie seu próprio modelo de ata. Ele aparece na escolha da tela Ao vivo. |

Se faltar: não ocorre.

### Fim do tour

Depois do último passo do último capítulo, o balão mostra um cartão sem âncora, no canto inferior direito:

- Título: "Tour concluído"
- Corpo: "Para rever uma parte, clique em ? no topo da tela. A Ajuda tem o manual e os atalhos."
- Botões: "Abrir a Ajuda" (vai para `help`) e "Fechar" (primário).

## 5. Interação

### 5.1 Entradas

| Onde | Ação | Resultado |
|---|---|---|
| Boas-vindas (`WelcomeModal`) | "Fazer o tour" | Fecha o modal e abre o seletor de capítulos. |
| Ajuda, cabeçalho | "Tour guiado" (renomeia `help.tour`, hoje "Refazer o tour") | Abre o seletor de capítulos. |
| Ajuda, nova seção "Tour guiado" (primeira da página, id `help-tour`, entra no índice) | Lista dos 9 capítulos, cada um com "Ver este capítulo" | Roda só aquele capítulo. |
| Botão "?" no topo de cada tela | Clique | Roda só o capítulo daquela tela. |
| Paleta (Ctrl K), seção Comandos | Novo comando "Fazer o tour" | Abre o seletor. |

### 5.2 Botão "?" por tela

- Componente `TourButton({ chapter })`: botão `tool-btn is-icon`, ícone `help` 15 px, `aria-label` e `title` "Ver o tour desta tela".
- Posição: último item de `div.page-actions` do cabeçalho. Onde não há `page-actions`, criar um no cabeçalho.

| Tela | Capítulo | Arquivo |
|---|---|---|
| Ao vivo | `preparar` (o seletor oferece continuar em `gravar`) | `pages/LivePage.tsx:391` |
| Conversas | `conversas` | `pages/LibraryPage.tsx:182` (cabeçalho sem `page-actions`: criar) |
| Conversa | `conversa`, depois segue para `abas` | `pages/SessionPage.tsx:417`, antes do botão apagar |
| Tarefas | `tarefas` | `pages/TasksPage.tsx:108` (cabeçalho sem `page-actions`: criar) |
| Chat | `chat` | `pages/ChatPage.tsx`, no `div.chat-rail-head` |
| Preferências | `preferencias` | `pages/SettingsPage.tsx:384`, no `PageHeader` |

Capítulo `basico` sai pelo seletor e pela Ajuda.

### 5.3 Seletor de capítulos

Painel não modal no canto inferior direito, mesma pele do balão (`tour-pop`), largura 340 px.

```
Tour do DroidNote                                  [x]
Escolha uma parte ou veja tudo em ordem.

 ✓  1  O básico                           4 passos
    2  Antes de gravar                    4 passos
 >  3  Gravar               parou no passo 2 de 4
    4  Suas conversas                     4 passos
    ...
    9  Preferências                       5 passos

[Começar do início]        [Continuar de onde parei]
```

- Cada linha é um botão. Clique roda aquele capítulo e segue para os próximos.
- Marca "✓" (ícone `check`) nos capítulos concluídos. Marca de posição no capítulo em andamento.
- Capítulos 5 e 6 sem conversa gravada: linha fica ativa, com texto auxiliar "Precisa de uma conversa gravada".
- "Continuar de onde parei" só aparece com progresso salvo. Botão primário nesse caso. Sem progresso, "Começar do início" é o primário.
- Esc ou [x] fecha. Foco inicial no botão primário. Lista navegável com Tab e setas.

### 5.4 Balão do passo

Evolui o `Tour` atual (`Onboarding.tsx:115`). Mantém: posicionamento ao lado ou abaixo da âncora, classe `.tour-target` na âncora, `role="dialog"` com `aria-modal="false"`, foco volta ao lugar de antes ao sair.

```
CAPÍTULO 3 DE 9 · PASSO 2 DE 4
Gravar

Avise as pessoas
Clique aqui para copiar um aviso de gravação.
Cole no chat da reunião antes de começar.

Sair   Pular capítulo           [Voltar] [Próximo]
```

- Linha de progresso: `tour.progress` "Capítulo {chapter} de {chapters} · passo {step} de {steps}". Abaixo, o nome do capítulo como eyebrow.
- No modo capítulo único (vindo do "?" ou de "Ver este capítulo"): progresso "Passo {step} de {steps}", sem "Pular capítulo".
- "Voltar" desligado no primeiro passo do primeiro capítulo. Voltar no primeiro passo de um capítulo vai ao último passo do capítulo anterior.
- Último passo de um capítulo: o primário vira "Próximo capítulo". Último passo do tour ou do capítulo único: "Concluir".
- "Pular capítulo" vai ao primeiro passo do capítulo seguinte. No último capítulo, vai ao cartão de fim.
- "Sair" e Esc encerram e guardam a posição.
- Foco vai ao botão primário a cada passo. Enter avança. As setas não navegam o tour, para não brigar com abas e listas da tela.
- Texto do passo em região `aria-live="polite"` para leitor de tela.

### 5.5 Sem bloquear a tela

- Sem fundo escuro, sem `inert` na página. A pessoa pode clicar em tudo durante o tour.
- A âncora recebe o anel `.tour-target` (já existe). A âncora entra na tela com `scrollIntoView({ block: "nearest", behavior: "smooth" })`. Com `prefers-reduced-motion`, sem `smooth`.
- O tour só faz duas coisas na tela: trocar de view e abrir a conversa mais recente. Nunca clica, nunca grava, nunca troca aba, nunca muda preferência.
- Se a pessoa trocar de tela e a âncora sumir, o tour pausa. O balão vira uma pílula no canto inferior direito: "Tour pausado" com botões "Continuar" (volta à view do passo) e "Sair". O tour não arrasta a pessoa de volta sozinho.

### 5.6 Retomar

- Chave `droidnote.tour.v1` em `localStorage`:
  `{ "chapter": "gravar", "step": 1, "done": ["basico", "preparar"], "finished": false }`
- Grava a cada troca de passo e ao sair. Todo acesso em `try/catch`. Sem acesso ao storage, o tour funciona e só não retoma.
- Ao concluir tudo: `finished: true`. O seletor mostra todos com "✓" e oferece "Começar do início".
- Se um id salvo não existe mais (tour mudou de versão), começa do início do capítulo salvo, ou do capítulo 1.
- O tour nunca abre sozinho. Só por ação da pessoa.

## 6. Casos de borda

### 6.1 Capítulos que precisam de conversa

- Ao entrar no capítulo 5 ou 6: se a view atual já é `session`, usa a conversa aberta. Senão, abre a mais recente de `sessions` (ordem por data de início, a mesma de `recentSessions` em `App.tsx`), com o mesmo caminho de `openSession`.
- Se não existe nenhuma conversa: cartão centrado sem âncora, no lugar do capítulo:
  - Título: "Grave sua primeira conversa"
  - Corpo: "Esta parte mostra uma conversa gravada. Grave alguns minutos em Ao vivo e volte aqui."
  - Botões: "Ir para Ao vivo" (vai para `live` e pausa o tour) e "Pular capítulo" (primário).
- Conversa ainda em gravação: usa outra conversa. Se só houver ela, mostra o cartão acima.

### 6.2 Âncora ausente

- Regra geral: espera até 600 ms a âncora aparecer (a view acabou de trocar). Depois disso, usa o "se faltar" da tabela. Se não houver alternativa, pula o passo sem mostrar nada.
- Âncora com retângulo de tamanho zero (escondida por CSS) conta como ausente.
- Se todos os passos de um capítulo faltarem, mostra o cartão centrado "Nada para mostrar aqui agora" com "Pular capítulo".

### 6.3 Gravação em andamento

- O tour pode rodar durante uma gravação. Trocar de view não para a gravação (a faixa "Há uma transcrição ativa" já existe).
- Capítulo 2: corpo recebe o prefixo `tour.lockedNote`.
- Passo `gravar.botao`: corpo alternativo `gravar.botaoGravando`: "Você está gravando agora. Clique no botão para parar."
- Passo `gravar.agenda`: pulado.

### 6.4 Modais e menus

- Se um `Modal` estiver aberto (boas-vindas, confirmação, paleta), o balão não aparece até ele fechar.
- Se a pessoa abrir um menu (Fontes, Exportar), o balão continua. O menu fica por cima (z-index do popover acima do balão).

### 6.5 Responsivo

- Balão: `width: min(300px, 100vw - 24px)`. Seletor: `min(340px, 100vw - 24px)`.
- Janela abaixo de 640 px de largura: o balão vai sempre para baixo da âncora, ou acima se não couber. Nunca ao lado.
- Barra lateral recolhida (Ctrl B): âncoras do capítulo 1 continuam. O balão se posiciona ao lado do ícone.
- Recalcula posição em `resize` e `scroll` (já existe no `Tour` atual).

## 7. Acessibilidade

- Balão e seletor: `role="dialog"`, `aria-modal="false"`, `aria-labelledby` no título, `aria-describedby` no corpo.
- Progresso lido pelo leitor de tela junto com o título.
- Contraste do texto do balão: mínimo 4.5:1 nos três temas (Escuro, Claro, Paper white). Usar os tokens de `shared/styles/tokens.css` já usados em `.tour-pop`.
- Anel `.tour-target`: não depende só de cor. Manter contorno de 2 px com afastamento.
- Botões com alvo mínimo de 32 px de altura.
- Esc sempre fecha o seletor ou o tour. Foco volta ao elemento de antes.

## 8. Texto e i18n

Chaves novas em `shared/i18n/catalogs/*.ts`, objeto `tour`. O texto em português está nas tabelas acima. Os outros 6 idiomas precisam de tradução.

```
tour.progress            "Capítulo {chapter} de {chapters} · passo {step} de {steps}"
tour.progressSingle      "Passo {step} de {steps}"
tour.back                "Voltar"
tour.next                "Próximo"            (já existe)
tour.nextChapter         "Próximo capítulo"
tour.skipChapter         "Pular capítulo"
tour.exit                "Sair"
tour.done                "Concluir"           (já existe)
tour.pickerTitle         "Tour do DroidNote"
tour.pickerBody          "Escolha uma parte ou veja tudo em ordem."
tour.fromStart           "Começar do início"
tour.resume              "Continuar de onde parei"
tour.steps               "{count} passos"
tour.stoppedAt           "parou no passo {step} de {steps}"
tour.needsSession        "Precisa de uma conversa gravada"
tour.paused              "Tour pausado"
tour.continue            "Continuar"
tour.pageButton          "Ver o tour desta tela"
tour.paletteCommand      "Fazer o tour"
tour.lockedNote          "Durante a gravação isto fica travado."
tour.noSessionTitle      "Grave sua primeira conversa"
tour.noSessionBody       "Esta parte mostra uma conversa gravada. Grave alguns minutos em Ao vivo e volte aqui."
tour.goLive              "Ir para Ao vivo"
tour.nothingTitle        "Nada para mostrar aqui agora"
tour.endTitle            "Tour concluído"
tour.endBody             "Para rever uma parte, clique em ? no topo da tela. A Ajuda tem o manual e os atalhos."
tour.openHelp            "Abrir a Ajuda"
tour.close               "Fechar"
tour.ch.<capítulo>.title             nome do capítulo (tabela da seção 3)
tour.ch.<capítulo>.<passo>.title     título do passo
tour.ch.<capítulo>.<passo>.body      corpo do passo
tour.ch.<capítulo>.<passo>Alt.body   corpo alternativo, quando houver
help.tour                "Tour guiado"        (troca "Refazer o tour")
help.tourSection         "Tour guiado"
help.tourSee             "Ver este capítulo"
```

As chaves antigas `tour.liveTitle`, `tour.liveBody`, `tour.libraryTitle`, `tour.libraryBody`, `tour.tabsTitle`, `tour.tabsBody`, `tour.askTitle`, `tour.askBody`, `tour.count` e `tour.skip` saem dos 7 catálogos.

Regras de texto aplicadas: sem travessão, verbo "Clique", frases curtas, termos do glossário (Conversa, Ata, Gravar, Ao vivo). "Templates" aparece porque é o nome da aba em Preferências (`templates.tab`).

## 9. Implementação sugerida

- Dados do roteiro em `features/onboarding/tourScript.ts`: lista de capítulos, cada um com `id`, `view`, `needsSession` e passos `{ id, selector, fallback?: { selector?, bodyKey?, skip? } }`. Sem texto no arquivo, só chaves.
- `Tour` recebe `onNavigate(view)` e `onOpenLatestSession()` vindos de `App.tsx`. Não importa estado da página.
- Atributos `data-tour` novos: `nav`, `recent`, `search`, `engine`, `mode`, `capture-language`, `template`, `sources`, `record`, `consent`, `mini`, `upcoming`, `folders`, `library-search`, `library-select`, `library-first`, `session-head`, `playback`, `transcript`, `session-ask`, `export`, `task-new`, `task-filters`, `task-list`, `chat-context`, `chat-new`, `chat-study`, `chat-attach`, `chat-tune`, `chat-rail`, `settings-tabs`. Total 31 atributos. Os atuais `live` e `library` em `NavButton` podem ficar ou sair.
- Teste: um teste por capítulo que monta a tela com dados de exemplo e confere que cada seletor encontra um elemento, ou que o "se faltar" se aplica.

## 10. Critérios de aceite

1. "Fazer o tour" nas boas-vindas abre o seletor com 9 capítulos e a contagem de passos.
2. Percorrer tudo mostra 41 passos com conversa gravada, sem nenhum balão sem âncora fora dos cartões previstos.
3. Sem conversas gravadas, os capítulos 5 e 6 mostram o cartão "Grave sua primeira conversa" e o resto funciona.
4. "Pular capítulo" leva ao capítulo seguinte. "Sair" e Esc fecham. Reabrir oferece "Continuar de onde parei" no passo exato.
5. O "?" de cada tela roda só o capítulo daquela tela, com progresso "Passo n de m".
6. Durante todo o tour, a pessoa consegue clicar em qualquer item da tela.
7. Nenhum passo grava, para, apaga, troca aba ou muda preferência.
8. Funciona em 400 px de largura e com a barra lateral recolhida.
9. Leitor de tela anuncia progresso, título e corpo de cada passo.
