# V4.4.0

Runtime oficial: Windows/Python 3.11.x; implementação e testes locais em 3.11.9.

- Contadores reais V4.3 reconciliados: 5755 hipóteses online no último log,
  5758 finais; 6085 tracklets finais, dos quais 1818 válidos e 4267 micro.
- Evidência acústica com lag/variância; consenso e conflitos preservados;
  estados confirmado/provável/incerto/offscreen e diagnóstico por speaker.
- Fallback dominante separado da identidade acústica, estados de câmera,
  geometria de cabeça, dwell, controle de movimento e gráficos persistentes.
- Commercial Gate V3 cobre Havan/Openbox com spans e OCR opcional localizado.
- Repair semântico por item mantém fatos válidos; story recovery preserva
  segmentos literais; ASR dirigido gera alternativas sem reescrever a fonte.
- Contrato SECOND_CURATION_DECISIONS V4.4 e interface de providers locais;
  visuais promovidos sob demanda conservam o catálogo e o ZIP original.
- Curator: import direto, micropercepção por corte, GC único em crop/split,
  verifier sobre frames renderizados e aprovação vinculada ao MP4/plano.
- ETA com histórico local compatível; cleanup por preview/confirmacão e
  leases de mídia; seleção/download explícito de fonte; UX de modelos.

O schema semântico de extração e seu prompt continuam 4.3.0, porque o contrato
de fatos não mudou. A implementação de repair e os fingerprints de módulos
mudaram; caches downstream são invalidados sem invalidar ASR/visão por decisões.
O schema compacto segue 2.0; o novo schema de decisões é 4.4.0.

Limites e evidências por bloco constam no Implementation Ledger.

## Finalização pós-limite do agente

- Ledger e benchmark report sincronizados com as métricas já confirmadas do full run:
  tracking 2754.265 s, 6085/1818/4267 raw/valid/micro, speaker/person 15.0490% e active speaker 9.6733%.
- P0-A promovido para `VERIFIED_FULL_RUN` quanto à cobertura observada, sem alegar acurácia de identidade sem anotação humana.
- Compare possui regressão explícita separando `proposed_zoom_event_count` de `zoom_event_count` entregue.
- Adicionado `scripts/dev/finalize_v44.py`: finaliza compare/validação apenas quando a retomada completa tiver `return_code=0`, lock removido e artefatos finais presentes; não executa inferência.
- Documentado em `docs/V44_FINALIZATION.md` o que depende do término real do full run local.

## Hotfix de contrato Understanding pós full-run limpo

- O full run de 07/10/2026 revelou `16_understanding: failed` com `list object has no attribute get`; o erro bloqueava `17b_broadcast_graphics`, `17c_commercial_visual` e `17d_targeted_asr`.
- A fronteira `semantic -> understanding` agora normaliza somente estruturas de contrato conhecidas (`topics`, `moments`, `questions_answers`, `program_sections` e `editorial_review`), preserva objetos válidos e registra `semantic_contract_normalized` quando recebe formato inesperado. Nenhuma evidência é inventada.
- `build_main_moments` tolera payload editorial não-mapeável sem transformar o conteúdo inválido em score.
- Regressão adicionada para lista legada/provider em `editorial_review` e linha semântica aninhada.
- A versão permanece 4.4.0 propositalmente: mudar `__version__` invalidaria caches de estágios anteriores. O hash de `understanding.py` invalida apenas o estágio 16 e downstream no resume.
- Evidência do run que revelou o hotfix: semantic fallback 8,6957%, speaker/person 15,0490%, active speaker 9,6733%, Camera Director 10,9982% de foco resolvido e 428 decisões; Smart Zoom entregue permaneceu 0.

## R3 — estabilização pós-benchmark parcial

- Incorporado o hotfix de contrato `semantic -> understanding` observado no full run: payloads lista/não-mapeáveis não derrubam mais `16_understanding`; somente objetos válidos são preservados e a normalização fica explícita em `notes`.
- Relatórios e segunda curadoria agora também toleram `ollama_editorial_review` legado em formato lista; conteúdo inválido não vira evidência e não derruba o handoff.
- O handoff passa a exportar `readiness_reasons`, explicando por que uma capability ficou indisponível (`shortlist_empty`, evidência visual incompleta, preview não verificado etc.).
- Corrigido link duplicado no relatório HTML.
- Export do projeto não polui mais a raiz ao ser extraído: metadados do pacote ficam em `.package/PROJECT_EXPORT_*`.
- Testes que dependem de display Tk ou metadata Git agora fazem skip explícito quando executados a partir de pacote exportado/headless, sem mascarar regressões no ambiente Windows/Git normal.
- Adicionado build label `R3` sem alterar `__version__ = 4.4.0`, preservando compatibilidade de cache/resume. Proveniência e pacote de segunda curadoria carregam o build label.
- Suíte de estabilização: 410 testes verdes, 2 skips ambientais; `compileall` verde e exportador validado em pacote limpo.

## R4.2-INTEGRITY-VISION
- Hardened nested Semantic -> Understanding contracts with path-level diagnostics.
- Fail-closed downstream publication/Stories on Understanding failure.
- Enforced commercial exclusion invariants and bounded commercial-block propagation.
- Added conservative face-supported micro-track reentry to established identities.
- Added causal Smart Zoom opportunity/request/accepted/delivered/aborted diagnostics.
- Regression suite: 423 passed, 2 environment skips in the audit container.
