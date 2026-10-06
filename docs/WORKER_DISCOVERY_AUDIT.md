# Auditoria Independente V4.2

Benchmark original e somente leitura. Achados sao
baseados em codigo e verificacoes, nao em supostas melhorias de acuracia.

## DISC-001: Arquivos Derivados Duplicados No Exportador Canonico

- Severidade: high.
- Evidencia: `exportar_ldporto.py` coletava PROJECT_EXPORT_MANIFEST.json,
  PROJECT_EXPORT_TREE.txt e PROJECT_EXPORT_README.txt antigos e os gravava novamente.
  A execucao direta retornou erro de entradas duplicadas nos tres nomes.
- Impacto: o exportador atual nao conseguia produzir o pacote de projeto desta fonte.
- Causa: a lista DERIVED_PACKAGE_NAMES nao acompanhou a migracao para o exportador canonico.
- Cobertura previa: relacionada ao requisito de migracao do teste legado; a falha
  no proprio exportador foi comprovada somente depois de migrar o teste.
- Arquivos: `exportar_ldporto.py`, `src/tests/test_v4_final.py`.
- Solucao: excluir derivados canonicos antigos e usar o exportador atual no teste.
- Testes: `test_work_package_has_single_derived_manifest_files`, 1 passed, Python 3.13.3.
- Status: fixed; tambem verifica colisoes case-insensitive e exclusao de .venv.

## DISC-002: Launcher Encerrava Sessoes Ollama Alheias

- Severidade: high.
- Evidencia/causa: ABRIR_ANALYZER.bat e CORRIGIR_GPU_WINDOWS.bat percorriam `ollama ps` e executavam stop para
  TODOS os modelos, sem identificar proprietario da sessao.
- Impacto: abrir a GUI podia interromper inferencia de outro aplicativo/usuario.
- Cobertura previa: nao pedido explicitamente; descoberto na auditoria de processos.
- Arquivos/solucao: ABRIR_ANALYZER.bat, CORRIGIR_GPU_WINDOWS.bat; removido encerramento indiscriminado.
- Testes: test_native_launcher_does_not_stop_other_ollama_sessions, BAT CRLF.
- Status: fixed. Gestao global de VRAM continua responsabilidade explicita do usuario.

## DISC-003: Cliente Local Podia Usar Proxy Ou Seguir Redirect Externo

- Severidade: high.
- Evidencia/causa: ollama_local._request_json validava somente URL inicial e usava
  urlopen com handlers padrao de proxy/redirect.
- Impacto: o contrato de processamento local nao era garantido na camada HTTP.
- Cobertura previa: P1.26 parcialmente; bypass especifico nao estava enumerado.
- Arquivos/solucao: ollama_local.py; ProxyHandler vazio, redirects bloqueados,
  credenciais/query/path ambiguos rejeitados, payload e JSON estrito limitados.
- Testes: servidor HTTP loopback REAL devolvendo redirect, URL fixtures e client
  sem chamada externa. Testes em test_v42_security.py.
- Status: fixed. Nao e teste de seguranca completo do servidor Ollama externo.

## DISC-004: IDs E Caminhos De Imagem Nao Eram Escapados No HTML

- Severidade: high.
- Evidencia/causa: reports.html_report interpolava person_id em alt/figcaption;
  caminhos portrait podiam referenciar rede ou traversal em analise importada.
- Impacto: conteudo nao confiavel podia virar markup ou requisicao de rede ao abrir
  o relatorio local, principalmente em Director-only de artifacts externos.
- Cobertura previa: P1.26 genericamente, nao a fronteira HTML especifica.
- Arquivos/solucao: reports.py; escape de IDs, referencias relativas somente,
  CSP sem rede/scripts externos e hash do unico script local de busca.
- Testes: test_report_html_escapes_ids_and_rejects_remote_or_traversing_images.
- Status: fixed em contratos/testes; revisao manual de acessibilidade GUI pendente.

## DISC-005: Optical Flow Usava Fator De Tempo Invertido

