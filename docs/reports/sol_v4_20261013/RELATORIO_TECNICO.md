# L.D.PORTO — SOL V4: relatório técnico

Data: 13/10/2026. Projeto atual, continuação dos fontes SOL V3. **Pacotes A/B/C implementados; regressão final: 1.892 passed, três skipped, zero falhas; 100 casos novos. Preservação integral verificada por hash.** SceneDetect PyAV foi até 3,89× mais rápido no trecho; checkpoint 10 ficou 47,8% menor. Identidade/ASD globais e qualidade humana permanecem pendentes nos escopos explicitados abaixo.

## 1. Inventário e estado inicial do Git

A análise longa terminou antes de qualquer implementação, teste ou benchmark desta rodada: log final às 11:07:45 locais, processo original encerrado e lock ausente. Não houve cancelamento da GUI, reinício/unload do Ollama ou segunda análise completa. O resultado original ficou `partial`.

Branch `baseline/ldporto-20261012-prompt01`, HEAD `2f4634f202f976c135c4bd28db590e289ce72156`. O working tree já continha as implementações V3 e outras mudanças, incluindo exclusões de infraestrutura aposentada. Essas exclusões não são trabalho V4. [git_before.txt](git_before.txt) registra o estado completo; [initial_state.json](initial_state.json) registra hashes de 472 fontes, 27 checkpoints e três exports protegidos. Nenhum commit, reset ou recriação do orquestrador.

Backup dos fontes sujos existentes, verificado antes das alterações: `C:\Users\leone\Documentos\Meus Projetos\LDPORTO_SOLV4_BACKUP_20261013\working_sources_before_sol_v4.zip`, SHA-256 `13ec1c21e25af8818ca2cb82db9063e981382e52ea072221b5410958d38a42b1`. Não foi extraído sobre o projeto. Diffs usaram essa cópia apenas como referência de fontes; ZIPs históricos de análise foram tratados como dados.

Fonte preservada: `input/youtube/7laRa_F3FbA/7laRa_F3FbA.mp4`, 480.580.282 bytes, SHA-256 `0231c20cfd8147d92926bda4f452777f3803c38b248064e65548f0b12a5fb98b`. Duração 3.982,834 s, AV1, 1920×1080, 29,97002997 FPS. Análise `analysis/video_1da839aad175`: 1.041 arquivos, 6.367.923.312 bytes. Manifesto de preservação: [preservation_before.json](preservation_before.json).

Pacote real da análise: `SECOND_CURATION_PARTIAL_7laRa_F3FbA_20261013_140239_076346_6beb9d.zip`, 3.428.934 bytes, SHA-256 `0c6cd22d4892fddbb23ab71e6c12997c2a47709ebd919c12b8ebeaaeaec2f4ff`. Pacotes pequenos gerados por fixtures da regressão não são evidência audiovisual desta fonte.

Conferência final às 12:41:09 locais: **`VERIFIED`**, sem divergências ou novos arquivos na análise original. Todos os 1.041 arquivos (incluindo 27 checkpoints), ZIP real, mídia original, peso YOLO existente, três `.package/PROJECT_EXPORT_*`, HEAD e 478 fontes congelados conferem. Evidências: [final_integrity.json](final_integrity.json), [git_after.txt](git_after.txt), [sources_frozen_final.json](sources_frozen_final.json). As mudanças documentais V4 posteriores a esse check estão somente nesta pasta de relatório.

Não houve instalação/download V4. Foram reutilizados Python 3.11.9, Torch/Torchaudio 2.8.0+cu128, torchvision 0.23.0+cu128, Ultralytics 8.3.200 e YOLO11n local. Peso de 5.613.764 bytes, SHA-256 `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`. Credenciais, modelos, mídia original, `.venv`, `.git` e `.package/PROJECT_EXPORT_*` não foram editados.

## 2. Gargalos auditados

As métricas da análise original são evidência do build anterior e diagnóstico de entrada, não prova de execução V4. [readonly_metrics.json](readonly_metrics.json) preserva os dados finais coletados.

| Etapa original | Tempo registrado | Observação |
|---|---:|---|
| 04 transcrição | 502,421 s | 13.082 palavras; revisão limitada por orçamento |
| 05 diarização | 66,469 s | três speakers acústicos |
| 06 cenas | 1.495,187 s | 618 cenas / 617 limites |
| 07 percepção | 3.312,203 s | 119.365 frames decodificados / 25.116 amostrados |
| 08 Re-ID | 4,547 s | 1.949 tracklets / 1.291 identidades de evidência |
| 10 Active Speaker | 16,937 s | associação global não confirmada |
| 15 semântica | 3.956,484 s | 23 blocos concluídos; resultado `partial` |

