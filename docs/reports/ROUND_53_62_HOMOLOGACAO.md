# Homologação 53–62 — 2026-10-09

Implementação técnica concluída. `technical_tests_passed=true` no escopo
declarado; `real_media_homologated=false`; `publication_approved=false`.
Não existe evidência de superação do OpusClip. Testes verdes não medem qualidade
editorial, OCR de televisão, identidade, falante ativo ou entrega de zoom real.

O export verificável é `docs/reports/ROUND_53_62_HOMOLOGACAO.json`, schema
`schemas/round62_homologation.schema.json`. Inclui hashes de checkpoints,
módulos, JUnit/logs, dez checks e resultados nullable. O gerador não executa
modelos, acessa rede, renderiza ou gera ZIPs; recusa sobrescrever saída.

## Evidência executada

- Regressão ampla dos testes atuais: **1509 passed, 4 skipped, 1 deselected**,
  zero failed/xfail/XPASS reportados, **160.96s**, exit **0**.
  Não é suite completa sem exclusões: foi excluído somente
  `src/tests/test_v4_final.py::test_work_package_has_single_derived_manifest_files`,
  pois gera snapshot ZIP, reservado ao orquestrador. Sem filtro `-k`.
- Focalizado definitivo 53–62: **168 passed, 1 skipped**, zero failed/xfail/XPASS,
  **11.73s**, exit **0**. Inclui o novo comparador A/B e leitura UTF-16/UTF-8.
- AST de **247 arquivos Python**, parse de **16 schemas JSON**, exit **0**.
  Schema do relatório validado pelo exportador; teste negativo impede transformar
  o relatório offline em aprovação de publicação.
- OCR local: `python scripts/dev/diagnose_ocr53.py --languages por+eng`,
  exit **2**, `dependency_missing / ModuleNotFoundError` no import pytesseract.
  Nenhuma inferência Tesseract feita. Idiomas disponíveis/versão: null.
  `por+eng` foi solicitado pela CLI, mas o diagnóstico encerrou antes de verificar idiomas.

Logs, exit codes, recibo comercial e hashes estão em `automacao/execucao/etapa62/`.
A regressão ampla iniciou antes dos arquivos62 novos; a focalizada definitiva cobre
as alterações finais. Não somar os dois conjuntos como casos únicos.
O primeiro export falhou (exit1): diagnóstico gravado pelo PowerShell em UTF-16
era lido como UTF-8. Corrigido leitor BOM-aware com teste; export verificado
passou (exit0), sem esconder o log inicial. Logs/recibos intermediários preservados.
Os testes incluem mocks e render FFmpeg de mídia sintética temporária; pequenos
ZIPs de fixtures dos testes existentes não são snapshots/entregas do projeto.

Skips reais: executável POSIX do autopilot incompatível com Windows; privilégio
symlink Windows; OCR sintético opt-in `LDPORTO_STAGE55_REAL_OCR=1`; Tk sem display.
Nenhum desses itens conta como passed. CUDA/CTranslate2, Community-1, Whisper,
YOLO, MediaPipe, Ollama e Tesseract reais precisam do canário opt-in60 e caches
locais; os mocks da regressão não atestam esses runtimes. Disponibilidade de
pacote instalada também não significa inferência ou device efetivamente usado.

## Dez checkpoints

Cada linha está ancorada no checkpoint de mesmo número em
`automacao/execucao/checkpoints/` e no módulo `src/tests/test_stageNN_*.py`.
O JSON fornece caminhos existentes, SHA256, contagem e status conservador.

| Etapa | Contrato validado offline | Homologação real pendente |
|---|---|---|
| 53 | OCR disabled/ready/executed distintos | pytesseract, exe e por+eng |
| 54 | GUI OCR persiste escolha, invalida resultado antigo | Tk/Windows com display |
| 55 | Comercial conserva desconhecidos e prova amostrada | Casos reais anotados |
| 56 | Replay 17c, hashes/origins/cache e isolação upstream | Recibo actually_executed no episódio |
| 57 | YOLO local opcional, fallback e device verdadeiro | Peso confiável, CPU/CUDA e VRAM concorrente |
| 58 | A/B com consentimento, anchors e goldset nullable | Anotações humanas e tracking real |
| 59 | Budget serial, retomada, cleanup e métricas atuais | Picos/throughput no Windows real |
| 60 | Load separado de inferência, timeout e replay sem autorização | Canário dos modelos locais |
| 61 | Render sintético 9:16, CRC/SHA e clipping bloqueante | Canário 10–30s, escuta e aprovação humana |
| 62 | JUnit, nulls/schema, A/B e preservação de saídas | Benchmark real controlado |

