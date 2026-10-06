# V4 — Matriz requisito → implementação → teste → limitação

| Gate / requisito | Implementação | Teste/evidência | Resultado | Limitação |
|---|---|---|---|---|
| A. Baseline reproduzível | fixture legado sanitizada e suíte independente de `analysis/` | suíte completa | IMPLEMENTED + TESTED | baseline original tinha 1 falha por arquivo pessoal ausente |
| B. Nullable/finite P0 | ordenação do Tracker segura para `None`; JSON sanitiza NaN/inf para null | regressões específicas | IMPLEMENTED + TESTED | vídeo real original não foi anexado |
| C. Checkpoint visão | chunks atômicos com checksum/hashes + estado do tracker | round-trip + corrupção rejeitada | IMPLEMENTED + SYNTHETICALLY TESTED | interrupção de vídeo longo real requer homologação local |
| D. Testes sem analysis pessoal | `tests/fixtures/legacy_analysis` | suíte limpa | IMPLEMENTED + TESTED | — |
| E. Exportador sem duplicatas | derivados excluídos da coleta e gerados uma vez | ZIP aberto e `namelist` validado | IMPLEMENTED + TESTED | — |
| F. Sem speaker/person artificial | Active Speaker V4 com estados de incerteza | testes de consenso/ausência | IMPLEMENTED + TESTED | ASD neural externo não é default |
| G. Global Planner | DP/Viterbi-like determinístico, stay-put e transition cost | testes de determinismo/safety | IMPLEMENTED + TESTED | budget editorial avançado ainda é heurístico |
| H. Director v3 preservado | Planner é advisory; Director mantém safety/hold/hysteresis | regressões legadas | IMPLEMENTED + TESTED | — |
| I. Hard cuts | hard boundaries continuam no Director | regressões existentes | IMPLEMENTED + TESTED | benchmark real pendente |
| J. Split/two-shot geométrico | candidatos só entram após geometria válida | testes Planner/Director | IMPLEMENTED + TESTED | detector real depende dos modelos locais |
| K. Preview real do Director | renderer consome timeline/keyframes reais | teste MP4 técnico | IMPLEMENTED + SYNTHETICALLY TESTED | não é render social final |
| L. Verifier olha preview | leitura de frames renderizados + ffprobe | teste de verifier | IMPLEMENTED + SYNTHETICALLY TESTED | face detector Haar é fallback quando modelos ausentes |
| M. Repair loop | clipping severo → fallback conservador → revalidação | testes de preview | IMPLEMENTED + SYNTHETICALLY TESTED | só classes seguras possuem auto-repair |
| N. Second Curation V2 | pacote grounded com IDs/evidências/câmera/contexto | teste de IDs resolvíveis | IMPLEMENTED + TESTED | qualidade editorial final é revisão humana/ChatGPT |
| O. Compat v1/v2/v3 | outputs antigos preservados, novos opcionais | suíte legada | IMPLEMENTED + TESTED | analyzer version sobe para 4.0.0 |
| P/Q. Testes | regressões legadas + V4 | `130 passed` | IMPLEMENTED + TESTED | runner Linux/Python 3.13 |
| R. synthetic/mock/real | relatório final separa categorias | documentação | IMPLEMENTED | benchmark real não executado |
| S. not_measured honesto | métricas sem ground truth usam `not_measured` | contracts/tests | IMPLEMENTED + TESTED | algumas métricas exigem anotação humana |
| T. Windows/Py3.11 | alvo/documentação/CRLF/quoting sem shell | BAT CRLF + comandos vetoriais | IMPLEMENTED + LOCAL VALIDATION REQUIRED | ambiente atual não é Windows 3.11 |
| U. Segredos | exportador exclui nomes sensíveis; token nunca impresso | inspeção final do ZIP | IMPLEMENTED + TESTED | revisão humana continua recomendada antes de distribuição |
| V. ZIP limpo | `.venv`, mídia, modelos, caches e ZIPs antigos excluídos | inspeção do pacote final | IMPLEMENTED + TESTED | pesos/modelos devem ser instalados fora do pacote |
| GUI review completa | backend de overrides + invalidação/undo/redo | testes backend | IMPLEMENTED + LOCAL/GUI VALIDATION REQUIRED | editor visual completo de todos overrides não foi construído nesta execução |
| ASD neural opcional | interface + candidatos pesquisados | docs + doctor | INTERFACE IMPLEMENTED | adapters LR-ASD/C3ASD ainda não implementados/benchmarkados |
| Real-video benchmark `video_87cfcb5f5347` | comandos e métricas preparados | busca no pacote | NOT RUN | `analysis/video_87cfcb5f5347` não veio no ZIP |