Na etapa 07: decode 1.247,963 s; faces 1.006,717 s; embeddings 341,564 s; landmarks 284,668 s; corpo 171,797 s; checkpoint 78,577 s. `face_body_embedding_detection` (1.525,096 s) contém subfases; não somar agregado e componentes. Foram 13.236 inferências YOLO CUDA bem-sucedidas, HOG zero e fallback zero. Corpo representa aproximadamente 5,2% do wall da etapa; reinstalar YOLO não resolveria o gargalo dominante.

SceneDetect já tinha prefetch de quatro frames; usa ContentDetector, todos os frames, redução própria de largura em torno de 256 para o detector, após decode AV1/RGB. O caminho caro é CPU/decodificação; não há evidência de falta de prefetch. Tracking decodifica novamente para obter seus frames e cronograma adaptativo. OCR reutiliza thumbnails existentes. Compartilhar o pequeno frame de cenas com a face/landmark alteraria a evidência; armazenar todos os RGB 1080p acrescentaria volume e RAM. Não foi introduzido cache monolítico de frames nem alterada a frequência de embeddings/landmarks.

## 3. Causas comprovadas e hipóteses

| Constatação | Estado / implicação |
|---|---|
| Decode e faces dominam etapa visual original | `VERIFIED`: tempos instrumentados; subtotais com sobreposição identificada |
| AV1 por PyAV/libdav1d é mais rápido neste trecho | `VERIFIED` no benchmark limitado; equivalência humana ainda `PENDING` |
| Qualidade facial repetia conversão/medição compatível de ROI | `VERIFIED`: agora reutilizada apenas quando método e limites inteiros coincidem |
| `mappings`/`intervals` duplicam a mesma projeção | `VERIFIED`: 92.974 pares, equivalência lógica integral demonstrada |
| Número 1.291 representa pessoas humanas reais | `NOT_MEASURED`: são hipóteses persistentes do engine |
| Fragmentação impede o consenso neste vídeo | `PARTIAL`: possível no longo prazo, mas todos os 777 candidatos locais têm estabilidade 1,0; nenhum sofreu o gate ≤0,5 |
| Teto antigo de 2.500 templates explica a fragmentação atual | Refutado para este resultado: galeria atual de 1.291 identidades |
| Qwen é lento por carregar o modelo a cada bloco | Refutado pelos custos finais: 5,893 s de load frente a 3.653,566 s de geração |

A abstenção legada de 1.803 tracklets contém 1.291 sementes válidas mais 512 micro-tracklets sem mapeamento. Não são 1.803 identidades fracassadas. Dos 1.459 rejeitados com melhor candidato facial, os gates se sobrepõem: margem 1.410, score 310, consistência de cluster 118 e veto temporal 12. Há 123 reentradas faciais online; 70 consolidaram e 53 viraram sementes. Mesmo raw ID não elimina a ambiguidade entre os melhores concorrentes offline.

## 4. Arquivos alterados nesta rodada

Diff relativo ao snapshot inicial, independente do dirty tree V3: [v4_source_changes.json](v4_source_changes.json). **15 arquivos existentes e seis novos**, além dos relatórios/evidências desta pasta.

| Pacote | Arquivos de implementação |
|---|---|
| A | `vision.py`, `scenes.py`, `face_quality.py`, `pipeline.py`, `run_status.py`, `config.py`; `core.py` registra versão `av` |
| B | `person_reid.py`, novo `speaker_windows.py`; parte ASD de `vision.py`, `_active_stage`/fingerprints, configuração opcional |
| C | novo `checkpoint_storage.py`, `core.py`, `execution_receipts.py`, `compact_artifacts.py`, `reports.py`, `semantic.py`, `scripts/dev/audit_camera_s6.py`, `audit_speaker_s5.py`; ajuste de exportação em `scripts/export/exportar_ldporto.py` |
| Testes e benchmark B | `test_sol_v4_visual.py`, `test_sol_v4_identity.py`, `test_sol_v4_checkpoint_storage.py`, `scripts/dev/benchmark_speaker_windows_sol_v4.py` |

