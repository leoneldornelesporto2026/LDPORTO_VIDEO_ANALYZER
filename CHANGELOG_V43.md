## R4.9-S2-PIPELINE-INTEGRITY — 2026-10-07

- Auditoria upstream estruturada, fail-closed, contratos únicos e métricas finais consistentes entre ZIP e artefatos locais.
- Estado explícito READY_FOR_REVIEW/PARTIAL separado de preview_approved/publication_ready.
- Validador semântico interarquivos e 17 regressões de integridade incluindo adulterações com hashes válidos.
- CLI de auditoria read-only e cache signature nova somente para 21_second_curation_handoff.

# V4.3 Changelog

## Scope

V4.3 hardens the existing analyzer instead of replacing its architecture. The main changes are evidence-preserving tracking/Re-ID, global speaker-person affinity, commercial gating, editorial boundary/Q&A/story fixes, structured semantic caching/repair, Smart Zoom, rendered preview verification, weighted progress/ETA, replay, causal status, repository cleanup and automatic second-curation export.

## Notable changes

- Tracking: shot-aware continuity, Hungarian assignment, embedding memory and explicit conflict safeguards.
- Re-ID / participants: robust templates, simultaneous-conflict rejection and separation of visual catalog from editorial participants.
- Speaker-person: global affinity over independent evidence windows; ambiguity remains null.
- Editorial: stronger commercial detection, 30-90 s default duration contract, cleaner openings/endings, better Q&A and story/topic hierarchy.
- Semantic: structured output, targeted repair, deterministic cache keys, grounded quote refs and partial Global Review preservation.
- Camera: Smart Zoom state machine, dwell/hysteresis, source-close suppression, upscale/crop safety and source-preserving fallback.
- Preview: rendered canaries, zoom/jitter/pumping/target-loss verification and bounded repair.
- UX: structured progress events, weighted overall progress, ETA and completion screen.
- Handoff: automatic SECOND_CURATION_READY/PARTIAL core ZIP, optional media ZIP, contact sheets, checksums/readiness and SECOND_CURATOR_BRIEF.json.
- Replay/compare: downstream replay with provenance and runtime-comparison guard across different execution scopes.
- Windows/runtime: Python 3.11 contract, FFmpeg/FFprobe discovery, TorchCodec shared-DLL bootstrap and reorganized scripts/requirements.
- Repository: generated PROJECT_EXPORT/WORK_PACKAGE files removed; historical manifests/docs relocated; root wrappers kept for compatibility.

## Audit fixes after commit 39d2193

- Restored the missing canonical `scripts/windows/diagnostics/DIAGNOSTICO_WINDOWS.bat` and `DIAGNOSTICO_GPU_WINDOWS.bat` implementations referenced by root wrappers.
- Added `SECOND_CURATOR_BRIEF.json` to the compact handoff contract and validator.
- Added regression coverage proving `compare_runs` surfaces V4.3 Smart Zoom/readiness/handoff metrics while preserving scope-aware runtime comparisons.
- Made the Windows-wrapper path regression portable without weakening its Windows contract.

## Remaining acceptance work

- Targeted ASR re-review/prioritization remains unfinished.
- A new full-video V4.3 run is required to prove real tracking/active-speaker/camera and runtime improvements.
- Final full-suite homologation must still be rerun on Windows/Python 3.11 after these last audit fixes.

## R4.9/S5 — Speaker ↔ Person e Active Speaker (2026-10-07)

