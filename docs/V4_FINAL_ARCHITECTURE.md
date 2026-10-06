# L.D.PORTO VIDEO ANALYZER V4 — arquitetura final

## Fluxo

`MEDIA → AUDIO → ASR → DIARIZATION → SCENES → PEOPLE TRACKING/CHECKPOINTS → RE-ID → PERSON RESIDUAL MOTION → ACTIVE SPEAKER V4 → SHOTS → CAMERA TIMELINE → SEMANTIC/UNDERSTANDING → GLOBAL CAMERA PLANNER → CAMERA DIRECTOR v3 → CANARY PREVIEW RENDERER → PREVIEW VERIFIER/BOUNDED REPAIR → SECOND CURATION PACKAGE V2`

O Global Planner não substitui o Camera Director. O Planner escolhe uma intenção editorial global determinística; o Director preserva estado, hysteresis, minimum hold, cooldown, hard safety, smoothing e limites físicos de movimento. O Preview Verifier observa frames efetivamente renderizados, não apenas JSON do Planner/Director.

## Contratos principais

- `camera_plan.json`: plano editorial global, schema 4.0.
- `camera_director_timeline.json`: execução/refinamento temporal v3.
- `preview_validation.json`: problemas observados no preview renderizado.
- `preview_canaries.json`: intervalos curtos de risco renderizados para homologação.
- `second_curation_package.json/.md`: pacote de evidência para segunda curadoria.
- `run_manifest.json`: causalidade de falhas, módulos válidos e primeiro estágio a reprocessar.
- `quality_issues.json`: problemas/limitações declarados.

## Regras de evidência

`null` significa evidência insuficiente, não zero. `NaN`/`±inf` nunca saem nos contratos JSON; são sanitizados para `null`. Active speaker pode declarar `KNOWN_PERSON`, `UNKNOWN_PERSON`, `OFFSCREEN_SPEAKER`, `MULTIPLE_SPEAKERS`, `INSUFFICIENT_EVIDENCE` ou `NO_CLEAR_SPEAKER`, e não força um PERSON_ID.

## Tempo

Intervalos usam `[start,end)` em segundos. Metadata preserva `time_base`, PTS inicial quando fornecido, start times de áudio/vídeo, offset A/V, frame rates reportados, rotação e flag de VFR provável. O decoder/container timestamp tem prioridade; `frame_index/fps` é fallback.

## Movimento

A visão estima movimento global de translação da câmera fonte por phase correlation entre amostras quando a evidência é suficiente. `person_motion` expõe velocidade observada, velocidade da câmera fonte e velocidade residual do participante. Isso evita confundir pan real com deslocamento do sujeito.