Os módulos compartilhados aparecem em mais de um pacote, sem duplicar a contagem. YAML ativo, app e fontes V3 fora dessa lista preservam seus hashes iniciais.

## 5. Correções implementadas

**A — percepção:** tempos separados de grab/retrieve, preparo, qualidade de frame/face, embeddings, corpo, landmarks, associação e persistência; métricas `decode_ms`, `face_ms`, `landmark_ms`, `embedding_ms`, `body_ms`, `tracking_ms`, `serialization_ms` são totais do trecho, com denominadores explícitos. Medições inexistentes ficam `null`. A conversão YOLO usa um `Boxes.cpu()` seguido de NumPy, preservando filtro/classe/ordem e adaptador de fallback. Gray compartilhado e sharpness de ROI são reutilizados sob equivalência estrita. Thresholds, FPS, resolução, sampling e política de VRAM permanecem.

SceneManager explícito mantém ContentDetector/min_scene_len/downscale/frame_skip=0/prefetch=4. Tempos do worker de decode e consumidor de detecção são concorrentes, não aditivos. Backend opcional `scenes.backend=pyav`, com modo de threading validado, registra PTS/FPS/contagem/EOF, tentativas de fallback e fechamento de stream/container. **OpenCV permanece padrão.** Fonte/config/versões/algoritmo/fingerprints seguem nos contratos de cache; `av`, `face_quality.py`, `vision_checkpoint.py` e helpers entram nos invalidadores pertinentes.

**B — identidade/ASD:** busca exata acima de 2.500 templates em blocos de 256, com concorrente global, desempate estável e veto temporal; o caminho numérico anterior é preservado para a galeria atual. Diagnóstico distingue sementes, merges e não mapeados, detalha gates e prepara até 24 pares online/offline para revisão, sem auto-merge. Embeddings/raw IDs nunca autorizam associação por localização ou quantidade esperada de participantes.

Janelas de ASD têm helper puro e três políticas opcionais: `legacy` padrão; `balanced_tail` equilibra apenas cauda menor que o mínimo; `tail_anchor` mantém todas as janelas/IDs legacy e acrescenta uma âncora limitada ao fim da fatia já delimitada por voz/shot/overlap. Sobreposição de medição é separada de sobreposição acústica. Os guards de independência temporal de afinidade e lag impedem duplicação de voto. Agregados de planejamento/perda e amostras/gaps dos candidatos persistem; valores bucais nulos não viram falha presumida de landmarks.

**C — armazenamento:** codec físico `asd_mapping_projection_v1` 1.0 somente para novas escritas da etapa 10 quando cada intervalo é projeção JSON exata do mapping, incluindo tipos e sinal de zero. Divergência preserva documento completo. Leitura central e snapshots hidratam listas e containers independentes; S5/S6 leem diretórios e ZIPs. Marcadores/referências/counts inválidos falham explicitamente. Hash lógico/recibo cobre dados hidratados; SHA físico cobre bytes armazenados. Cache hit antigo não é reescrito.

Buffer de escrita conserva bytes UTF-8, temporário exclusivo, atomic replace, flush/fsync e cleanup de temporário. `verify_receipt` calcula digest do payload uma vez por chamada e mantém comparações e ambas as barreiras de artefatos. Snapshot de entrada do relatório é escrito sincronicamente antes de mutações finais, isolado e verificado em disco, sem deepcopy redundante. Tempos finais ficam no diagnóstico externo `artifact_metrics.json`, fora do recibo fechado.

Seis sidecars existentes substituem cópias no documento compacto: evidência ASD, diagnóstico/afinidade speaker-person, perfil semântico, revisão editorial Ollama e gráficos de broadcast. Referências aditivas 1.1; ausência de sidecar conserva conteúdo inline. Revisão independente identificou que S6 precisava solicitar `broadcast_graphics` explicitamente; a correção preserva a região protegida no replay e o canário recusa sidecar adulterado.

Caches semânticos 4.3 guardam metadados originais opcionais com checksum e escopo de duração. Cache hit mostra história separada do custo de chamadas atuais; dados adulterados não são exibidos. Prompt, modelo Qwen3:14b, perfil `max`, budgets e compacto desativado permanecem. Mudança de `core.py` invalida fingerprints dos estágios pertinentes via mecanismo existente; não houve recomposição da análise longa ou invalidation silenciosa de arquivos históricos.

