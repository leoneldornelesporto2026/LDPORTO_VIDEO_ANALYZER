# V4.4 Implementation Ledger

Runtime oficial: Windows/Python 3.11.x; validação local usa 3.11.9.
Branch: feature/v4.4-evidence-driven-editor. Sem commit/push/merge/reset/clean.
Curator preservado em `.cache/v44_preserved_curator` antes da primeira edição.
Esse snapshot fica no workspace Analyzer; os renders originais do Curator
continuam em `LDPORTO_VIDEO_CURATOR/output` (12 finais e um preview).

Baseline reconciliado: [V44_BASELINE_RECONCILIATION.md](V44_BASELINE_RECONCILIATION.md).
O full run **V4.3** local existe. Nenhuma validação V4.4 recebe crédito por isso.

Status permitidos: PENDING, IN_PROGRESS, VERIFIED_UNIT, VERIFIED_FIXTURE,
VERIFIED_REPLAY, VERIFIED_FULL_RUN, BLOCKED.

| Bloco | Estado | Evidência / próxima validação |
| --- | --- | --- |
| Baseline / contadores | VERIFIED_FIXTURE | Contagem real e timestamps reconciliados; snapshot com checksums; regressão discriminante |
| P0-A diagnostics / affinity / active speaker | VERIFIED_FULL_RUN | Replay e full run convergiram: speaker/person 15.0490%, active speaker legado 9.6733%, provável sem overlap 8.0853%, confirmado 0%. Cobertura foi reproduzida no vídeo completo; acurácia de identidade contra anotação humana continua não certificada. |
| P0-B câmera / layouts / GC | VERIFIED_REPLAY | 146 testes verdes; foco resolvido 15.1801%, dominante visual 9.8220%, speaker apoiado 5.3582%; zoom entregue 1.0x. Composição final/visual real de GC validada no Curator |
| P0-C comercial | VERIFIED_REPLAY | 138 testes verdes; três false negatives reais excluídos com spans; replay dos 209 principais: 2→7 comerciais; OCR opcional por candidato |
| P0-D semantic / story / ASR | VERIFIED_REPLAY | 180 testes verdes; dois arcos completos recuperados; ASR real em 9.34s de áudio, raw preservado; fallback V4.4 só será medido no full run |
| P1 segunda curadoria / importação | VERIFIED_REPLAY | 50 testes Analyzer e 21 Curator; pacote real 213 candidatos, shortlist 11 após gate, visual promovido e import direto verificados; preview refinado no bloco seguinte |
| P1 Curator refinamento | VERIFIED_REPLAY | 35 testes Curator; seis renders reais de oito segundos e preview de candidato promovido de 89.22s; GC único em crop/split; verifier sobre MP4; revisão atual dos renders ao fim do benchmark |
| P1/P2 operações | VERIFIED_UNIT | ETA/histórico compatível, cleanup por confirmação com leases e checagem de arquivo alterado, rehydration com SHA256, UX de modelos, ruído preservado no debug |
| Suíte legada | VERIFIED_UNIT | 352 passed em Windows/Python 3.11.9 antes dos patches |
| Full run V4.4 / compare final | IN_PROGRESS | Retomada válida confirmou diarização, tracking e P0-A no vídeo completo. Tracking 2754.265s; 6085/1818/4267 raw/valid/micro; speaker/person 15.0490%; active speaker 9.6733%. Semântica estava em 13/46 quando a sessão do agente atingiu o limite; compare/report final aguardam o pipeline concluir. |

## P0-A

Alterados: active_speaker.py, vision.py, pipeline.py, reports.py, replay.py;
adicionados baseline_audit.py, perception_diagnostics.py, speaker_signals.py e
test_v44_perception.py. Primeiro 5 failures/1 pass reproduziram as lacunas;
regressão de lag também falhou antes do módulo. Depois: 45 passed.
Sinais visuais corroborativos só preservam ou reduzem evidência acústica; posição
de tela não entra na identidade. Confiança continua proxy heurístico não calibrado.
Replay real em `.cache/v44_validation/P0A_audio_replay`: nenhuma nova inferência
ASR, visão ou LLM; áudio/mouth recalculado das observações/WAV existentes. Diagnóstico
dos 23 speakers e heatmap de fragmentação gerados. Correlações negativas com IC
cruzando zero ficam registradas como fracas, não como contradição comprovada.
Ganho de coverage medido em replay não prova acurácia de identidade nem melhoria
do runtime total. A métrica legada inclui alguns overlaps incertos; a nova parcela
provável os separa explicitamente. Não houve relaxamento de thresholds acústicos.