- Severidade: medium.
- Evidencia/causa: preview_verifier multiplicava deslocamento por fps*stride,
  embora a diferenca medida estivesse entre frames espacados por stride/fps.
- Impacto: velocidades/avisos de movimento inflados por stride ao quadrado.
- Cobertura previa: P1.15 genericamente; erro dimensional nao estava identificado.
- Arquivos/solucao: preview_verifier.py; fps/stride. Padding full-frame intencional
  nao e UNEXPECTED_BORDER; capture liberado mesmo em erro; zero frames nao aprova.
- Testes: decoder OpenCV REAL com optical flow MOCK de 1px, resultado 10px/s em
  vez de 40px/s; preview FFmpeg sintetico real.
- Status: fixed; fluxo da camera fonte nao e movimento editorial isolado calibrado.

## DISC-006: Re-render De Reparo Falho Podia Parecer Validacao Limpa

- Severidade: high.
- Evidencia/causa: preview_integration so acrescentava issues se rerender sucedia;
  second_issues vazio era interpretado como sucesso mesmo sem frames reinspecionados.
- Impacto: timeline reparada nao verificada podia substituir a entregue.
- Cobertura previa: P1.15; ramo de falha nao estava no checklist especifico.
- Arquivos/solucao: preview_integration.py; render failures explicitos,
  successful_rechecks==expected_rechecks obrigatorio e repaired_timeline apenas
  se repair_accepted.
- Testes: test_failed_repair_render_never_reports_ok.
- Status: fixed. Canary valida somente intervalos renderizados, nao o video inteiro.

## DISC-007: Cache Reutilizava Dados Alterados E Indisponibilidade Definitiva

- Severidade: high.
- Evidencia/causa: Context.step validava key/status, nao checksum dos dados; aceitava
  unavailable/blocked do cache. Chunk ASR corrompido levantava erro sem recomputar.
- Impacto: evidencia alterada ou dependencia reparada podia ficar invisivel na retomada.
- Cobertura previa: P1.23/P1.24; instancia concreta adicional em Context/ASR.
- Arquivos/solucao: core.py, transcription.py, vision_checkpoint.py, pipeline.py,
  run_status.py; data_checksum, retry de unavailable, recomputacao local, fingerprints
  externos por etapa, DAG, progress/code/model/checksum-chain/sampling-state.
- Testes: corrupted_stage, unavailable_stage, corrupted_ASR, semantic corruption,
  vision chain, decoder REAL interrupt/resume com detector FIXTURE, full pipeline.
- Status: fixed em fixtures/execucao sintetica. Soak real e codec VFR longo pendentes.

## DISC-008: Download De Assets Verificava Tamanho, Nao Hash Confiavel

- Severidade: high.
- Evidencia/causa: download_models.py apenas calculava SHA depois de aceitar o arquivo;
  nao o comparava aos hashes ja fornecidos em models/vision_models_manifest.json.
- Impacto: resposta alterada/corrompida suficientemente grande podia ser carregada.
- Cobertura previa: preflight/hashes genericos; trust anchor nao explicitado.
- Arquivos/solucao: scripts/download_models.py; hashes oficiais do pacote como
  expected, limite de tamanho, atomic replace somente depois de conferir, cleanup .part.
- Testes: hash mismatch nao instala asset e remove parcial, sem rede real.
- Status: fixed. Atualizacao legitima de modelo exige revisar hash/fonte explicitamente.

## DISC-009: Registro Do Downloader Podia Escapar Da Pasta Do Video

- Severidade: high.
- Evidencia/causa: media.resolve_input fazia directory/previous.filename sem verificar
  containment; hash correto nao impedia filename com traversal ou link externo.
- Impacto: cache importado/adulterado podia reutilizar midia fora da pasta autorizada.
- Cobertura previa: P1.26 genericamente; registro de download nao enumerado.
- Arquivos/solucao: media.py; basename estrito, sem slash/drive/.. ou symlink;
  registro JSON corrompido nao e aceito; timeout de socket.
- Testes: cached external media com hash correto ainda e rejeitada antes de download.
- Status: fixed. Download YouTube real/rede/cookies nao executado nesta maquina.