Na regressão completa, o exportador selecionou as duas cópias de checkpoint de benchmark em `docs/reports`, gerando `file_too_large`/`PARTIAL_EXPORT` (331 MB e 173 MB). A seleção do pacote de fontes agora exclui somente snapshots com nome de etapa `NN[letra]_nome.json` sob `docs/reports/**`. Os dados continuam no disco; relatórios, `result.json`, manifestos e fixtures fora de reports permanecem exportados. README/manifesto explicitam a política, e o inspetor independente recusa snapshots indevidos. Limites de tamanho e gates permanecem. O pacote de análise conserva seu coletor próprio.

## 6. Testes adicionados

Pacote A: 22 casos novos, incluindo equivalência de ROI, conversões YOLO, contadores, backend/default, fallback/fechamento, timestamps e invalidadores. Foco final: **152 passed**, 6,58 s, [a_targeted_tests.json](a_targeted_tests.json).

Pacote B: 41 casos novos. Exercitam caudas, fronteiras, overlap, amostras ausentes/inválidas, positivos/negativos de sinais, silêncio/offscreen, reentrada, galeria grande/concorrente, estabilidade e independência das âncoras. Foco final: **101 passed**, 2,62 s, [identity_b_focus_03.json](identity_b_focus_03.json).

Pacote C: 35 casos novos no foco inicial de **131 passed**, 28,39 s, [storage_focused_run.json](storage_focused_run.json). Equivalência lógica/mutação, fallback sem perdas, markers inválidos, corrupção física, novo produtor/cache hit sem rewrite, ambas as barreiras de recibo, bytes UTF-8, S5/S6 diretório/ZIP, referências e tampering, snapshot/gates e custos históricos separados. Após revisão independente, um canário S6 adicional: **36 passed no arquivo C**, 1,44 s, [storage_s6_independent_review_fix.json](storage_s6_independent_review_fix.json). O ajuste do exportador adicionou outro canário de pacote real de fontes com preservação de dados locais/resumos/fixtures: **39 passed** no foco (37 C + dois testes antigos que falharam), 6,36 s de wrapper, [storage_export_regression_fix.json](storage_export_regression_fix.json). Total confirmado: **100 casos novos** (22 A + 41 B + 37 C), todos aprovados na suíte final.

As duas primeiras falhas em fixtures novas A/B foram expectativas incorretas de canários (rescue/primeiro frame), corrigidas sem relaxar gates de produção; logs iniciais permanecem. Focos compartilham regressões existentes, portanto não somar seus totais como testes únicos. Sinais/identidades sintéticos são explicitamente fixtures, sem alegar precisão humana.

## 7. Testes existentes preservados

Baseline atual antes de editar: **1.791 passed, quatro skipped, zero falhas**, 1.795 casos, 306,794 s, [before_full.json](before_full.json), [log](before_full.log), [JUnit](before_full.xml). O histórico V3 de 1.792/3 é referência anterior; não substitui essa execução.

Skip adicional da baseline: teste Tk `test_native_execution_screen_receives_structured_stage_events_and_final_package`, display indisponível naquela execução; **passou na execução final**. Outros três skips permanecem: dois de privilégio de symlink Windows e um Tesseract opt-in. [test_case_comparison.json](test_case_comparison.json) confirma todos os 1.795 casos antigos preservados, 100 adicionados, nenhum ausente. O aumento de 101 aprovados frente à baseline corresponde aos 100 novos mais o Tk antes skipped.

## 8. Regressão final

**`VERIFIED`: 1.892 passed, três skipped, zero failures/errors, exit code 0; 1.895 casos.** Pytest 250,39 s, wrapper 251,035 s. Evidências finais: [after_full.json](after_full.json), [log](after_full.log), [JUnit](after_full.xml) e [comparação de casos](test_case_comparison.json). Os 478 fontes congelados, HEAD e evidências anteriores permanecem íntegros.

Uma execução foi interrompida pelo próprio agente após o achado de consumidor S6; não conta como aprovação. A seguinte completou 1.894 casos com 1.889 passed, três skipped, duas falhas de exportação, 249,52 s de wrapper. Diagnóstico comprovado no manifesto: apenas as duas cópias de benchmark acima do limite, nenhum essencial ausente. A correção passou pelos 39 testes focados e pela regressão integral final acima. Resultados anteriores preservados em `after_full_interrupted_s6.log` e `after_full_failed_export.{json,log,xml}`. O comando completo final é registrado pelo runner:

