# SOL V3 — visão, ASD e câmera, 2026-10-13

## Evidência consultada e limites

O ZIP `SECOND_CURATION_PARTIAL_jNQXAC9IVRw_20261013_035536_877801_09f678.zip` existe, contém 66 membros e não contém paths absolutos, traversal ou barras Windows nos nomes consultados. O ZIP anterior solicitado, `SECOND_CURATION_PARTIAL_jNQXAC9IVRw_20261012_232326_642182_7f5d97.zip`, não está em `pacotes_para_enviar/`; nenhuma comparação de conteúdo com esse arquivo ausente é afirmada aqui.

Fonte do resultado disponível: `jNQXAC9IVRw`, 19,014 s, 320×240, 15 fps, SHA-256 `e25bcad888afc039e27d316da0471ea08199ed2cf0f424cffd46d05a7902c998`. Foram lidos seus JSONs exportados e checkpoints atuais de `analysis/video_4b0f48e4f4ae/`. Esses artefatos não foram alterados. O replay diagnóstico usa apenas esses dados; não voltou a analisar áudio, imagem ou vídeo da fonte.

## Causalidade confirmada

| Componente | Observação real nos artefatos | Interpretação / correção |
| --- | --- | --- |
| Visão corporal do pacote | YOLO ausente; HOG CPU, 50 chamadas bem-sucedidas; `NOT_READY`, qualidade degradada | Falta de modelo, com fallback explicitamente executado. Não prova recall de corpos sentados. |
| Landmarks / faces | 131 chamadas de landmarker; 113 observações faciais persistentes; 108 com `lip_opening`, 105 com `mouth_activity` | A medição labial ocorreu. `0` janelas positivas não significa detector labial ausente. |
| ASD SPEAKER_00 | 9 janelas acústicas; 4 candidatos de correlação; 2 janelas independentes admitidas na afinidade; 0 suporte positivo qualificado | Dois candidatos têm correlação aproximadamente 0,54006, abaixo do mínimo 0,55. Os outros dois não apresentam bound inferior positivo. Limiares preservados. |
| ASD SPEAKER_01 | Uma janela totalmente sobreposta, sem janela solo utilizável | Áudio misturado não é atribuído à pessoa visível. A voz e a associação continuam `UNRESOLVED`. Nenhuma fusão acústica foi feita. |
| Câmera | 251 janelas preservadas: 189 sem alvo confirmado, 40 sem pessoa observada e 22 com overlap | Os buckets e durações existentes foram reproduzidos. Zero foco/zoom permanece correto nesta evidência. |
| Qualidade de crop | A geometria observada também é bloqueada por `upscale_limit` para a saída configurada | Barreira paralela de resolução, independente de haver hook ou pessoa confirmada. O crop não é forçado em 240p. |

O tempo registrado da etapa 10, 0,031 s, é compatível com leitura de janelas e correlação heurística NumPy já apoiada nos landmarks produzidos pela etapa 07. Não é evidência de que a etapa tenha sido pulada.

O diagnóstico antigo `MAPPED_PERSON_NOT_IN_LOCAL_CANDIDATES` era inadequado quando o resumo não tinha pessoa aceita. Agora uma correlação abaixo do mínimo recebe causa específica; ausência de mapping global aceito é separada de ausência de candidato ou de medição.

## Mudanças incrementais

- `audiovisual_diagnostics.py`, `vision.py`, `active_speaker.py` e `perception_diagnostics.py`: status por janela, correlação/bounds/lag, critério mínimo, timestamps observados de frame e boca, contadores de qualidade facial e dados do áudio realmente lido. Contagens distinguem janelas acústicas, candidatos emitidos, afinidade independente e suporte positivo qualificado. Referência de pixels usa o threshold existente de qualidade de embedding apenas como diagnóstico; não vira novo gate de identidade. Oclusão física não comprovada continua `null`.
- `camera_evidence.py` e `camera_director.py`: `zoom_gate_diagnostics` acrescenta causas paralelas tipadas e estágios oportunidade → alvo → crop → proposta → aceite → render. O campo legado `zoom_zero_root_cause` continua disponível. Os motivos paralelos têm denominadores e não devem ser somados. `focus_decision_audit` passa a declarar também contagens e denominador das janelas preservadas.
- `body_model_paths.py` e `vision.py`: modelo canônico em `models/body/`, com compatibilidade explícita com o mesmo filename no caminho legado da raiz quando o canônico falta. Um arquivo configurado existente sempre vence, inclusive inválido, que será rejeitado em vez de substituído. Diagnóstico passivo não carrega pesos, não faz inferência e nunca promove `READY` por existência de arquivo.
- `core.external_fingerprints` e `vision_checkpoint.py`: fingerprints e chunks usam o asset efetivamente selecionado; mudança do peso legado invalida o cache. O helper novo participa do hash de código do checkpoint.
- Privacidade de YOLO: loader define `YOLO_OFFLINE`, desabilita auto-install e usa `YOLO_CONFIG_DIR` temporário por processo. Eventos/sync/hub são desabilitados apenas em memória; não são utilizados os hooks de settings que gravam a configuração global do usuário. O diagnóstico puro não importa Ultralytics/Torch.
- `audit_camera_s6.py`: replay de análise compactada hidrata os sidecars verificados por checksum. Observações persistentes são pareadas com os frames finais remapeados por ReID. Misturar observações persistentes com IDs brutos de frames da etapa 07 fabricaria ausência de alvo.