## DISC-010: Composicao Estavel Mantinha Burst Visual Permanente

- Severidade: medium.
- Evidencia/causa: SamplingScheduler renovava burst_until em TODA amostra com
  dois rostos ou sem boca detectada, inclusive planos de estudio estaveis.
- Impacto: speech_sample_fps alto permanente sem beneficio medido, ampliando CPU/I/O.
- Cobertura previa: P2.1 genericamente; causa operacional concreta nao explicitada.
- Arquivos/solucao: visual_sampling.py, vision.py; bursts por mudanca de composicao,
  movimento/cut; sondagem de boca ausente espacada; estado salvo no checkpoint.
- Testes: stable_multiple_people, dynamic sampling, clean/resume decoder equivalence.
- Status: fixed. HOG/YOLO/face-first e ganhos reais precisam benchmark, default mantido.

## DISC-011: GUI Trocava Modelo Configurado Por Outro Instalado

- Severidade: high.
- Evidencia/causa: App.refresh_ollama substituia escolha ausente por names[0].
- Impacto: readiness podia usar um modelo nao escolhido, ate embedding-only;
  violava expectativa de falhar diante de capability configurada ausente.
- Cobertura previa: GUI/preflight genericamente; troca silenciosa nao enumerada.
- Arquivos/solucao: app.py; escolha preservada, ausencia exibida. Lambda de erro
  captura mensagem redigida antes de o contexto de excecao ser limpo.
- Testes: callback GUI FIXTURE preserva qwen3:14b com apenas outro modelo instalado.
- Status: fixed. GUI nativa/tecnologia assistiva e Ollama real permanecem pendentes.

## DISC-012: Baseline Auxiliar Herdava Pacotes Globais

- Severidade: high para a integridade da validacao, nao vulnerabilidade do produto.
- Evidencia/causa: pyvenv.cfg inicialmente tinha include-system-site-packages=true;
  pip-audit inicial alcancou 216 advisories em 24 pacotes herdados.
- Impacto: resultados podiam depender de pacotes alheios e ser descritos incorretamente
  como baseline hermetico ou CVEs do Analyzer.
- Cobertura previa: disciplina de evidencias; incidente de ambiente nao era requisito funcional.
- Arquivos/solucao: .venv temporaria isolada de verdade; documentacao distingue os
  baselines. Nenhum pacote global foi atualizado/removido. Apenas pip auxiliar recebeu
  correcao apos re-scan isolado. Essa .venv nunca entra no ZIP.
- Testes/evidencia: sys.path sem site-packages global, User site=false, re-scan isolado
  sem advisory conhecido. Isso nao valida dependencias pesadas nao instaladas.
- Status: fixed. Python 3.11 runtime continua pendente, nao substituido pelo 3.13.

## Cobertura Do Quarto Passe

Foram inspecionados pipeline/engines first-party, CLI/GUI, installers/BATs,
requirements, modelos manifestados, schemas, exporters, reports/handoff, sampling,
tracking/identidades, semantico, camera/geometry/motion/planner, preview, overrides,
cache/checkpoints, scripts e tests/docs relevantes. Testes de mocks nao foram usados
para alegar modelos funcionais; quando disponivel, decoder/FFmpeg/subprocessos/HTTP
foram exercitados de verdade com fonte sintetica.

Instalacao limpa e Windows/Python 3.11: pendentes, com doctor de recursos enabled.
Long-video/RAM/VRAM: reducao de duplicacao/serialization implementada, sem soak/peak
RSS real. Cancelamento/corrupcao: checksums, atomic writes, locks e processo filho
real em timeout; modelos/hardware nao exercitados. Network/offline/gated: contratos
preflight e fixtures, sem credenciais reais. Segredos: scanner forte integral dos
pacotes, redaction de logs/tracebacks; nao auditoria formal de toda classe de segredo.
ASD neural/treinamento/publicacao/render final foram mantidos fora do escopo.

Achados high deste levantamento receberam correcao/regressao. Isso nao e alegacao
de ausencia absoluta de riscos nem homologacao de hardware/modelos/3.11.