```powershell
& .venv/Scripts/python.exe -B docs/reports/sol_v4_20261013/run_regression.py after_full
```

O subprocesso executa `.venv\Scripts\python.exe -m pytest -q --junitxml=...`, capturando stdout, exit code, duração e nomes dos casos. Nenhuma nova análise completa é necessária para essa regressão.

## 9. Benchmarks antes/depois

Trecho novo derivado por streamcopy, 0–120 s: [excerpt_manifest.json](excerpt_manifest.json), hash `21ed73ee50197a4289c1c527e2e9024859605f880d3daad5e1f205bbae5ecdda`. Mesmo AV1, 1920×1080 e FPS nativo; duração efetiva 120,0199 s. Thumbnails originais em 10,043 s e 85,152 s foram inspecionadas: duas pessoas simultâneas e enquadramento diferente, sem atribuir nomes/falante pela imagem. Replay ASD também usa fatia 164,512–168,562 s apenas de áudio/observações já salvos.

### A — benchmark OpenCV/visão, mesma configuração

Config SHA-256 `6a8454e8c054b6141b34e2fa8de1054363d4ace7a7462dc1c778338d2f54dbdb` antes/depois. Ambos 3.597 frames decodificados, 691 amostrados, 1.231 observações, 11 hipóteses/11 thumbnails, 304 embeddings, 359 YOLO CUDA bem-sucedidos e HOG zero. Evidência: [perception_comparison.json](perception_comparison.json), resultados `before_visual/` e `after_visual/`.

| Tempo total da subtarefa | Antes | Depois |
|---|---:|---:|
| SceneDetect OpenCV | 49,767 s | 48,717 s |
| Vision wall | 98,481 s | 85,151 s |
| Decode (grab+retrieve) | 39,784 s | 34,717 s |
| Faces | 26,411 s | 23,336 s |
| Embeddings | 9,195 s | 8,033 s |
| Landmarks | 7,917 s | 6,753 s |
| Corpo | 5,938 s | 4,993 s |
| Associação | 0,479 s | 0,407 s |
| Checkpoint intermediário | 0,730 s | 0,909 s |
| Escrita final do JSON visual | 0,361 s | 0,373 s |

Wall visual observado caiu **13,5% (1,1565×)**; FPS amostrado efetivo 7,02→8,12. É um par de processos novos, sem repetição estatística/controle de cache do SO. A variação no decode e nos detectores contribui; não atribuir toda diferença às duas otimizações. Checkpoint intermediário ficou mais lento. JSON visual cresceu 6.117.098→6.296.136 bytes por diagnósticos (+2,9%), não constitui redução de volume etapa 07.

### A — experimento SceneDetect/PyAV, mesmos frames/algoritmo

| Processo somente cenas | Tempo | Frames | Pico RAM |
|---|---:|---:|---:|
| OpenCV atual | 47,944 s | 3.597 | 327.946.240 bytes |
| PyAV SLICE/libdav1d | 12,469 s | 3.597 | 199.180.288 bytes |
| PyAV AUTO/libdav1d | 12,320 s | 3.597 | 199.163.904 bytes |

Ganhos observados **3,845× / 3,892×**; seis cuts relativos preservados com tolerância explícita de um frame, `1/FPS=0,0333666667 s`, mais 0,5 µs de quantização decimal. Primeiro corte deslocou um frame; restantes idênticos salvo arredondamento. Nenhum corte novo/perdido relativo à referência nessa tolerância. [scene_decoder_comparison.json](scene_decoder_comparison.json) não é ground truth de cortes humanos.

EOF real: os três backends decodificaram os últimos 120 frames do original, PTS monotônicos e último PTS igual, delta zero. Pixels finais PyAV/OpenCV diferem: máximo 29/255, média absoluta 0,03910, RMS 0,84538, 0,415% dos canais alterados. Causa não estabelecida; [decoder_eof_quantified.json](decoder_eof_quantified.json). PyAV continua opt-in até inspeção de limites e qualidade em mais codecs/trechos.

## 10. RAM/VRAM e uso efetivo

Vision em processo novo: pico RAM 1.958.043.648→1.944.231.936 bytes, queda pequena (~0,7%) que não demonstra redução geral. Scene-only PyAV caiu aproximadamente 39,3% frente a scene-only OpenCV; estes são processos comparáveis sem modelo visual. Decodificação/cenas, YuNet/SFace e MediaPipe usam CPU nesse benchmark; YOLO executou `cuda:0` na RTX 5070. GPU permanece sequencial, um frame em voo.

