# Implementacao V4.2

Data: 2026-10-05. Producer: 4.2.0. Arquitetura mantida; nenhuma segunda curadoria
final, musica, branding, publicacao ou render social foi implementado.

## Ambiente E Baseline

Alvo: Windows 10/11 + Python 3.11.x. Busca explicita em PATH, registro, instalacoes
locais e .venv encontrou somente Python 3.13.3 executavel. Veja
V4_2_WINDOWS_HOMOLOGATION.md. Nao houve instalacao global nem adaptacao exclusiva
de arquitetura/requisitos para 3.13.

Baseline original nao hermetico: tentativa com erro de coleta (soundfile ausente),
depois 127 passed / 3 failed / 0 skipped, 34.274 s. Duas falhas eram FFmpeg ausente;
a outra era teste do exportador removido. O teste migrado revelou duplicatas reais
no exportador canonico. Depois da correcao, o teste de unicidade passou.

A heranca de site-packages global foi removida. Validacoes posteriores usam .venv
auxiliar 3.13.3 isolada, OpenCV contrib 4.11, NumPy 2.2.6, fixtures e ferramentas
FFmpeg/ffprobe fora do pacote final. O alvo 3.11 nao foi declarado homologado.

## Passes Executados

1. P0: instalacao recomendada com diarizacao/visao; preflight compartilhado com
   imports reais, tokens apenas em memoria, assets/carregamento, acesso HF,
   CUDA/DLLs, Ollama/modelo, schemas e escrita. Falha antes de resolver/download
   da midia. GUI tem seletores e estado; doctor reprova recursos habilitados.
   ASR valida tempos, containment e IDs; preserva raw/anomalias/alternativas.
   Exclusive diarization alinha sem apagar overlap. Re-ID consolida tracklets
   qualificados com evidencia facial e veto de simultaneidade; participantes
   editoriais deixam de ser o conjunto de raw IDs.
2. Semantico/editorial: enums de contexto, locale PT-BR, grounding em IDs e
   rejeicao de timestamps novos/JSON nao finito. Uma tentativa de reparo.
   Perguntas separadas de pares respondidos; relevancia lexical e speaker real
   exigidos. Entidades filtram falsos positivos. Topicos relacionados formam
   sections; payoff desconhecido continua null. Boundaries de frase/contexto/arco,
   dedup com alternativos, classificacao comercial e score/penalidades expostos.
3. Camera/contratos/performance: A40-B1-A considera retorno observado no mesmo
   shot. Timeline temporal, foco resolvido, preservacao e switches sao separados.
   Preview verifica frames reais, distingue padding e nao aceita reparo sem
   re-render/recheck. Pacote V3 resolve referencias canonicas. JSON e serializado
   atomicamente; analysis.json usa referencias. Compact artifacts/chunks retêm
   IDs/timestamps e escopo original. Exportador tem estados e checksums, self-test,
   inspecao total e limite de tamanho preservado. Cache causal, chunks ASR/semantico
   com checksum, visao com code/model fingerprint e cadeia/estado de sampling.
   Compare_runs tolera legado. Fases visuais/semanticas e tamanho de artifacts sao
   observaveis; sampling estavel nao fica perpetuamente em burst.
4. Auditoria independente adicional: veja DISC-001 a DISC-012 em
   WORKER_DISCOVERY_AUDIT.md. Foram exercitados subprocessos/timeout, locks,
   HTTP real, downloader/cache, modelo hash, HTML, corrupcao/resume, exporter e
   workflow completo. Regressões intermediarias foram corrigidas antes do fechamento.

## Validacao Executada

- Suite completa auxiliar: 228 passed / 0 failed / 0 skipped em 46.08 s
  (JUnit: 46.051 s). O fechamento documental repete o gate; resultado definitivo
  em WORKER_FINAL_REPORT.md.
- py_compile: 65 arquivos Python first-party, sem erros.
- Sintaxe ast.parse feature_version=(3,11): passou; nao e runtime Python 3.11.
- BATs: CRLF real verificado, sem LF isolado ou CR duplicado.
- Schemas: meta-validacao de todos, exemplos minimos V2/V3/V4.2 e fixtures
  completas de camera/preview/relatorio; referencias canônicas verificadas.
- FFmpeg/ffprobe: workflow real em video/audio SINTETICOS, caches e Director-only
  sem fonte. Preview renderizado/decodificado. Detector de visao e fluxo em testes
  explicitamente fixture/mocked, nao pesos reais.
- Exporter self-test: PASS; projeto READY, analise vazia EMPTY, CRC/checksums,
  nomes unicos inclusive Windows, exclusao .venv e secret scan integral.
- Doctor real: exit 2; ASR/diarizacao/visao/semantico/scenes ERROR, camera_preview
  e export READY; OCR/audio_events DISABLED. runtime_target_match=false.
- pip-audit isolado apos atualizar apenas pip da .venv: nenhum advisory conhecido
  encontrado. Isso NAO certifica extras/modelos que nao foram instalados.
- Auditoria offline de evidencia real: 176 -> 163 candidatos, 13 alternativos,
  6 comerciais; sem inferencia nova no video e sem acuracia anotada.

## Configuracoes Novas

