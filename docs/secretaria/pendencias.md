# Pendências — DroidNote

| aberta em | item | dono | falta | espera o CEO? |
|---|---|---|---|---|
| 2026-11-13 | Commit e release do trabalho de 2026-11-13 | CEO | resolvido: CEO pediu a 2.3.1 (patch); Novidades ajustadas para a 2.3.1; push autorizado e feito | não |
| 2026-11-13 | Qual "skill nova" de download de vídeo o CEO quis dizer | CEO | resposta do CEO | sim |
| 2026-11-13 | Empacotamento MSIX para a Microsoft Store via WinApp CLI; conta gratuita da empresa; testar microfone no MSIX | CEO | aprovação e criação da conta | sim |
| 2026-11-13 | Refatoração da base de provedores de IA (2 a 3 dias); DeepSeek precisa de legal-lgpd | CEO | aprovação do CEO; parecer legal-lgpd para DeepSeek | sim |
| 2026-11-13 | Conectores, top 5: MCP local, pasta Markdown, webhook, participantes via ICS, exportar tarefas | CEO | aprovação do CEO | sim |
| 2026-11-13 | Página do DroidNote no site: 10 melhorias no repositório Website | CEO | aprovação do CEO | sim |
| 2026-11-13 | Executor de testes do frontend (vitest) não adicionado | tec-frontend | adicionar vitest | não |
| 2026-11-13 | Acabamento: prazo de tarefa sem data cortado; centralização vertical do mapa mental; rótulo "Modelo da nota (Ollama)" ainda diz nota; corrida do parar em chat novo | tec-frontend | corrigir | não |
| 2026-11-13 | Segurança opcional: `hmac.compare_digest` no token, `secure_delete` para chaves antigas em texto puro, ocultar `sk-` nos logs, KeySeal fora do Windows | tec-backend | implementar | não |
| 2026-11-13 | Idioma do Windows desconhecido cai em pt, não en | CEO | decisão do CEO | sim |
| 2026-11-13 | Advogado: revisar a base legal da gravação | legal-lgpd (prepara a consulta) | contratar advogado tem custo | sim, espera o CEO |
| 2026-11-19 | Aprovar a página simples da bolha: https://claude.ai/code/artifact/66165cee-022f-4429-a1b1-ba05d6ef5107 (maquetes em `docs/uxui/proposals/`) | CEO | aprovação | sim |
| 2026-11-19 | Construir: abrir com o Windows, fechar para a bandeja, bolha, aviso de 5 minutos de silêncio | tec-frontend, tec-backend | aprovação da linha acima; construir | sim (depende da aprovação) |
| 2026-11-19 | "Detectar fala" com microfone ocioso | legal-lgpd | parecer antes de construir | sim (depende da aprovação) |
| 2026-11-19 | Mistura de modelo de nota: modelo próprio só preenche "topics"; esqueleto fixo Resumo/Decisões/Ações/Pendências sempre impresso (`summarize.py:271-277, 427-461`; `prompts.py:50-64`) | tec-backend | aval do CEO; corrigir | sim |
| 2026-11-19 | Correções do chat: contexto só 64 trechos/12k caracteres (reunião de 60 min ~8% lida, fontes todas do início); busca FTS sem ranking (ordem start_ms); comando de barra briga com o modo ativo (estudo junta resumo aos flashcards); streaming falso na OpenAI; Ollama cita [mm:ss] e não [n]; OpenAI inventa citação "[resumo da reunião]"; modo rápido pode ficar sem trechos; travamento do Ollama mostra texto de erro errado; popover de modo não fecha com Esc; modo não salvo por chat; comandos de barra sobrepostos aos prompts salvos; remover /flashcards em 7 idiomas + tour + CHANGELOG + marketing | tec-ai | aval do CEO; corrigir | sim |
| 2026-11-19 | Limite contra injeção de instruções vindas das transcrições (prompt injection) | csq-seguranca | definir e validar | não |