## P0-B

Alterados camera_director.py, director_config.py, director_integration.py,
analysis_quality.py, config.py/config.yaml, pipeline.py e reports.py. Adicionados
camera_evidence.py, interview_layout.py, broadcast_graphics.py, test_v44_camera.py
e scripts/dev/replay_camera_v44.py. Regressões primeiro falharam; 146 testes de
câmera/integração verdes, incluindo vídeo MJPG real de seis segundos.

Replay P0-A + câmera em `.cache/v44_validation/P0B_camera_replay`: cobertura de foco
15.1801% (baseline 0), 9.8220% por face dominante, 5.3582% apoiado em speaker/person.
Nenhuma inferência upstream foi repetida. Estes números medem evidência amostrada,
não acurácia anotada. Split/two-shot continuam zero neste replay.
Sete pedidos de Smart Zoom não produziram zoom: máximo/medio entregue 1.0x;
não contar pedidos como ganho. A opção de fallback agora também está nos defaults
do runtime. GC usa oito frames por candidato selecionado, sem varrer o programa;
não realiza OCR obrigatório nem comprova identidade. Composição final e validação
visual de GC entram no bloco Curator, sem sobrescrever renders existentes.

## P0-C

Regressões reais extraídas dos segmentos canônicos do full run V4.3 (hash do vídeo
na fixture): Havan MOMENT_00038_0001 e Openbox MOMENT_00008_0001/00009_0001.
Quatro failures antes da implementação, depois 138 testes verdes, incluindo
comercial/ranking V4.2/V4.3 e integração. Alterados editorial.py/pipeline.py;
adicionados commercial_gate.py, fixture, test_v44_commercial.py e replay script.
Flexões brasileiras, preço por extenso, Pix/urgência corroboram CTA/oferta;
marca/preço isolados e negação não bastam. OCR tem origem e offsets próprios,
é opcional e limitado a dois frames por candidato; não altera a fala ASR.

Replay `.cache/v44_validation/P0C_commercial_replay`: 209 principais (alternates
neste replay não recontados), comerciais 2→7. Os dois adicionais, MOMENT_00011_0000
e MOMENT_00011_0002, contêm parcelamento/loja/CTA literal de Openbox. Os cinco
acréscimos foram conferidos pelo texto, sem inferência LLM/OCR/ASR nova. Não é uma
estimativa de acurácia global nem benchmark full-run V4.4.

## P0-D

Alterados semantic.py, understanding.py, transcription.py, config.py, pipeline.py,
reports.py; adicionados story_recovery.py, targeted_asr.py, regressões e script de
ASR curto. As regressões reproduziram range parcial, buraco de coverage e perda
de itens válidos após falha do repair. Depois: 180 testes verdes com integração.
Repair expande ranges por item, envia somente itens inválidos/intervalos ausentes
e preserva irmãos válidos. Falhas mantêm componentes validados e fallback por
segmentos não cobertos; semantic_chunk_profile exporta escopo/categorias/preservação.

Os 12 fallbacks reais V4.3 eram **coverage de tópicos**, conforme os registros de
15_semantic: não eram falhas de transporte/modelo. Baseline permanece 26.0869%.
O novo repair para buracos está validado por fixture; nenhuma redução percentual
de fallback real V4.4 foi inventada antes da inferência/full run.

Replay de story: dois arcos completos recuperados (antes zero), desfechos literais
SEG_02578 (aplausos, 7804.66–7815.78) e SEG_02620 (transformação, 7908.6–7913.0),
com interrupções e vínculos de tópico. Inferência heurística ainda needs_review.
ASR real curto em `.cache/v44_validation/P0D_targeted_asr`: 2 janelas desses payoffs,
9.34s de áudio, alternativas em cache, zero substituição canônica. Teste real de
extração/cache também verde. Confiança de texto é separada de alinhamento temporal,
cuja probabilidade permanece null por falta de calibração independente.