Transformação do checkpoint C: pico 1.501.851.648→1.501.179.904 bytes, praticamente igual. Releitura isolada do formato codificado: 1.363.910.656 bytes, escopo diferente. Não alegar redução do pico do pipeline inteiro. Na análise longa, amostra RSS ≥12.538.220.544 bytes ao iniciar export não é medição de pico integral.

YOLO no benchmark isolado registrou pico Torch de 69,598 MiB tanto antes quanto depois; não é pico sistêmico completo de VRAM. Os 1.652,7 MiB do processo original incluem alocações de etapas anteriores e não são exclusivamente YOLO. Snapshots de VRAM livre incluem outros consumidores. Redução no pico Torch YOLO desta amostra: zero; ganho de VRAM do pipeline completo: `NOT_MEASURED`.

## 11. Fragmentação e identidade

Replay CPU integral do Re-ID sobre checkpoint 07 original, sem decode/modelos: [reid_preservation.json](reid_preservation.json). Config do Re-ID confere com etapa 08 original (`e708c4ac41fe4c2a106b6d302e615576c579c928e9bc62db73137f3da3628902`). Todos os campos legados de identidade, mapping, decisões, métricas e pares de revisão conservaram hash.

| Métrica real | Antes | Depois |
|---|---:|---:|
| Tracklets | 1.949 | 1.949 |
| Micro-tracklets | 523 | 523 |
| Sementes / identidades persistentes | 1.291 | 1.291 |
| Merges aceitos | 146 (135 estáveis / 11 micro) | iguais |
| Micro sem mapping | 512 | 512 |
| Proxy de fragmentação | 0,2221652129 | igual |

**Não houve melhoria comprovada da fragmentação real nesta rodada.** A busca grande elimina uma limitação futura; os diagnósticos tornam as causas auditáveis. Forçar raw IDs/merges atuais burlaria os concorrentes e gates. Replay atual levou 2,554 s; não comparar com 4,547 s do Context original, que tem outro escopo.

Precisão/recall, merges corretos/incorretos e ID switches humanos: `NOT_MEASURED`. Continuidade em vídeo anotado com duas pessoas/alternância: `PENDING`, depende de anotações verificáveis. Os testes positivos/negativos sintéticos preservam pessoas simultâneas e reentradas, sem substituir essa homologação.

## 12. Active Speaker e sincronização

Funil real original: três speakers acústicos → 3.994 janelas → 777 candidatos → 35 sinais locais qualificados → dez janelas de afinidade independente → seis suportes → **zero associação global confirmada**, cobertura 0%, sincronização global `not_measured`. Contagens de perda por janela: 1.496 curtas, 1.416 overlap, 305 amostras bucais insuficientes, 742 abaixo dos gates, 35 qualificadas. Essas categorias usam o denominador de janelas, não número de pessoas.

Foram identificadas 204 fatias balanceáveis, 202 não sobrepostas; o ganho geométrico potencial de 452→654 janelas elegíveis não prova amostras suficientes por pessoa/correlação. Por isso não foi promovido por configuração.

Replay CPU com áudio mono 16 kHz real e 115 observações projetadas verificadas, três fatias de 86,262–89,840 s, 105,472–112,823 s e 164,512–168,562 s. Recalcula correlação, bounds e lag; nenhuma chamada GPU/Ollama/ASR/detector. [speaker_windows_b_cpu_anchor.json](speaker_windows_b_cpu_anchor.json).

| Política | Janelas | Áudios medidos | Candidatos | Qualificados locais |
|---|---:|---:|---:|---:|
| Legacy padrão | 7 | 4 | 4 | 1 |
| Balanced tail experimental | 7 | 7 | 7 | 0 |
| Tail anchor experimental | 10 | 7 | 7 | 1 |

Balanced tail mediu mais e perdeu a qualificação nesse recorte; continua desativada. Âncora conserva o positivo legacy e mede a cauda, mas **não aumentou qualificados** nesta amostra. Guards de independência impedem duplicar votos. Lag local recalculado é proxy de sinal; não confirma identidade nem sincronização global. Precisão/recall e falsas associações reais: `NOT_MEASURED`. `UNRESOLVED` permanece quando os critérios não se sustentam; não foi usado rosto central/único como falante presumido.

