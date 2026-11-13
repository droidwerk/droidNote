# Diário — DroidNote

| data | risco | pedido | funcionários | resultado |
|---|---|---|---|---|
| 2026-11-13 | R2 | Pesquisa: provedores de IA, conectores, concorrentes, distribuição e confiança, revisão da página do produto | cmi, seo-marketing | Relatórios em `docs/mercado/pesquisa-2026-11-13.md` e `docs/cmi/distribuicao-confianca-2026-11-13.md`; revisão da página do produto entregue (melhorias no repositório Website ficam pendentes). |
| 2026-11-13 | R2 | Fase A: memória por pasta; correções de interface (acessibilidade e contraste); boas-vindas uma vez e novidades por versão; aba Ajuda; selo da chave; correções de texto LGPD (inclui `consent.defaultCloud`) | tec-backend, tec-frontend (2 ordens); tec-uxui-critico, csq-revisor-diff, csq-seguranca, legal-lgpd | Implementado e aprovado por csq-revisor-diff, csq-seguranca e legal-lgpd. Backend: 294 testes passam. Nada commitado. |
| 2026-11-13 | R2 | Chat sai do beta: escopo só nas conversas escolhidas, seleção múltipla em chips persistida, parar salva o parcial, renomear, tentar de novo sem duplicar, id do chat no primeiro evento SSE, histórico em grupos, selo Beta removido | tec-backend (3 ordens), tec-frontend (3 ordens); csq-revisor-diff, csq-seguranca, legal-lgpd | Implementado e aprovado. Nada commitado. |
| 2026-11-13 | R2 | Tour completo do produto | tec-uxui-designer (roteiro), tec-frontend (implementação), tec-uxui-critico (validação visual) | Tour com 9 capítulos e 41 passos. |
| 2026-11-13 | R2 | Revisão visual na ferramenta real | tec-uxui-critico | 3 rodadas sobre capturas reais (255, 240 e 105 recortes); tudo aprovado. |
| 2026-11-13 | R2 | Teste ao vivo | EOG | Feito em localhost com uma CÓPIA do banco do CEO no scratchpad e Ollama local; sem custo de OpenAI. |
| 2026-11-13 | R1 | Mapa do droidBrain (graphify) do droidnote | EOG + 2 extratores de docs | 3.404 nós, 10.090 ligações, 154 grupos. `graphify-out/` no .gitignore; segredos, áudio, modelos e imagens no .graphifyignore. |