## Artefatos e classificação de validação

`vision_artifact_replay.json` registra **artifact-only diagnostic replay**, sem inferência nova: 10 janelas, 4 candidatas, 2 independentes de afinidade e 0 qualificadas; câmera continua com 189/40/22 e 251 preservações. Acrescenta causas `NO_PERSON_OBSERVATION`, `NO_CONFIRMED_AUDIO_VISUAL_TARGET`, `AUDIO_OVERLAP`, `upscale_limit` e `NO_GROUNDED_EDITORIAL_BEAT`.

`vision_canaries/canary_report.json` e os MP4/PNG associados registram **integration_local_synthetic_render**, realizado em CPU. O positivo usa geometria, locutor e hook anotados artificialmente em fonte 1280×720. O Director focaliza, aceita dois eventos ao longo da timeline, e o preview de 2 s consome 30 frames de `SMART_ZOOM_IN`, com escala medida de 3,16049 a 3,16856. O marcador sintético fica com margem mínima de 0,20. O negativo usa 320×240 e locutor incerto: zero foco e zero zoom, 30 frames preservados, margem de 0,37292. Os hashes dos PNGs e dos pixels decodificados, a variância de Laplaciano e as margens foram medidos nos arquivos renderizados.

Esses marcadores são ilustrações geométricas, não rostos detectados nem pessoas reais. Não constituem ground truth de recall facial/corporal, associação humana ou WER. O áudio controlado de duas vozes dos testes é uma onda/envelope sintético com anotações labiais injetadas. O algoritmo mede correlação nesse sinal e respeita overlap, mas isso não homologa duas vozes humanas.

## Comandos reais e resultados

```powershell
.venv/Scripts/python.exe -m pytest -q src/tests/test_sol_v3_visual_diagnostics.py
```

Primeira execução: 1 failed / 7 passed em 0,41 s. O fixture positivo de 12 s não oferecia duração restante suficiente para o gate existente de zoom. O fixture foi ampliado para 30 s, sem alterar o gate: 8 passed em 0,34 s. Após acrescentar render real: 9 passed em 1,90 s. Mais três testes cobrem privacidade sem persistência, hidratação compacta com rejeição de checksum adulterado e alias legado sem contornar link no caminho configurado. O escopo tem 12 testes novos.

```powershell
.venv/Scripts/python.exe scripts/dev/sol_v3_camera_canary.py --output-dir docs/reports/sol_v3_20261013/vision_canaries
.venv/Scripts/python.exe scripts/dev/diagnose_body_model.py --model models/body/yolo11n.pt --device cpu
.venv/Scripts/python.exe scripts/dev/diagnose_body_model.py --help
.venv/Scripts/python.exe scripts/dev/audit_camera_s6.py analysis/video_4b0f48e4f4ae --output docs/reports/sol_v3_20261013/vision_camera_replay --replay
```

Todos retornaram exit code 0. Para repetir o canário, escolha diretório de saída novo: o harness preserva resultados existentes. O diagnóstico passivo, executado após a instalação autorizada coordenada pelo agente principal, encontrou Ultralytics 8.3.200 e o peso local de hash `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`; declarou corretamente `model_loaded=false`, `inference_executed=false`, `NOT_READY`. Carregamento e inferência reais CPU/CUDA são executados/registrados separadamente pelo agente principal; nenhum resultado desses smokes é antecipado aqui.

```powershell
.venv/Scripts/python.exe -m pytest -q src/tests/test_sol_v3_visual_diagnostics.py src/tests/test_vision_decision_integrity.py src/tests/test_stage57_local_yolo.py src/tests/test_s5_speaker_person_active.py src/tests/test_stage28_voice_person_evidence.py src/tests/test_stage29_active_speaker_consensus.py src/tests/test_stage31_focus_audit.py src/tests/test_stage32_safe_camera.py src/tests/test_camera_director.py src/tests/test_stage30_shot_continuity.py src/tests/test_stage41_vision_resources.py src/tests/test_v42_cache.py src/tests/test_s6_camera_director_smart_zoom.py
```

**204 passed em 5,03 s**, exit code 0, com peso e dependência opcionais já presentes. Os fixtures de backend continuam locais/mocked; não carregaram pesos reais nessa regressão. Nenhum teste foi retirado pelo escopo visual.

Após o último hardening de alias/link e propagação dos diagnósticos no helper S6:

```powershell
.venv/Scripts/python.exe -m pytest -q src/tests/test_sol_v3_visual_diagnostics.py src/tests/test_stage57_local_yolo.py src/tests/test_s6_camera_director_smart_zoom.py src/tests/test_vision_decision_integrity.py
```

**52 passed em 2,84 s**, exit code 0. A contagem anterior de 204 corresponde à regressão anterior ao acréscimo do teste de alias/link.

`git diff --check` do escopo retornou exit code 0, com os avisos existentes de conversão futura LF → CRLF.

## Pendente

Homologação de pessoas sentadas/ocultas e duas pessoas reais, erro de associação speaker/person com referência humana e sincronismo em entrevista 720p/1080p de 2–5 minutos continuam **PENDING REAL-VIDEO / HUMAN REVIEW**. O vídeo 240p disponível não é transformado em caso obrigatório de sucesso. Prévia técnica, ASR/ASD sintético e integridade de JSON não concedem `PREVIEW_APPROVED` ou `PUBLISH_READY`.
