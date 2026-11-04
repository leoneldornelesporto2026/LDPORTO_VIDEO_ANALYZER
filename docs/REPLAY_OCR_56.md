# Replay OCR comercial (etapa 56)

Execute na raiz atual, Python 3.11, usando uma análise extraída e mídia original
local. Os caminhos abaixo são exemplos a substituir, não evidências disponíveis.
O JSON/YAML de configuração deve usar os campos existentes `ocr.enabled=true`,
`ocr.languages`, `ocr.tesseract_cmd` quando necessário e
`export.second_curation_visual_candidate_limit`. O limite é de candidatos:
no máximo três frames por candidato, sem varredura integral. Para somente JSON,
configure `export.second_curation_auto=false`, `preview.enabled=false` e
`export.include_candidate_previews=false`; não habilite geração de pacotes/previews
para corrigir OCR. Nenhuma instalação ou download faz parte deste comando.

```powershell
python analyze.py "C:\midia\original.mp4" --replay-analysis "C:\analises\snapshot" --from-stage commercial --config "C:\config\ocr-local.json" --output "C:\analises\replay-ocr" --offline --dry-run
python analyze.py "C:\midia\original.mp4" --replay-analysis "C:\analises\snapshot" --from-stage commercial --config "C:\config\ocr-local.json" --output "C:\analises\replay-ocr" --offline
```

`commercial`, `commercial_visual` e `17c_commercial_visual` são aliases da mesma
rota real: `replay_analysis` -> `Context.step(17c_commercial_visual)` ->
`targeted_ocr`, com mídia validada por SHA-256 antes de abrir frames. Hash ausente,
divergente, traversal, runtime indisponível ou falha total bloqueiam a operação.
`--source-hash` é uma validação adicional opcional; não substitui o hash upstream.
`--allow-legacy-snapshot` só permite versões legadas explicitamente; não atesta
inferência atual. `--force` ignora o cache downstream e não chama ASR/LLM.

`13_ocr` é o OCR geral das amostras da visão no pipeline completo. Esta rota
seleciona `17c`, que inspeciona janelas de candidatos existentes; não executa
`13_ocr` nem atribui cobertura geral ao vídeo. O script histórico
`scripts/dev/replay_commercial_v44.py` refina texto de snapshot e informa
`ocr_rerun=false`; ele não substitui esta rota. A GUI atual configura OCR e usa
a CLI do Analyzer; não foi criada uma nova ação gráfica de replay nesta etapa.

O dry-run não cria saída nem abre decoder; lista DAG, snapshots verificados,
dependências ausentes e motivos. Estima somente o limite de trabalho, com duração
em segundos null: não há medição real nem promessa de economia exata. Dependências
de snapshot ausentes deixam o plano BLOCKED conservadoramente.

Consumidores recalculados/verificados: refinamento comercial, revisão de legendas,
planner, director, preview verifier e relatórios/curadoria. ASR, pyannote, tracking,
visão e semântica são snapshots; áudio direcionado 17d fica skipped. Preview
verifier com preview desligado não renderiza canário nem concede aprovação.

O cache 17c inclui fonte SHA-256, janelas/candidatos, configuração OCR/idiomas,
limite, amostragem, versão/hash do exe, versões locais e código OCR. Hashes de
traineddata são recuperados de TESSDATA_PREFIX, tessdata ao lado do exe ou
share/tessdata no diretório pai. Caminhos não recuperáveis permanecem null;
quando esse dado é null não se afirma identidade do modelo linguístico. Alterar
OCR invalida 17c/consumidores, sem executar etapas caras upstream.

`reprocess_manifest.json` registra stage_origin (`snapshot`, `cache`,
`actually_executed`, `not_executed`), status, invalidadores, hashes de checkpoints
antes/depois, integridade dos históricos e hash estável da evidência OCR.
O hash de evidência cobre textos/frames/cobertura/fonte, sem cronômetros voláteis.
Não é o SHA do JSON inteiro: recibos de duração variam entre execuções reais.
O status da execução OCR e `report_analysis_status` são registrados separadamente.
OCR desligado/falha total permanecem `not_measured`, evidência SHA=null. Falha
tentada registra actually_executed com status blocked, nunca sucesso fictício.
Históricos e seus builds não são editados. Compare hashes e origins; cache hit
não é nova inferência. publication_ready continua false neste recibo.

Teste focalizado offline:

```powershell
python -m pytest -q src/tests/test_stage56_ocr_replay_audit.py src/tests/test_stage46_commercial_visual_replay.py -r s -p no:cacheprovider --tb=short
```

Mocks provam chamadas/isolamento, não OCR de produção. Smoke real de vídeo de
até 10s requer ação explícita do usuário, fonte nova autorizada, snapshot com
mesmo SHA e Tesseract/idiomas já instalados; não foi executado nesta etapa.
Curadoria READY não implica publish_ready, aprovação humana ou qualidade OCR.
