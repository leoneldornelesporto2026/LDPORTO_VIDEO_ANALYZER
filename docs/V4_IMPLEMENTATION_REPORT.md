# L.D.PORTO VIDEO ANALYZER V4 — relatório de implementação

> Documento HISTORICO da entrega de 2026-10-04, nao resultado da fonte atual.
> O baseline V4.2 encontrou 3 falhas (FFmpeg ausente e exporter legado obsoleto).
> Resultado/evidencia atual: [V4_2_IMPLEMENTATION_REPORT.md](V4_2_IMPLEMENTATION_REPORT.md).

Data da entrega: 2026-10-04.

## Baseline real deste runner

- Ambiente: Linux x86_64, Python 3.13.5.
- Baseline antes das alterações: **116 passed / 1 failed**.
- Falha baseline: teste de integração dependia de `analysis/video_87cfcb5f5347/llm_insights.json`, ausente no pacote exportado.
- Após P0 inicial: 119 passed / 0 failed.
- Após Planner/Preview: 122 passed / 0 failed.
- Resultado final: **130 passed / 0 failed** em ~4.7 s na suíte local sem hardware/modelos externos.

## Correções P0

1. **People tracking `None` × float**: a ordenação de candidatos do Tracker podia cair em comparação de tuplas com `face_similarity=None` versus `float` quando IoU empatava. A ordenação agora usa chave numérica apenas internamente e preserva `None` como ausência de evidência.
2. **Finite JSON**: `NaN/+inf/-inf` são sanitizados para `null`; zero continua zero.
3. **Traceback técnico**: falhas salvam traceback completo em `logs/technical_errors.jsonl` com stage/run/config/checkpoint, sem imprimir segredo.
4. **Causal status**: `failed/unavailable/blocked` são distinguíveis; tracking realmente falho bloqueia descendentes. Capacidade opcional desativada não bloqueia indevidamente source fallback.
5. **Checkpoint visual**: chunks atômicos, checksum, hashes, versão, backend e estado mínimo do tracker.
6. **Exportador**: `WORK_PACKAGE_*` existentes não entram na coleta; o ZIP os gera exatamente uma vez.

## P1/P2 implementado

- Active Speaker V4 com estados explícitos de incerteza.
- métricas tracking versus identidade.
- adaptive sampling preservado e enriquecido.
- movimento global da câmera fonte separado do residual do participante.
- metadata temporal com timebase/PTS/start offset/VFR provável e `[start,end)`.
- Global Camera Planner V4 determinístico, source-first, stay-put, custos de transição e geometrias seguras.
- Camera Director v3 preservado como executor stateful.
- Canary Preview Renderer.
- Preview Verifier em frames renderizados.
- repair loop limitado para clipping severo com fallback conservador.
- Semantic LLM: uma tentativa de reparo estrutural, sem novos IDs/timestamps.
- Second Curation Package V2.
- backend de manual overrides com undo/redo/reset e invalidação por dependência.
- run manifest causal e quality issues exportados.
- schemas novos e round-trip/minimal validation.
- `--doctor` expandido.

## Pesquisa ASD atual

Foram revisados repositórios primários de LR-ASD, Light-ASD, TalkNet e C3ASD. O V4 mantém `heuristic_consensus` como default. Interface para adapters externos existe, porém adapters/pesos externos **não foram incorporados** sem benchmark no Windows/Python 3.11/hardware real. Veja `docs/V4_ASD_CANDIDATES_20261004.md`.

## O que NÃO foi validado neste runner

- Windows 10/11 + Python 3.11 nativo.
- CUDA/NVIDIA/VRAM.
- faster-whisper/CTranslate2 (não instalados aqui).
- Ollama (não estava rodando).
- HF token/acesso/licença do `pyannote/speaker-diarization-community-1`.
- YuNet/SFace/Landmarker locais.
- benchmark real `analysis/video_87cfcb5f5347`, que não veio no pacote.
- soak test de horas com medição real de RAM/VRAM/I/O.
- GUI completa de revisão visual/overrides; backend/contratos foram preparados.
- adapter neural ASD LR-ASD/C3ASD.

## Doctor deste runner

`python analyze.py --doctor` retornou código 2 de forma esperada: FFmpeg/ffprobe presentes, mas faster-whisper/CTranslate2/GPU/Ollama/modelos de visão ausentes. Isso é diagnóstico correto, não falha mascarada.

## Comando exato de homologação Windows

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
python install.py
python -m pytest src/tests -q --disable-warnings
python analyze.py --doctor
python analyze.py "C:\caminho\video real.mp4" --preview --camera-profile natural
```

Leia também `docs/V4_WINDOWS_PY311_HOMOLOGATION.md`.

## Arquivos novos

- `DELIVERY_MANIFEST_V4.json`
- `docs/V4_ASD_CANDIDATES_20261004.md`
- `docs/V4_CACHE_RESUME.md`
- `docs/V4_FINAL_ARCHITECTURE.md`
- `docs/V4_GLOBAL_PLANNER.md`
- `docs/V4_IMPLEMENTATION_REPORT.md`
- `docs/V4_OVERRIDES.md`
- `docs/V4_PREVIEW_RENDERER_VERIFIER.md`
- `docs/V4_REQUIREMENT_MATRIX.md`
- `docs/V4_SECOND_CURATION.md`
- `docs/V4_WINDOWS_PY311_HOMOLOGATION.md`
- `schemas/camera_plan.schema.json`
- `schemas/preview_validation.schema.json`
- `schemas/review_overrides.schema.json`
- `schemas/run_manifest.schema.json`
- `schemas/second_curation_package.schema.json`
- `src/ldporto/asd_backend.py`
- `src/ldporto/global_camera_planner.py`
- `src/ldporto/preview_integration.py`
- `src/ldporto/preview_renderer.py`
- `src/ldporto/preview_verifier.py`
- `src/ldporto/review_overrides.py`
- `src/ldporto/run_status.py`
- `src/ldporto/second_curation.py`
- `src/ldporto/vision_checkpoint.py`
- `src/tests/fixtures/legacy_analysis/llm_insights.json`
- `src/tests/fixtures/legacy_analysis/scenes.json`
- `src/tests/fixtures/legacy_analysis/speakers.json`
- `src/tests/fixtures/legacy_analysis/timeline.json`
- `src/tests/fixtures/legacy_analysis/words.json`
- `src/tests/test_v4_final.py`

## Arquivos alterados

- `analyze.py`
- `config/config.yaml`
- `export_ldporto_project.py`
- `pack_ldporto_for_work.py`
- `src/ldporto/__init__.py`
- `src/ldporto/active_speaker.py`
- `src/ldporto/analysis_quality.py`
- `src/ldporto/camera_director.py`
- `src/ldporto/config.py`
- `src/ldporto/core.py`
- `src/ldporto/director_integration.py`
- `src/ldporto/handoff.py`
- `src/ldporto/media.py`
- `src/ldporto/person_motion.py`
- `src/ldporto/pipeline.py`
- `src/ldporto/reports.py`
- `src/ldporto/semantic.py`
- `src/ldporto/vision.py`
- `src/tests/test_director_integration.py`
- `src/tests/test_v2_perception.py`

## Arquivos removidos

- Nenhum.