## 13. Redução comprovada de checkpoint

Arquivo original etapa 10 foi lido e preservado. Antes, cópia local integral reproduziu exatamente seus bytes/SHA físico. Depois, apenas a cópia de benchmark nesta pasta foi codificada. [storage_comparison.json](storage_comparison.json), `storage_before/result.json`, `storage_after/result.json` e `storage_encoded_read/result.json` contêm medições reais em processos distintos.

| Medição | Antes | Depois |
|---|---:|---:|
| Bytes físicos | 331.319.797 | 172.939.789 |
| Redução de disco | — | **47,8028%** |
| Packing + escrita | 21,036 s (packing zero) | 3,962 + 10,618 = **14,580 s** |
| Redução packing+write | — | **30,6908%** |
| Verificação do recibo | 27,247 s | 8,612 s sobre original hidratado; 9,940 s em releitura codificada |
| Leitura | 8,388 s | 7,569 s codificado + hidratação |
| Mappings / intervalos lógicos | 92.974 / 92.974 | 92.974 / 92.974 |
| Estado do recibo | `verified_partial` | `verified_partial` |

SHA lógico do **registro completo** igual nas três execuções: `cec3c62a675a94a2fa6501eb946f4dcaf32a5dda47ea7005200e345577ee7ba3`. SHA físico legacy `33b372104fcc0aabad064b04929502263c9d68441cbb5385ad3787d587a962c1`; codificado `ecc5f00a133b4bcf7fb0defd8f007f32ce4836924a7af824c9559c9aaf9b7d0a`. Essa mudança física esperada não altera checksum lógico/receipt.

Um par de processos, cache de filesystem não removido: tempo é observação controlada de escopo, sem distribuição estatística. Não houve compactação do histórico, exclusão de evidências nem alteração da Camera Timeline monolítica. Redução do pacote completo/etapa 12: `NOT_MEASURED`.

## 14. Qualidade, equivalência e custos editoriais

Na visão OpenCV, hashes dos campos legados são idênticos: geometrias, IDs, embeddings, lip/landmarks, gates de qualidade, frames/thumbnails e cenas. Comparação projeta fora somente novos campos diagnósticos e exclui explicitamente tempos/preflight VRAM variável; lista completa em `perception_comparison.json`. Isso prova preservação numérica neste trecho, sem presumir acerto humano.

Re-ID preserva todas as saídas legadas na análise completa salva. Codec C mantém semântica integral, adaptação dos leitores, isolamento e barreiras de integridade. Gates `PARTIAL`, `READY_FOR_REVIEW`, `PREVIEW_APPROVED`, `PUBLISH_READY` continuam separados; testes técnicos não promovem publicação.

Qwen final original: 23 blocos, 32 chamadas totais (30 locais incluindo sete reparos + duas globais), 398.026 prompt tokens e 32.143 gerados. Geração 3.653,566 s (~92% do tempo servidor), prompt 272,373 s, load 5,893 s. P50/P90/P95 locais 122,688/235,094/253,578 s. Validação final 22/23, inicial 16/23, reparos 6/7 bem-sucedidos, um fallback, zero cache hits. Revisão global 593,766 s, `partial`, com item inválido não recuperado. Foram preservados 117 tópicos e 80 momentos; completude editorial exige inspeção humana.

**Nenhum novo benchmark de inferência Qwen foi executado em V4; ganho de geração/qualidade editorial é `NOT_MEASURED`.** O pacote C melhora observabilidade/cache sem mudar prompts/saídas. Compacto segue desativado conforme resultado anterior 2,96% mais lento. Não foi reduzido `max` nem aumentado budget.

ASR original: 710 flags/13.082 palavras (5,4273%, **não WER**), 666 flags de baixa confiança, 150 anomalias, 144 desalinhadas, 100 regiões revisadas/limitadas, 16 multipass/86,36 s, 245 adiadas. Inferência, idioma/alternativas/proveniência, priorização V3 e budgets preservados; WER/revisão humana `NOT_MEASURED`.

Camera Director original permaneceu parcial, 2.433 intervalos, 1,55 switches/min, 2.395 switches suprimidos e aproximadamente 3,5% de cobertura. Canários de preview de 99,6 s não homologam render de 66 minutos. Qualidade final de câmera/Smart Zoom: `PENDING`. Audio events `skipped`, `events=[]`, `music_under_speech=null` significa recurso opcional sem medição, não ausência factual de risada/música/aplauso.

