# Diagnóstico e melhorias — outubro de 2026

Varredura completa de backend, captura de áudio e frontend. Cada item diz o que estava errado, como foi medido e o que mudou. O que ficou para depois está no fim, em ordem de impacto.

## Captura de áudio

| Problema | Evidência | O que mudou |
| --- | --- | --- |
| O áudio do sistema era lido como "último bloco de 100 ms". Com relógios diferentes entre placas, blocos se repetiam ou sumiam. | Código de `_LatestLoopback.latest()` | Fila real (`_LoopbackFifo`), latência limitada a 60–300 ms, deriva corrigida |
| Reamostragem por bloco, interpolação linear sem filtro. Em placa de 48 kHz (quase todas), tudo acima de 8 kHz dobrava para dentro da faixa de voz. | Tom de 12 kHz: saía com amplitude 0,707 em 4 kHz. Agora: 0,000 (teste `test_stream_resampler_keeps_block_size_and_removes_alias`) | `StreamResampler`: FIR passa-baixa + fase contínua entre blocos |
| VAD por energia (RMS ≥ 0,004): ventilador e teclado viravam "fala"; quem fala baixo era cortado. | Limiar fixo em `vad.py` | Silero VAD neural por canal (já vinha no faster-whisper, sem download) |
| Sem fone, a voz de quem está na chamada entrava duas vezes: pelo áudio do sistema e pelo microfone, como "Você". | Fluxo mic/loopback sem cancelamento | `EchoGate` silencia o eco no canal do microfone, só para a transcrição |
| Uma frase alucinada ("inscreva-se no canal") apagava a janela inteira de 20 s. | `filter_transcript` sobre o texto todo | Filtro por frase do Whisper |
| Cada segmento era a janela inteira (até 20 s, várias pessoas misturadas). | `without_timestamps=True` | Palavras com tempo; turnos por voz com início e fim reais |
| Crash nativo (access violation) com o reagrupamento rodando junto da transcrição. | Reproduzido isolando OpenBLAS + onnxruntime/CTranslate2 em threads | `OPENBLAS_NUM_THREADS=1` no início do processo |

## Quem falou

Antes: microfone = "Você", áudio do sistema = "Outros". Depois da gravação, um LLM tentava adivinhar o falante só pelo texto. Em aula, o microfone (o professor) era rotulado como quem grava.

Agora há um motor de voz local (detalhes em [arquitetura](architecture.md#motor-de-voz-quem-falou)):

- Impressão vocal neural (WeSpeaker ResNet34-LM, ONNX, 26 MB), feature Kaldi reimplementada em numpy.
- Diarização palavra a palavra, ao vivo, com reagrupamento espectral periódico que corrige a fragmentação.
- "Falando agora" em tempo real (~0,6 s), antes da transcrição.
- Memória de vozes: nomear uma voz uma vez faz o DroidNote reconhecê-la nas próximas gravações.
- A ata, o chat e as exportações passam a distinguir "Voz 2" de "Voz 3" mesmo sem nome.

Validação com áudio real (tudo local):

| Áudio | Resultado |
| --- | --- |
| Amostra com gabarito (pyannote, 2 pessoas, troca rápida de turno) | 2 vozes; os 9 turnos atribuídos corretamente |
| Entrevista em português (2 pessoas, rua, ruído) | 2 vozes; perguntas e respostas separadas; 114 s processados em 55 s na CPU |
| Reunião de trabalho com 5+ pessoas | 3 a 5 vozes conforme o trecho |
| Gravações de uma pessoa só | 1 voz (sem "falantes fantasmas") |
| Memória entre sessões | Voz nomeada reconhecida sozinha em sessão nova; nenhuma confusão em sessão de controle com outras pessoas |

## Frontend

| Problema | O que mudou |
| --- | --- |
| CSS de 4.900 linhas num arquivo, com uma segunda camada (linha 1942) redefinindo os mesmos componentes | Sistema novo: `tokens.css` (tokens dos 3 temas + primitivos), `shell.css`, `console.css`, `pages.css` |
| Visual de painel SaaS genérico; o valor do produto (quem falou, o que está acontecendo) não aparecia | Console de captura: botão reator, timecode, osciloscópio por canal, filtro de eco visível, "falando agora" |
| Falantes eram dois rótulos fixos | Painel de vozes com assinatura vocal, % de fala, nomear com um clique, linha do tempo multitrack clicável |
| Sem busca global, embora o backend tenha FTS | Paleta `Ctrl+K`: busca falas, sessões e comandos; abre a sessão no segundo exato |
| Lista de sessões sem estrutura | Agrupada por dia, ícone do modo, duração em mono, indicador da gravação ativa |
| Telemetria escondida | Faixa de status: gravação, conexão, privacidade, modelos em uso |
| "Editar" fixo em português num app de 7 idiomas | Traduzido; restam os itens da seção abaixo |

## Recomendado a seguir

1. **Sessão presa em "gravando"** depois de queda do processo: no arranque, marcar como parada as sessões sem captura ativa.
2. **`uvicorn --reload` do `dev.ps1` trava** quando há WebSocket aberto (observado nesta sessão). Usar `--timeout-graceful-shutdown 2`.
3. **Textos fixos em português** que ainda escapam do i18n: `ModelSelect` ("Escolher modelo", "Já neste PC", "Será baixado"), `Toast` (aria "Fechar aviso"), `SessionTitle` (aria "Título da sessão"), `ProgressBar` ("Progresso"), títulos padrão das sessões ("Reunião", "Aula", "Ditado") e cabeçalhos das exportações (Markdown/PDF/DOCX).
4. **Sobreposição entre janelas** (1 s) é deduplicada só por texto; às vezes uma frase curta sai duas vezes. Com os tempos de palavra já disponíveis, cortar pela fronteira da sobreposição.
5. **Sessões curtas** (< 1 min) às vezes dividem uma pessoa em duas vozes. Hoje dá para juntar dando o mesmo nome às duas; falta um "juntar vozes" explícito.
6. **Fala simultânea** (duas pessoas ao mesmo tempo) vai para a voz dominante. Um modelo de segmentação com sobreposição (pyannote-segmentation em ONNX) resolveria.
7. **SQLite abre uma conexão por consulta.** Agora em WAL e com índices; o próximo passo é uma conexão compartilhada.
8. **Bundle principal de 913 KB** (TipTap). Carregar o editor de nota sob demanda.

## Ideias de diferencial

- Cadastro de voz no primeiro uso ("leia esta frase") para o DroidNote já saber quem é você.
- Ata com responsável automático por voz e balanço de fala da reunião ("Ana falou 62%").
- Legenda ao vivo numa janela flutuante, com a cor de cada voz.
- Destaque palavra a palavra na reprodução (os tempos de palavra já existem; falta guardar).