## P1 contrato / visuais / importação

Contrato `schemas/second_curation_decisions.schema.json` V4.4, compilador portátil
idêntico nos dois projetos e interface SecondCuratorProvider/ManualJsonProvider;
nenhuma API externa obrigatória. Ações approve/reject/promote/demote/commercial,
merge/split/expand/shrink/alternate/duplicate, limites e referências validados.
On-demand gera novo ZIP conservando original/catalog completo; previews opcionais
ficam externos ao core. CLI exportador aceita --visuals-on-demand/--candidate.

Curator: second_curation_import.py, contrato, approval.py, loader/curator/pipeline,
GUI/CLI e regressões. Botão IMPORTAR SEGUNDA CURADORIA; fontes FIRST_PASS,
SECOND_CURATOR, MANUAL_OVERRIDE e AI_SECOND_CURATOR. Imports em cache próprio;
overrides originais preservados. Checksum, origem e paths verificados antes de
materializar; decisões mantêm limites explícitos sem snap silencioso. Aprovação
V4.4 depende do hash do plano e do MP4 revisado, mantendo arquivos anteriores.

Validação: 50 testes Analyzer (contrato/handoff/runtime), 21 Curator incluindo os
18 existentes. Pacote real derivado do replay: 213 candidatos, shortlist 11
(Havan removida), READY; MOMENT_00042_0001 recebeu contact sheet sob demanda e
foi importado via decisões como SECOND_CURATOR. Evidência no cache P1; seleção
de um candidato valida integração, não representa revisão editorial final de
todo o episódio. Preview/câmera/GC reais serão medidos no próximo bloco.

## P1 Curator — micropercepção, câmera final e verifier

Novos micro_perception.py, camera_refinement.py, final_camera.py, camera_verifier.py;
alterados render.py/pipeline.py/subtitles.py/approval.py. O SDK puro de câmera
do Analyzer foi copiado para o Curator, mantendo seu funcionamento independente.
Detector local YuNet, tracks restritos ao corte/shot, 6 fps, cache com fonte,
configuração/modelo/OpenCV/código/checksum. Não atribui identidade acústica.
O plano seguro do Analyzer pode evitar reanálise de faces; fonte ausente não
reexecuta Analyzer. A composição FFmpeg de crop e split preserva uma cópia
inteira do GC. Regressão real primeiro reproduziu GC duplicado (duas faixas).

29 testes Curator verdes, incluindo os 18 existentes, cache/cuts/deadzone,
geometria/dwell, traversal, aprovação e FFmpeg nas duas resoluções com áudio/ASS.
Seis renders de 8s no vídeo original: interview 3200–3208, comercial 7059–7067,
payoff 7800–7808. Cada corte teve 48 amostras locais. Foco visual: 0%, 0%, 32.91%.
A revisão de imagens revelou crop cortando GC; foi corrigido e rerenderizado.
Evidência em `Curator/.cache/v44_validation/real_camera`.

Import direto real: 213 candidatos preservados; candidato rank original 15
MOMENT_00042_0001 promovido. Preview real 7726.56–7815.78 (89.22s), com legendas,
18 decisões, 8 resets, 10 mudanças locais, 41.47% foco visual, zero identidade
confirmada. Verifier amostrou 12 frames renderizados: faces visíveis em 100%
das amostras, nenhum alerta de borda. Isto é proxy, não acurácia anotada.
Nenhuma aprovação humana foi fabricada: lote desse preview permanece bloqueado.

## P1/P2 operações

44 testes de operações/runtime Analyzer e suite Curator verdes. Regressões
primeiro falharam: ETA escalava indevidamente custo futuro e cleanup/histórico
compatível não existiam. `storage.py` portátil protege JSONs/legendas/dados
editoriais/contact sheets/pacotes/renders e arquivos em uso; executa somente
lista confirmada, dentro dos caminhos resolvidos e sem alterações pós-preview.
Nenhum arquivo pesado real foi removido durante a implementação. GUI oferece
preview com bytes atuais/liberáveis/preservados. Rehydration exige arquivo
original verificado; download é uma escolha explícita. Modelos visuais possuem
botões baixar/abrir pasta/copiar comando. Clearcut permanece no log de debug
e é suprimido da UI de execução normal. Eventos de falha sem stage mantêm o
teste permanente V4.3. Dashboard JSON e links HTML mostram evidência/causalidade.