- Separação explícita de identidade persistente e pessoa **falando agora** (`active_person` conservador).
- Consenso audiovisual local exige correlação de boca/áudio com limite inferior, lag coerente, cobertura e margem, além de janelas independentes. Reações apenas com evidência visual explícita.
- Fala simultânea não atribui voz misturada automaticamente; distinção de offscreen / wide shot / falta de frame com indicadores de incerteza.
- Camera Timeline, Global Planner e Director respeitam `active_person` e evitam zoom automático baseado apenas em rosto visível.
- Auditor offline `scripts/dev/audit_speaker_s5.py`, goldset CSV e opção de comparar predições ASD externas sem promover modelo.
- Limites e instruções: [`docs/S5_SPEAKER_PERSON_ACTIVE_20261007.md`](docs/S5_SPEAKER_PERSON_ACTIVE_20261007.md).
- Análise original dos cinco locutores não acompanha o ZIP: **nenhuma taxa de recuperação real é reivindicada**.

## R4.9/S6 — Camera Director e Smart Zoom (2026-10-07)

- Funil causal de janelas de foco por causa, duração e fallback visual; não converte associação global em falante ativo.
- Preflight de crop temporal do mesmo shot e identidade; bloqueio de zoom sem pelo menos duas amostras distintas.
- Split calculado no aspecto real de cada painel (sem deformação) e validado contra amostras seguintes.
- Beats editoriais com `hook_type` comprovado e Q&A completo, mantendo veto a beats sem IDs/timestamps.
- Solicitações de zoom contadas por tentativa real, separadas de oportunidades, eventos aceitos e entrega por keyframes.
- Alerta de borda em preview baseado em geometria, contraste e repetição temporal, não em fração bruta de pixels pretos.
- Auditor offline em pasta/ZIP, com replay opcional apenas do Director: `scripts/dev/audit_camera_s6.py`.
- Testes novos de geometria, split real, zoom, fundo preto, barras artificiais, CLI e replay.
- Guia completo: `docs/S6_CAMERA_DIRECTOR_SMART_ZOOM_20261007.md`. Sem alegação de ganho no benchmark antigo sem seus artefatos.

## R4.9/S7 — Transcrição, reparação e legendas (2026-10-07)

- Identificados pontos de integração: orçamento global de 4 janelas, abertura/desfecho da shortlist nem sempre revisados e presets karaoke sem gating real de alinhamento.
- `17d_targeted_asr` agora respeita `editorial_shortlist`, com janelas de hook/payoff mesmo sem alerta do ASR principal; preserva alternativas sem substituição automática e registra cobertura.
- `17e_subtitle_review_s7` fornece evidência por corte e diagnósticos que distinguem `needs_review` original, fala simultânea, riso e problemas temporais.
- Exports SRT provisórios, CSV humano, validação de aprovação por corte e arquivos separados `.human_reviewed.srt`.
- Social Output e Curator bridge impedem habilitar karaoke pelo simples pedido de preset; exigem texto e alinhamento verificados.
- Código Python 3.11 AST validado; suíte ampliada para 555 passed / 2 skipped (Linux). Windows e taxa real de Emerson pendentes.
- Documentação: `docs/S7_TRANSCRICAO_REPARACAO_LEGENDAS_20261007.md`.

## 2026-10-08 — R4.9/S8 Commercial Gate, Broadcast Graphics e Stories

- Commercial Gate: blocos com IDs/intervalos/segmentos e combinação de intenção comercial fragmentada pelo ASR, limitando propagação e preservando decisão upstream.
- OCR comercial opcional: três frames por trecho; bbox, confiança e status explícitos, sem afirmar duração nem inventar anúncio com base em um frame.
- `17b` e `17c`: estados medidos/skip/unavailable/partial propagados aos checkpoints e relatório de integridade.
- Segunda curadoria e Stories: manter `excluded` e `review` fora da shortlist; manifestar blocos, motivos e visuais; seleção estratificada sem forçar número.
- Títulos com âncora lexical, presets por Story, retângulos de texto provisórios com conflitos de GC/OCR, reação acústica só quando evidenciada; nenhuma publicação automática.
- Auditor offline de pasta/ZIP com CSV de referência humana; teste em fixtures e regressão completa.
- Homologação obrigatória: vídeo real do Emerson/Clóvis, Tesseract/PANNs caso habilitados e renderização Windows/Python 3.11.