Auditoria read-only dos consumidores de eventos: `audio.py:205` conserva `skipped`/`null`; `preflight.py:327` não carrega PANNs quando desativado; `second_curation.py:296` mantém música desconhecida; `social_output.py:475` conta evidências registradas; `subtitle_review.py:265` mantém revisão humana necessária. Nenhum falso negativo factual encontrado nesses caminhos. Limitação `PARTIAL`: o sidecar exportado `audio/sound_events.json` isolado não tem estado próprio para diferenciar desativado de medição vazia; exige manifesto da etapa 14, além de `origin_verified=null`/escuta pendente. Canários existentes em `test_s8_commercial_graphics_stories.py`, `test_stage24_audio_plan.py`, `test_s7_subtitle_review.py` entram na regressão completa; não houve inferência de eventos nova.

## 15. Limitações restantes e estados

| Entrega | Estado |
|---|---|
| Instrumentação/otimizações A e inferência local YOLO CUDA | `VERIFIED` no trecho medido |
| PyAV mais rápido e equivalência de cuts relativa em um frame | `VERIFIED` limitado; promoção padrão `PENDING` |
| Identidade/ASD: contratos, diagnósticos, canários e replay local | `VERIFIED` em escopos declarados |
| Redução real de fragmentação e ASD global | `PARTIAL`: não melhoraram/confirmaram no dado real |
| Ground truth humano identidade/falante/cortes/WER | `NOT_MEASURED`, homologação `PENDING` |
| Codec/checksum lógico/referências/recibos C | `VERIFIED` |
| Redução física etapa 10 e packing+write | `VERIFIED`, par único |
| Menor RAM/VRAM do pipeline longo inteiro | `NOT_MEASURED` |
| Inferência/qualidade Qwen V4 e segunda curadoria humana | `PENDING` / `NOT_MEASURED` |
| Regressão completa final / 100 novos / 1.795 antigos preservados | `VERIFIED`: 1.892 passed / três skips / zero falhas |
| Preservação da análise, ZIP, mídia, modelo, exports, HEAD e fontes | `VERIFIED`: sem divergências |

Não existe bloqueio técnico de implementação nesta rodada. Não foram inventadas anotações; resposta opcional sobre ground truth não é aprovação presumida. Não se declara o pacote publicável.

## 16. Comandos seguros para homologação posterior

Executar no projeto, com processo de análise anterior encerrado. Testes abaixo são offline; os benchmarks visuais usam apenas o excerpt já derivado e inferência local autorizada, sem pipeline completo. Use diretório de saída novo para não sobrescrever evidências.

```powershell
# Canários offline dos três pacotes
& .venv/Scripts/python.exe -m pytest -q src/tests/test_sol_v4_visual.py src/tests/test_sol_v4_identity.py src/tests/test_sol_v4_checkpoint_storage.py

# Regressão completa (captura JSON/log/JUnit)
& .venv/Scripts/python.exe -B docs/reports/sol_v4_20261013/run_regression.py homologacao_posterior

# Replay limitado de sinal áudio/boca salvo: sem GPU, modelos ou nova transcrição
& .venv/Scripts/python.exe -B scripts/dev/benchmark_speaker_windows_sol_v4.py --analysis analysis/video_1da839aad175 --config config/config.yaml --output docs/reports/sol_v4_20261013/speaker_windows_homologacao_nova.json

# Leitura/integridade da cópia já codificada, sem alterar checkpoint original
& .venv/Scripts/python.exe -B docs/reports/sol_v4_20261013/benchmark_storage.py storage_homologacao_nova --input docs/reports/sol_v4_20261013/storage_after/10_active_speaker.json --read-only
```

Comandos registrados dos benchmarks visuais, decode/EOF e armazenamento: [a_benchmark_commands.json](a_benchmark_commands.json), [storage_benchmark_commands.json](storage_benchmark_commands.json) e manifestações de resultados. Para inspeção humana, comparar cortes em 3,070/3,103 s, 7,007 s, 81,882 s, 101,401 s, 105,339 s e 113,080 s do excerpt, antes de optar por PyAV. Anotar IDs visuais anônimos, turnos, offscreen e overlap nas três fatias ASD; medir precisão/recall somente a partir dessas anotações verificadas. Nenhum comando de instalação, download, publicação, limpeza ou rerun do vídeo completo foi necessário.
