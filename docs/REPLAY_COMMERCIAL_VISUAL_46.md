# Etapa 46 — replay visual comercial 17c

`--from-stage commercial_visual` e `--from-stage 17c_commercial_visual` executam o mesmo fluxo. O alias legado `commercial` agora tem esse contrato: exige mídia local original e OCR disponível. Para apenas reclassificar ASR, sem OCR, o fluxo existente é `--from-stage understanding`.

A fonte é o argumento **posicional** de `analyze.py`; não existe `--source`. `--source-hash` é uma conferência adicional do SHA-256 do metadata, não substitui a mídia. `--config` aceita YAML (inclusive JSON compatível). Não há flag `--ocr`: configure `ocr.enabled`, `ocr.languages` e `ocr.tesseract_cmd` no arquivo de configuração.

Exemplo de configuração parcial `config/replay_commercial_visual.yaml` (arquivo a criar pelo operador com o caminho real do binário instalado):

```yaml
ocr:
  enabled: true
  languages: por+eng
  tesseract_cmd: 'C:\Program Files\Tesseract-OCR\tesseract.exe'
preview:
  enabled: false
export:
  second_curation_auto: false
  include_candidate_previews: false
```

Exemplo PowerShell, sem instalar dependências, renderizar preview ou gerar ZIP de entrega:

```powershell
$mediaPath = 'D:\Midias\programa_original.mp4'
$analysisPath = '.\analysis\programa_existente'
$replayPath = '.\analysis\replay_17c_separado'
$mediaHash = (Get-FileHash -LiteralPath $mediaPath -Algorithm SHA256).Hash.ToLowerInvariant()
python .\analyze.py $mediaPath --replay-analysis $analysisPath `
  --from-stage commercial_visual --source-hash $mediaHash `
  --config '.\config\replay_commercial_visual.yaml' --output $replayPath --offline
```

Confirme primeiro que `$mediaHash` corresponde ao SHA-256 do metadata da análise. Nunca substitua o metadata para fazer uma mídia diferente passar. Um diretório extraído de referência histórica continua somente leitura. `--allow-legacy-snapshot` permite o contrato legado explicitamente; não atesta inferência atual. `--force` ignora os caches da saída do replay, mas continua sem executar ASR, diarização, tracking, person_reid, entendimento/Ollama ou semantic neste fluxo.

O replay valida checksums locais dos JSONs, IDs/tempos de transcrição e referências semânticas. Exige `main_moments.json` verificável para conservar os candidatos da etapa 16. Mídia ausente/divergente, OCR desabilitado, binário/idiomas ausentes e falha total de decode/OCR produzem `analysis_status=blocked`, `17c=blocked` e `replay_blocked.json` com instrução. O CLI retorna código 1 quando não existe pacote; também retorna 1 com `second_curation_auto=false`, mesmo havendo reexportação JSON válida (contrato preexistente do CLI). A saída JSON deve ser conferida nesse modo.

O runtime reporta habilitação, executável e seu SHA-256, versão medida, idiomas disponíveis/solicitados e OpenCV. O cache 17c incorpora SHA-256 da mídia, candidatos, configuração/limite OCR, runtime, checksums upstream e hashes dos algoritmos. Antes de reusar OCR, a fonte e o runtime são verificados de novo; resultados de outra fonte são bloqueados, inclusive no cache com checksum de dados consistente. Checksum corrompido do cache provoca nova execução; checksum corrompido do snapshot rejeita a entrada. Caminhos com `..`, symlinks e componentes reparse do Windows são recusados antes de resolver caminhos, incluindo fonte, snapshot, referências e cache 17c.

`commercial_visual_s8.json` contém o recibo de execução, recursos de frames (hash dos bytes decodificados, shape, instante solicitado, posição do decoder quando disponível), texto literal reconhecido e source_sha256. O tempo de amostragem continua uma posição solicitada de seek; não comprova precisão temporal de frame ou permanência contínua na tela. Contact sheets/thumbnails históricos não são recibos OCR. Este fluxo utiliza decode seletivo da mídia, não OCR de imagens históricas. A falta de thumbnails não bloqueia quando a fonte local está validada; sem essa fonte, bloqueia.

Depois do 17c, o refinamento comercial e a shortlist são recalculados; revisão de legendas, planejamento/direção, verificador de preview e relatórios seguem seus contratos/configurações. `17d_targeted_asr` é explicitamente skipped: reparo de áudio dependente da seleção requer revisão posterior e não é executado por replay visual. Não se herdam aprovações. `PARTIAL`, `READY_FOR_REVIEW`, `PREVIEW_APPROVED` e `PUBLISH_READY` continuam separados, e publicação exige aprovação humana por hash.

`replay_provenance.replay_plan.stage_dispositions` discrimina `reprocessado`, `snapshot_reused` e `not_available`. Cache hit das etapas processadas aparece em `stage_runtime`/`stage_status`; snapshot reutilizado não é inferência nova. Estado antigo sem artefato validado não vira sucesso. Checksums são verificações de integridade do pacote local, não assinatura/autenticação contra alteração coordenada de JSON e manifesto.

Homologação pendente: Tesseract real/por+eng, decode e precisão dos seeks em mídia real autorizada, symlink/junction/reparse e UI de revisão no Windows. Os testes da etapa usam mídia sintética de hash conhecido, decode simulado e o loop real de targeted_ocr com Tesseract simulado. Não demonstram acurácia em Clovis nem execução de Tesseract instalado.
