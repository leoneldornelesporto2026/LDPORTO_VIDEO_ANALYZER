# Matriz De Requisitos V4.2

Evidencia: R=artefatos reais anteriores, S=midia/execucao sintetica, F=fixture/mock,
E=execucao local sem modelos, ST=sintaxe/schema estatico. Nenhum item R significa
rerun V4.2 do mesmo video. Alvo runtime Windows/Python 3.11 continua pendente.

| Requisito | Implementacao | Teste/evidencia | Limite restante |
|---|---|---|---|
| Gate A / baseline | suite, py_compile, hashes, docs de ambiente | E: 127/3 baseline nao hermetico; E/ST suite final e 65 compilados | 3.11 real nao localizado |
| Exporter legado | exporter canonico exclui derivados anteriores | test_work_package_has_single_derived_manifest_files; E | original script nao reintroduzido |
| P0.1 install/preflight | install.py, preflight.py, pipeline.py, GUI | test_v42_preflight; F/E doctor | clean install 3.11/modelos/GPU |
| P0.2 doctor | mesmo run_preflight para CLI/GUI | E: doctor exit 2 honesto | imports/assets externos ausentes |
| P0.3 ASR | transcription.py; raw/timestamps/review metrics | test_v42_perception, test_corrupt_asr_chunk; F | audio real/ground truth; sem auto-replace sem evidencia |
| P0.4 diarizacao/exclusive | diarization.py | test_exclusive_alignment_keeps_overlap_evidence; F | Community-1/HF real nao executado |
| P0.5 Q&A | question_candidates/pairs, qa_metrics | perguntas sem speaker; transicao relevante; F/R | relevance lexical nao acuracia anotada |
| P0.6 scenes/shots | shots com classificacao e limites compartilhados explicitos | test_shot_classification; F/R 556=556 | fades/static-shots nao inferidos sem evidencia |
| P0.7 qualidade tracking | person_reid metrics/quantis/unknowns | microtracks e no-embedding; F/R | IDs switches/picos reais nao medidos |
| P0.8 camadas | raw_tracks -> persistent people -> participants | microtracks_do_not_explode_participants; F | thresholds dependem do benchmark real |
| P0.9 Re-ID | templates faciais, margem, veto simultaneo | strong merge, same screen no embedding, simultaneous; F | busca limitada pode under-merge |
| P0.10 participantes | thresholds/status, reports layer | offscreen speaker + microtrack tests; F | host/guest sem diarizacao nao inventados |
| P0.11 active speaker | projection IDs + consensus + presence | v2/v4 uncertainty/consensus; F | ASD neural nao integrado/promovido |
| P1.1 enums | editorial.py + schemas + normalization | context enum param tests; F/R | legacy field e projection |
| P1.2 PT-BR | locale strict + lexical wrong-language gate | english rejected, global repair; F/R | detector lexical nao linguagem calibrada |
| P1.3 topicos/hierarquia | stopwords, merge, sections, primary qualified | keyword soup unresolved, multi-topic section; F/R | tema profundo requer LLM real/revisao |
| P1.4 entidades | textual cue/self intro + lexical filter | Nao/Ele/Era/Deixa; F/R | nomes civis nunca de rosto |
| P1.5 arcos | marker/QA/discussion grounded candidates | multisection no old regex; F | payoff desconhecido permanece null |
| P1.6 boundaries | sentence/reference/story completion + duration knobs | v2 story expansion; F | nao cortar significado por duracao |
| P1.7 dedup | sweep NMS, exact primary + alternates | exact/high overlap/distinct tests; F/R 176->163 | alta sobreposicao nao basta para equivalencia |
| P1.8 comercial | multicue classifier + default exclusion | ads vs interview; F/R 6 candidatos | heuristica, nao anotacoes humanas |
| P1.9 ranking | raw/components/weights/penalties/final/version | explicit utility and null components; F | utilidade, nao viralidade |
| P1.10 global review | IDs/evidence/literal validation, generated copy | invented ID/timestamp/literal rejection; F/R | justificativa semantica precisa revisao humana |
| P1.11 semantico/cache | checksummed chunks, budget, every-chunk accounting | one repair/fallback/corruption/cache; F | Ollama real/ganho temporal nao medido |
| P1.12 causal status | run_status effective/degraded/unaffected | degraded camera not fully valid; F/R | direct runtime externo pendente |
| P1.13 camera metrics | coverage/focus/source/switch separated | temporal=1 focus=0 test; F/R | cobertura nao prova inteligencia |
| P1.14 microinterrupt | observed A-B-A planner preference + Director hold | A40 B1 A; F | fortes reacoes/cuts continuam excecoes seguras |
| P1.15 preview | real decoded pixels + bounded accepted repair | FFmpeg/OpenCV S; failed repair F; optical-flow F/S | clipping/subtitle-safety dedicada nao calibrados |
| P1.16 V3 handoff | canonical ID cross-file validation, scores/copy/thumbnails | test_v4_final + canonical refs; F/S | preview video apenas ref ao run original |
| P1.17 relatorios | participants corretos + temporal/focus + safe HTML | exports + full pipeline S + HTML F | GUI manual/assistive tech pendente |
| P1.18 compact/export | 6 compact artifacts + indexed chunks + states | >32MB / empty / missing chunk / self-test; E/F | memoria do processamento nao totalmente streaming |
| P1.19 monolitico | references default, legacy opt-in, safe hydration | traversal/checksum + Director-only; E/S | consumidores legados precisam modo explicito |
| P1.20 storage | iterencode/atomic + sizes/top20/counts | exports e full workflow; E/S | pico RSS/VRAM not_measured |
| P1.21 thumbs | evidence/time priority + qualified visual identity | fragmented new-person not promoted; F | expressao/eyes/dedup perceptual nao medidos |
| P1.22 quality gates | P0_FAIL/P1_DEGRADED/PASS_WITH_WARNINGS/PASS | reports e gates causais; F/E | verdict nao certifica acuracia |
| P1.23 invalidation | DAG + external/code/config/package scoped | diarization/ranking/export no upstream invalidation; F/S | trocar modelos requer fingerprints disponiveis |
| P1.24 resume | ASR/semantic/vision checksums + progress + sampling state | corrupt caches + real decoder interrupt/resume; F/S | soak longa duracao/codec VFR real |
| P1.25 determinism | stable IDs/order/digest/provenance/options | planner equality, resume equality; F | LLM non-determinism; tempos fora de equivalencia normalizada |
| P1.26 security | argv, redaction, local HTTP, bounds, hash/model/path guards | actual child/HTTP + fixtures; E/F | scanner heuristico nao auditoria formal |
| P2.1 vision perf | fase decode/detect/body/embed/landmark/motion/I/O; stable sampling | stable burst + real decoder S/F | HOG/YOLO comparacao real nao executada; default mantido |
| P2.2 semantic budget | max calls/hour + max chars/full global request + profiles | full payload budget, cache; F | tokens estimados por chars/4, nao tokenizer |
| P2.3 compare_runs | OLD NEW tolerant + offline editor audit | legacy/missing fields, no mutation; F/R | nao presume fonte igual sem hashes |
| P2.4 acceptance | directional metrics sem claims de accuracy | R: only deterministic old artifacts reprocessed | same-video runtime 3.11/GPU requerido |
| P2.5 configuracao | typed/validated defaults + YAML/docs | config/syntax gates; ST/F | tuning exige novo benchmark |
| GUI / Windows | checkboxes/state, secret in memory, no global Ollama stop | static syntax/BAT + CLI S/E | GUI acessibilidade/manual e 3.11 real |
| Discovery/final ZIP | WORKER_DISCOVERY_AUDIT + final report + inspect-zip | self-test CRC/sha/all-entry secret scan; E | formal model/license/long-run acceptance pendente |