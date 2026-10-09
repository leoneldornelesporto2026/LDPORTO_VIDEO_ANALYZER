# Baseline técnico — etapa 01

Base autorizada: workspace atual. Nenhum ZIP foi extraído ou criado; pipeline e identificadores permanecem intactos.

Manifesto: `R4.9-S9-S10-S11`, base `R4.9-S8`. Código declara `{'__version__': '4.4.0', '__build__': 'R4.9-S4-TRACKING-FACIAL'}`.
Conferência: 295/296 hashes coincidem; divergências: src/tests/test_v43_runtime.py.
O ZIP integrado original não está na raiz; o manifesto do export e os fontes atuais permitem a reconciliação disponível.

Execução João Gordo: build **reportado** `R4.9-S4-TRACKING-FACIAL`, run_id `bc598e72ec323ce8`, source_hash `bc598e72ec323ce824bcff749e8c1db2cd7d97627307aaf9cec53042bcd12575`.
Os dois pacotes têm o mesmo run_id e hash de fonte. Não existe prova dos hashes dos fontes executados: essa identificação permanece null.
Estado: `partial/P1_DEGRADED`; causa raiz `04_transcription`. Métricas observadas: `{'candidates_before_dedup': 55, 'candidates_after_dedup': 52, 'final_shortlist_count': 1, 'raw_track_count': 1814, 'valid_track_count': 898, 'micro_track_count': 916, 'persistent_person_count': 653, 'id_switch_count': None, 'active_speaker_confirmed_coverage': 0.0, 'resolved_focus_coverage': 0.01947000028570923, 'zoom_event_count': 0, 'story_payoff_coverage': 0.0, 'semantic_fallback_ratio': 0.09090909090909091}`.
Workflow histórico: `{'review_ready': True, 'review_state': 'READY_FOR_REVIEW', 'preview_approved': False, 'publication_ready': False, 'review_required': True, 'approval_authority': 'curator_human_review_and_preview_hash_gate'}`. Export de análise: `READY`.
55 → 52 → 1 são observações históricas, sem metas de seleção. READY não autoriza publicação.

## Cobertura funcional

| Sessão / funcionalidade | Implementadores atuais | Evidência no export antigo | Estado |
|---|---|---|---|
| S1 — Understanding e contratos | `src/ldporto/understanding.py`, `src/ldporto/editorial.py` | SECOND_CURATION_READY.zip::editorial/story_arcs.json; runtime=ok | implementada; execução atual no export: inconclusiva |
| S2 — Integridade e gates upstream | `src/ldporto/integrity_contracts.py`, `src/ldporto/run_status.py`, `src/ldporto/second_curation_export.py` | SECOND_CURATION_READY.zip::summary/upstream_contract_validation.json; runtime=ok | implementada; execução atual no export: inconclusiva |
| S3 — Integridade narrativa e shortlist | `src/ldporto/editorial_intelligence.py`, `src/ldporto/story_recovery.py`, `src/ldporto/semantic.py` | SECOND_CURATION_READY.zip::editorial/selection_report_s3.json; runtime=ok | implementada; execução atual no export: inconclusiva |
| S4 — Tracking e recuperação facial | `src/ldporto/vision.py`, `src/ldporto/person_reid.py`, `src/ldporto/face_quality.py` | SECOND_CURATION_READY.zip::people/person_identities.json; runtime=partial | implementada; execução atual no export: inconclusiva |
| S5 — Speaker/person e falante ativo | `src/ldporto/active_speaker.py`, `src/ldporto/speaker_roles.py`, `src/ldporto/speaker_signals.py` | SECOND_CURATION_READY.zip::people/speaker_person_summary.json; runtime=partial | implementada; execução atual no export: inconclusiva |
| S6 — Camera Director e Smart Zoom | `src/ldporto/camera_director.py`, `src/ldporto/camera_preflight.py`, `src/ldporto/camera_motion.py` | SECOND_CURATION_READY.zip::camera/camera_summary.json; runtime=partial | implementada; execução atual no export: inconclusiva |
| S7 — Revisão de transcrição e legendas | `src/ldporto/transcription.py`, `src/ldporto/targeted_asr.py`, `src/ldporto/subtitle_review.py` | SECOND_CURATION_READY.zip::subtitles/subtitle_review_s7.json; runtime=ok | implementada; execução atual no export: inconclusiva |
| S8 — Comercial, GC e Stories | `src/ldporto/commercial_gate.py`, `src/ldporto/broadcast_graphics.py`, `src/ldporto/social_output.py` | SECOND_CURATION_READY.zip::editorial/commercial_review_s8.json; runtime=ok | implementada; execução atual no export: inconclusiva |
| S9 — Curator, canário e lote por hash | `src/ldporto/curator_delivery.py`, `src/ldporto/curator_bridge.py` | null; runtime=None | implementada; execução atual no export: não executada nesta etapa; sem prova no export |
| S10 — Aceitação A/B e recursos | `src/ldporto/performance_acceptance.py`, `src/ldporto/performance.py` | null; runtime=None | implementada; execução atual no export: não executada nesta etapa; sem prova no export |
| S11 — Homologação técnica e humana | `src/ldporto/homologation_s11.py` | null; runtime=None | implementada; execução atual no export: não executada nesta etapa; sem prova no export |

Implementada indica fonte presente e reconciliado, não homologação de todos os caminhos. Os estágios antigos contêm artefatos S5–S8 apesar do rótulo S4; não se infere uma versão executada exata desses nomes.

## Evidências e parâmetros

BASELINE.json guarda hashes SHA-256 dos ZIPs, membros consultados, conferência de todos os membros declarados e todos os 296 arquivos do manifesto.
Também preserva stage_status, stage_runtime, metadados da fonte, formato 9:16, fingerprint/modelo e parâmetros semânticos disponíveis. Configuração histórica completa: null; config atual é apenas referência com hash.

- `automacao/evidencias/SECOND_CURATION_READY.zip`: `8339e90f41cce13f93bc61cc6417cecc1058ad37df272d194d7f62060d860349`; 113 membros; divergências no manifesto: [].
- `automacao/evidencias/CHATGPT_REVIEW.zip`: `5a9da201f984d63de2c68dbd9aee4c03365b9e0815b1fb041130d4da02b5f073`; 424 membros; divergências no manifesto: [].

## Riscos e limites

- Build declarado no código está desatualizado em relação ao manifesto; não alterado nesta etapa.
- Hashes do código executado não estão disponíveis; build exato só é conhecido como rótulo reportado.
- Um teste atual difere do manifesto original; o workspace é a autoridade e não foi sobrescrito.
- READY/READY_FOR_REVIEW coexistem com partial/P1_DEGRADED; não significam PREVIEW_APPROVED ou PUBLISH_READY.
- S9–S11 carecem de prova real Windows, Curator independente, revisão humana por hash e A/B medido.
- Identidades e falante ativo não são ground truth; null de id_switch_count preservado.
- Relatório histórico de 582 passed/2 skipped é evidência anterior, não resultado desta etapa.

## Reprodução e validação

`python scripts/dev/baseline_etapa01.py` regenera ambos os baselines de forma determinística com biblioteca padrão, sem importar o pipeline.
Comandos, saídas e exit codes efetivamente executados: `automacao/execucao/checkpoints/CHECKPOINT_ETAPA_01.md`.
Não executados: mídia real, ASR, visão, CUDA, Ollama, renderização, A/B e Curator independente. Homologar no Windows em etapa autorizada com mídia original e revisão humana por hash.
Cache invalidado: nenhum. Próximo passo: revisar divergência do teste e rastreabilidade da build; não reanalisar para corrigir rótulo.