Correção de métricas: pedidos de zoom são separados de movimento entregue;
replay final mantém 7 pedidos e **0 eventos entregues / 1.0x**. Coverage do
director passa a contar foco/split entregues; disponibilidade de amostras
visuais fica em `camera_director_visual_sample_coverage`.

## Correção durante o benchmark — cache de diarização

O primeiro full run V4.4 iniciou em 2026-10-07 00:13:39 UTC, após suites verdes.
ASR terminou em 731 s, mas a etapa 05 rejeitou community-1 sem token, apesar
de o preflight ter carregado os mesmos pesos completos do cache Hugging Face.
Foi solicitada parada segura ao final da etapa de cenas, preservando checkpoints,
manifestos e logs. Esta tentativa não valida qualidade de diarização/speaker.

Regressão `test_v44_diarization_cache.py` reproduziu a falha antes da correção.
`model_cache.py`, `diarization.py`, `preflight.py` compartilham resolução local;
o fingerprint da etapa 05 inclui o helper. 51 testes afetados passaram.
Inferência real de 20 s do original (3200–3220) carregou community-1 sem token:
2 agrupamentos acústicos, 4 turns, 7.70 s, confiança não fornecida permanece null.
Evidência: `.cache/v44_validation/diarization_cache_fix/DIARIZATION_CACHE_FIX_VALIDATION.json`.
A retomada usa apenas checkpoints da própria tentativa V4.4, com registros
separados e sem comparar seu wall time isolado ao full run V4.3.

Revisão final adicionou regressões para proteção de renders quando selecionados
como fonte opcional, separação CPU/GPU/driver no histórico de ETA e trajetória
do Analyzer recortada no meio de uma decisão. Curator: 34 testes verdes.
Na transição LLM→ASR direcionado, o modelo Ollama local já concluído é liberado
antes de carregar Whisper; cache de reparo não dispara unload nem inferência.
GUI abre as opções de modelos visuais quando preflight falha com pesos ausentes.

`apply_commercial_refinement` atualiza shortlist e contadores após o gate visual,
sem deixar contagem anterior na análise entregue. Regressão verificou exclusão
e preservação da proposta original. Comparador não calcula delta de tempo total
quando há cache, e mostra tempo original das etapas retomadas sem atribuir ganho.
52 testes de compare/export/runtime verdes. Feedback opcional de performance
possui schema compartilhado, valida fonte/data/faixas e preserva desconhecidos;
armazenamento local não dispara aprendizado nem aprovação.

Replay passa a incluir gráficos broadcast existentes e fingerprints de fatos
e artefatos de speaker, além do helper de story recovery. 41 testes replay/runtime
verdes, com exclusão comercial a partir do contexto canônico sem nova inferência.
Preview opcional sob demanda possui ZIP de mídia separado e referência por
candidato com member/bytes/SHA256; regressão reproduziu referência ausente,
depois 11 testes de segunda curadoria/handoff verdes.

Na revisão de integração, `micro_perception.py`/`final_camera.py` do Curator
passam a preservar decisões longas válidas quando excedem o orçamento de
percepção densa (240 s por padrão). Há probe real dos bounds, oito seeks
limitados para GC e source-preserve explícito; nenhum trim silencioso nem
reanálise global. Regressão com vídeo OpenCV real falhou antes e passou depois,
incluindo rejeição de bounds fora da duração real da fonte.

Parciais medidos da retomada: etapa 05 ok em 142.25 s, 23 agrupamentos acústicos;
etapa 07 partial em 2754.265 s (versus 2670.282 s V4.3, +3.15%). Re-ID conservou
6085/1818/4267 raw/valid/micro. Etapa 10 partial em 7.734 s: speaker/person
15.0490%, active legado 9.6733%, provável sem overlap 8.0853%, confirmado zero.
Resultados coincidem com o replay e promovem o P0-A para VERIFIED_FULL_RUN quanto a cobertura observada. Benchmark geral permanece IN_PROGRESS: a extração semântica havia alcançado 13/46 chunks quando a sessão do agente terminou; câmera final, pacote e compare final ainda precisam concluir. Acurácia de identidade permanece sem ground truth anotado.