Comercial sintético: oito casos executados com decoder/OCR simulados e fusão
atual; oferta/institucional confirmados, um provável, uma discussão de marca
sem evidência de anúncio. **FP=[], FN=[]** nos quatro casos decididos;
**quatro abstinências**: qr_only, absent, partial, ocr_only. A regra binária
considera confirmed/probable positivos e measured_no_ad_evidence negativo;
requires_review/not_measured/label null abstêm. Isso não é acurácia populacional.
Precision/recall reais e goldset corporal/editorial permanecem null.
`commercial_synthetic.json` guarda os resultados efetivamente produzidos.

HOG/CPU executado em imagens sintéticas na etapa59 é referência histórica com
escopo explícito, não device medido no Clóvis atual. YOLO e CUDA reais nesta
rodada: null. Replay17c no episódio: null/not_measured. Canário61 real:
`real_canary_not_run`, `SOURCE_MEDIA_MISSING`; o recibo sintético de etapa61
permanece separado. Não se atribui aprovação humana a render técnico.

## Baseline Clóvis e proveniência

Referência principal, sem duplicar métricas: **CHECKPOINT_ETAPA_52.md**, seção
“Métricas, evidência e limitações”: candidatos/únicos/shortlist/Stories,
flagged, speaker-person, active speaker, foco câmera, zoom entregue e clipping.
Os **4627 microtracklets** constam também em
`automacao/execucao/etapa58/REPORT_ETAPA_58.json` como baseline fornecido.
Complementos fornecidos pelo enunciado62, não remedidos: denominador flagged
**19299** e Ollama **aproximadamente 90 minutos**. Origem histórica, sem custo
real medido nesta rodada. Todos os pós/deltas de mídia real = null/not_measured.

A etapa52 já verificou origem dos ZIPs: SECOND_CURATION_READY schema1.0,
analyzer4.4.0/build R4.9-S4-TRACKING-FACIAL; CHATGPT_REVIEW é export de
2026-10-08. Não foram abertos/usados novamente como evidência atual nesta etapa.
Nenhuma análise existente alterada. Nenhum número de fixture é comparado ao
benchmark real ou a produto concorrente.

## Sequência local futura (usuário, não executada automaticamente)

Execute na raiz atual, com Python do projeto. Substitua os caminhos de exemplo
por arquivos locais autorizados e diretórios **novos**. Não instale/download
modelos ou execute vídeo completo para resolver dependência indisponível.

1. GUI: OCR comercial → selecionar tesseract.exe local → idiomas por+eng →
   habilitar conscientemente → Verificar OCR. Provisionar manualmente fora desta
   rodada pytesseract compatível, executável e traineddata quando ausentes.
   Confirmar o mesmo Python usado pelo launcher. CLI de disponibilidade:

   ```powershell
   python scripts/dev/diagnose_ocr53.py --tesseract-cmd "C:\Tesseract-OCR\tesseract.exe" --languages por+eng
   ```

   Somente se READY, executar o smoke sintético explícito adicionando `--smoke`.
   READY não atesta OCR do episódio. Não mudar PATH global.

2. GUI: Detector corporal local → HOG/CPU explícito se YOLO não foi homologado;
   ou selecionar `.pt` confiável local, backend yolo, device cpu inicialmente.
   Conferir SHA256 com `Get-FileHash -LiteralPath "C:\pesos\yolo11n.pt" -Algorithm SHA256`.
   Seguir `docs/YOLO_LOCAL_57.md`; peso/runtime/licença são pré-condições,
   sem aprovação implícita por existir arquivo. Só testar cuda após verificar VRAM.
   Salvar perfil local completo; manter opções de export/previews desligadas no replay OCR.

3. Diagnóstico e smoke inferencial curto, sem source (não inicia pipeline longo):

   ```powershell
   python analyze.py --doctor --offline --config "C:\config\perfil-local.yaml"
   python analyze.py --inference-smoke --offline --config "C:\config\perfil-local.yaml" --smoke-test-seconds 30 --smoke-total-seconds 120 --smoke-output diagnostics/smoke62_novo.json
   python analyze.py --smoke-replay diagnostics/smoke62_novo.json
   ```

   Conferir calls, device, hashes e executed_pass de cada capacidade habilitada.
   Replay não autoriza análise longa. Sem GPU/Ollama carregados neste relatório;
   não há garantia de timeout do servidor Ollama após terminar worker.

4. Replay seletivo no mesmo episódio/snapshot atual com SHA comprovado:
   perfil `ocr.enabled=true`, `ocr.languages=por+eng`, executável local;
   `export.second_curation_auto=false`, `preview.enabled=false`,
   `export.include_candidate_previews=false` e limite de candidatos pequeno.

   ```powershell
   python analyze.py "C:\midia\clovis.mp4" --replay-analysis "C:\analises\snapshot-atual" --from-stage commercial --config "C:\config\ocr-replay.json" --output "C:\analises\ocr62-novo" --offline --dry-run
   python analyze.py "C:\midia\clovis.mp4" --replay-analysis "C:\analises\snapshot-atual" --from-stage commercial --config "C:\config\ocr-replay.json" --output "C:\analises\ocr62-novo" --offline
   ```

   Só segundo comando após plano sem blockers. Conferir reprocess_manifest.json,
   hashes/source, origin actually_executed versus cache/snapshot, OCR17c measured
   e idiomas, contagens/falhas; upstream ASR/LLM preservado. Cache hit não é
   nova inferência. O script replay_commercial_v44.py não reexecuta OCR.