| Campo | Default | Efeito |
|---|---:|---|
| preflight.allow_self_repair | false | Instalacao opcional apenas na .venv do projeto, nunca global |
| preflight.network_timeout_seconds | 5 | Timeout de sondagens leves |
| preflight.repair_timeout_seconds | 600 | Limite de pip self-repair |
| export.legacy_full_analysis | false | Referencias/checksum por padrao; true ativa monolitico legado |
| export.chunk_records | 500 | Maximo de registros por chunk compacto |
| export.chunk_max_bytes | 2097152 | Budget de bytes de payload por chunk |
| vision.tracklet_min_visual_seconds | 1.0 | Evidencia temporal minima para candidato de identidade |
| vision.tracklet_min_observations | 3 | Observacoes distintas minimas |
| vision.identity_min_visual_seconds | 3.0 | Identidade significativa; tambem retarda retratos |
| vision.reid_candidate_limit | 64 | Busca facial deterministica limitada por banded signs |
| understanding.participant_min_visual_seconds | 8.0 | Tempo visual amostrado minimo |
| understanding.participant_min_observations | 12 | Minimo de observacoes para participante visual |
| understanding.participant_min_speech_seconds | 3.0 | Fala acustica/mapeada para participante confirmado |
| understanding.participant_min_distinct_shots | 2 | Recorrencia visual; presenca longa pode substituir |
| understanding.candidate_min_seconds | 8.0 | Duracao util minima, sem fabricar limites |
| understanding.candidate_preferred_min_seconds | 30.0 | Inicio da faixa desejada |
| understanding.candidate_preferred_max_seconds | 90.0 | Fim da faixa desejada |
| understanding.candidate_soft_max_seconds | 120.0 | Aviso de duracao |
| understanding.candidate_hard_max_seconds | 180.0 | Requer revisao, nao corta significado automaticamente |
| understanding.allow_commercial_candidates | false | Comerciais ficam fora da shortlist padrao |
| understanding.commercial_penalty | 0.5 | Penalidade explicita de utilidade |
| understanding.ranking_weights | mapa abaixo | Pesos apenas de componentes disponiveis |
| semantic_analysis.max_calls_per_hour | 80 | Budget proporcional, minimo 4 chamadas para fonte curta |
| semantic_analysis.fallback_warning_fraction | 0.1 | Limite para aviso/degradacao |

Pesos atuais: hook=.15, standalone_clarity=.15, clean_opening=.10,
clean_ending=.10, story_completeness=.10, qa_completeness=.10,
information_density=.10, visual_viability=.05, audio_quality=.05,
duration_suitability=.10. Componentes nao medidos sao null, nao zero; utilidade
nao e probabilidade de viralizacao. Penalties de contexto required=.10 e unresolved=.05.
Dedup nao apaga evidencia nem transcript de alternativos.

## Limitacoes E Decisoes Conservadoras

- Homologacao runtime 3.11 real, Windows limpo, GPU/VRAM, HF/Community-1, MediaPipe,
  YuNet/SFace, Ollama, OCR/YOLO/PANNs opcionais e GUI manual permanecem pendentes.
- Sem token/pesos/inferencia nao ha claim de acuracia ASR/DER/Re-ID/ASD.
- Busca Re-ID limitada pode perder merges; prefere under-merge a unir pessoas
  simultaneas. Sem embedding nao une por posicao. Biometria visual fica na analise
  local, nunca e identidade civil.
- Scores/contexto/idioma/comercial/entidades/arcos sao conservadores. Arco de
  discussao com payoff nao observado nao e rotulado narrativa completa.
- Alternativas ASR nao substituem canonico sem verificacao independente de audio;
  probabilidades do modelo nao comprovam fidelidade.
- Todas as observacoes ainda ficam em memoria durante o processamento; escrita
  compacta/streaming reduz duplicacao, mas soak de horas e pico RSS/VRAM nao medidos.
- Long-static-shot, ID switch, olhos/expressoes, subtitle-safe-area e precisao de
  clipping neural nao sao medidos onde nao existe evidencia/modelo dedicado.
- ASD neural continua interface opcional sem adapter/pesos/default novo, pois nao
  houve benchmark Windows/3.11 nem revisao de licenca/ganho medido nesta maquina.
- Standards corporativos privados retornaram 404/conteudo nao acessivel; foram
  aplicadas as regras carregadas, sem alegar auditoria formal desses documentos.

## Artefatos E Compatibilidade

Producer 4.2.0; analysis reference schema 4.2; second-curation 3.0 com leitura de
schema 2.0 preservada; camera plan 4.0, Director 3.0, preview/run manifest 1.0.
Colecoes legadas seguem separadas. consumidores monoliticos precisam usar o modo
legado ou load_analysis_artifacts. Preview e tecnico; nao comprova o video inteiro.
CHATGPT_ANALYSIS_HANDOFF.json tambem usa references por padrao, preservando campos
de camera ja consumidos. legacy_full_analysis=true restaura o handoff completo 2.0.
O ZIP final deve excluir ambientes, midia, pesos, cache, previews, proxies, logs
internos e ZIPs originais. Resultados finais da inspecao constam em WORKER_FINAL_REPORT.md.