5. Antes de vídeo completo, realizar canário61 em **arquivo curto autorizado
   separado 10–30s** e JSON atual com SHA e timestamps já existentes:

   ```powershell
   python scripts/dev/curation_canary61.py --analysis "C:\amostra\evidencia.json" --source "C:\amostra\curto.mp4" --candidate-id M1 --output diagnostics/canary62_novo --authorize-short-media
   ```

   Conferir clipping/texto/GC/QR, legenda/áudio/timestamps e zoom; obter parecer
   humano por hash. Não apontar canário para episódio longo.
   Somente após blockers controlados e decisão explícita do usuário:

   ```powershell
   python analyze.py "C:\midia\clovis.mp4" --offline --config "C:\config\benchmark62.json" --inference-smoke --output "C:\analises\clovis62-novo"
   ```

   Esse último comando executa análise completa e tem custo alto; não executado
   nesta etapa. Config deve habilitar somente modelos locais homologados.

6. Para pacote segunda curadoria, habilitar manualmente
   `export.second_curation_auto=true` em perfil de export separado, sem previews
   de lote automáticos. A rota atual exporta após replay; ação de gerar ZIP é
   **exclusiva do usuário/orquestrador**, nunca parte desta rodada:

   ```powershell
   python analyze.py "C:\midia\clovis.mp4" --replay-analysis "C:\analises\clovis62-novo" --from-stage commercial --offline --config "C:\config\export62.json" --output "C:\analises\curadoria62-nova"
   python scripts/dev/audit_homologation52.py --package "C:\pacotes\SECOND_CURATION_READY_novo.zip" --output "C:\relatorios\audit62-novo.json"
   python scripts/dev/compare_benchmark62.py --baseline "C:\analises\baseline\analysis.json" --current "C:\analises\clovis62-novo\analysis.json" --output "C:\relatorios\AB62-novo.json"
   ```

   O comparador preserva source_sha256, SHA do analysis, configuração integral
   e fingerprints salvos; hashes ausentes são null. Não usar ZIP histórico como
   baseline atual. Hashes de configuração diferentes suprimem deltas legados;
   para HOG/YOLO usar o protocolo controlado `docs/BODY_AB_58.md`.
   Prompts efetivos completos não são comprovados só por PROMPT_VERSION/digest
   ou código atual: preservar captura local real das requisições por execução,
   incluindo messages, schema/format, modelo e opções, sem credenciais. A rota
   atual não exporta automaticamente todas as requisições efetivas. Sem captura,
   `effective_prompts=null` e `provenance_complete=false`: bloquear alegações A/B
   dependentes de prompts. Se houver capturas verificadas, acrescentar
   `--baseline-prompts "C:\relatorios\requests-before.json" --current-prompts "C:\relatorios\requests-after.json"`.
   Anexos são declarados pelo usuário e exigem revisão; SHA não autentica sua origem.

## Próximos ajustes derivados das lacunas reais

| Prioridade | Evidência / ajuste | Custo e possível regressão | Prova que encerra pendência |
|---|---|---|---|
| P0 | pytesseract ausente nesta execução; provisionar ambiente local manualmente | Setup fora desta rodada; incompatibilidade com Python/idiomas | READY por+eng, smoke e replay17c com hashes |
| P0 | Fonte/canário real e revisão humana ausentes | Derivação curta, render e inspeção; crop pode cortar cabeça/texto | CANARY61 real + escuta/legibilidade/GC/QR + parecer por hash |
| P1 | Sem goldset real/fingerprints/prompts completos do par atual | 10–20 amostras consentidas e anotação; instrumentação pode expor transcript local se exportada indevidamente | A/B58 e capturas locais verificadas, fonte/modelos/config idênticos ou variação explícita |
| P1 | Symlink/reparse e Tk não homologados, conforme skips reais | Máquina Windows interativa; acesso pode continuar bloqueado | Teste com privilégios locais e GUI real |
| P2 | Teste snapshot excluído por proibição da rodada | Custo de snapshot para orquestrador | Regressão independente e resultado do teste reservado |

Nenhum ajuste de thresholds, sampling ou modelo é justificado por FP/FN zero em
fixtures. Sem medição real, throughput/VRAM/ganho de tempo e custo de modelos
ficam null. Não instalados assets, não houve mídia longa/GPU/Ollama, upload,
serviço pago ou publicação. Estados PARTIAL, READY_FOR_REVIEW, PREVIEW_APPROVED
e PUBLISH_READY continuam separados; READY não significa publicação autorizada.
