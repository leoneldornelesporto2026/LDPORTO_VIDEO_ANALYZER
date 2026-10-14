# P0 — fidelidade da transcrição original

Data: 12/10/2026. Escopo: inspeção de código e regressão sintética offline no ambiente Windows existente. Nenhuma inferência ASR real, execução integral do pipeline, acesso ao Ollama, instalação ou download foi realizado por esta auditoria.

## Causa e limites da conclusão

`config/config.yaml` e `src/ldporto/config.py` definiam `language: pt`; `TranscriptionEngine.recognize` encaminhava esse idioma obrigatório ao faster-whisper. Isso impedia a detecção automática de inglês. Não foi encontrada chamada de produção com `task=translate`; a tarefa estava implícita no padrão do backend. Não foi ouvido nem reprocessado o áudio de `Me at the zoo`: a origem acústica exata da hipótese contendo “frutas” permanece **não validada**. Nenhuma palavra real foi corrigida por suposição.

Outras perdas de evidência comprovadas no código: o idioma de `TranscriptionInfo` era descartado; o agrupamento e a diarização descartavam metadados de idioma e revisão; hipóteses alternativas perdiam proveniência; a importação alterava objetos fornecidos pelo chamador e descartava traduções separadas; a seleção da fonte limpa podia promover texto divergente apenas por maior probabilidade do modelo.

## Alterações implementadas

- Idioma padrão `auto`, encaminhado como `language=None`; `task=transcribe` explícito em produção e no canário local. Idiomas `pt` e `en` continuam escolhas explícitas, sem fingir que a probabilidade de idioma forçado constitui detecção acústica.
- `multilingual=true` no modo automático utiliza a capacidade já existente no faster-whisper instalado de detectar idioma durante as janelas de decodificação. O `Segment` instalado não expõe o idioma de cada janela: `language` do segmento permanece `null`, enquanto `language_hint` e `language_detection_scope=chunk_initial_hint` identificam honestamente a informação disponível. Não há detecção lexical inventada nem inferência adicional para preencher idioma.
- Cada hipótese recebe ID ligado ao hash do áudio, offset, configuração de decodificação, idioma, prompt (somente hash), versões do backend, hash do código, dispositivo e fingerprint já coletado pelo preflight quando disponível. Palavras referenciam `hypothesis_id`; não repetem a proveniência completa. Metadados completos ficam nos chunks originais, na tabela de hipóteses e nas alternativas.
- Limites novos de multipass: `max_review_calls=16` e `max_review_audio_seconds=180`, além do limite de regiões existente. O tempo de áudio é contado por chamada, inclusive quando uma região possui várias fontes. Regiões/hipóteses que excedem orçamento ficam pendentes com motivo, sem perder marcação de revisão.
- Texto ou idioma divergente entre pilotos impede a promoção automática da fonte limpa. O áudio original é escolhido e palavras dos intervalos observados recebem revisão. Probabilidade alta não autoriza substituir texto divergente.
- Divergências entre hipóteses, idioma de baixa confiança, problemas temporais e flags recebidas propagam motivos para palavras e segmentos, inclusive após associação de locutores. A transcrição permanece intacta; discrepância ou idioma incerto tornam o estágio `partial`. Probabilidade do modelo não é probabilidade calibrada de correção.
- Importações são copiadas. Textos explicitamente marcados como tradução ou reescrita semântica são rejeitados no campo canônico. Traduções são mantidas na coleção separada `translations`, com idioma de destino e referência a segmento original existente; o segmento original é preservado como âncora mesmo após divisão por locutor. Discrepâncias entre `word`, `raw` e texto de segmento são preservadas e sinalizadas, sem escolher uma correção por adivinhação. Ajustes de timestamps mantêm `raw_start`/`raw_end`.
- O analysis expõe `transcript_translations`, `transcript_original_import_segments`, `transcription_language_hypotheses`, `transcription_review_budget` e proveniência adicional. As alterações de semântica/exportação foram coordenadas com os responsáveis pelos respectivos módulos; traduções não entram como transcrição original.

Arquivos deste escopo: `src/ldporto/transcription.py`, `targeted_asr.py`, `diarization.py`, `config.py`, `inference_smoke.py`, alterações limitadas de metadados em `pipeline.py`, `config/config.yaml` e `src/tests/test_transcription_fidelity.py`. Imports sem consumidores (`re`, `numpy`, `overlap`) foram retirados de `transcription.py`; não houve mudança de dependências instaladas ou requisitos.

Uma revisão independente posterior identificou perda de incerteza na reconstrução de candidatos em `understanding.py`: as fronteiras finais podem incorporar segmentos novos, embora a hipótese semântica original estivesse limpa. Foi aplicada propagação dos flags de ASR sobre os segmentos finais do candidato antes do ranking, sem modificar scores ou política de seleção. O caso novo verifica uma extensão de fronteira que inclui segmento incerto e preserva essa informação até o diagnóstico editorial.

## Comandos reais e resultados

Os comandos foram executados com `.venv\Scripts\python.exe`, sem acionar modelos. `Tee-Object` gravou a saída e `exit $LASTEXITCODE` preservou o código de saída do pytest.

1. `.venv\Scripts\python.exe -m pytest -q src/tests/test_transcription_fidelity.py src/tests/test_v42_perception.py src/tests/test_v42_cache.py src/tests/test_v44_targeted_asr.py src/tests/test_stage49_on_demand_asr.py src/tests/test_stage60_inference_smoke.py`
   Resultado inicial: **88 passed in 2.97s**, saída `asr_targeted_tests_initial.txt`.
2. Ao revisar contratos e incluir semântica: mesmo comando acrescido de `src/tests/test_v43_semantic.py src/tests/test_stage14_semantic_fallback.py src/tests/test_stage40_semantic_benchmark.py`.
   Resultado intermediário: **129 passed in 2.64s**, saída `asr_targeted_tests_review.txt`.
3. Após aplicar a revisão independente sobre divergência de texto no mesmo idioma e identidade da hipótese: mesmo conjunto integrado, **131 passed in 2.73s**. A revisão final encontrou ainda um caso de importação em que o marcador de configuração `auto` poderia virar idioma do texto; ele foi corrigido com um caso adicional, mantendo idioma desconhecido como `null`.
   Resultado final deste escopo: **132 passed in 2.93s**, saída `asr_targeted_tests_final.txt`.
4. `.venv\Scripts\python.exe -m pytest --collect-only -q src/tests/test_transcription_fidelity.py`
   Resultado após o caso adicional de entendimento: **32 tests collected**, saída `asr_new_test_collection.txt`.
5. `.venv\Scripts\python.exe -m pytest -q src/tests/test_transcription_fidelity.py src/tests/test_stage12_candidate_recovery.py src/tests/test_s3_editorial_intelligence.py src/tests/test_stage10_humor.py src/tests/test_stage11_discourse_boundaries.py src/tests/test_stage14_semantic_fallback.py src/tests/test_stage48_editorial_recovery.py src/tests/test_v2_perception.py src/tests/test_v42_export.py`
   Resultado da propagação até os candidatos finais: **136 passed in 3.92s**, saída `asr_understanding_uncertainty_tests.txt`.

Os 32 casos novos cobrem contratos simulados PT/EN/misto, tarefa/idioma explícitos, informação de idioma ausente e de baixa confiança, proveniência, passagem pela diarização e candidatos finais, importação sem mutação, traduções separadas e referências inválidas, rejeição de reescrita, divergências sem substituição, limites de custo, fonte limpa contraditória em PT e no mesmo EN, timestamps originais, configuração `auto` importada e identidade alterada pela configuração de decodificação. Nenhum teste antigo foi removido neste escopo. O número agregado acima inclui testes existentes e deve ser combinado com a regressão integral registrada pelo responsável pela entrega.

## Homologação e performance

**Resolvido e testado com fixtures:** configuração forçada incorreta como padrão, tarefa original explícita, metadados/proveniência, preservação de importação, segregação de traduções, proteção de hipóteses e orçamentos de reprocessamento.

**Parcialmente resolvido:** fidelidade acústica. Os controles foram implementados e os contratos testados; Whisper pode continuar produzindo hipóteses erradas ou perder alternâncias de idioma dentro de uma janela. `language_hint` inicial não descreve obrigatoriamente a fala de cada segmento.

**Pendente / não validado:** ouvir e homologar português, inglês e code-switching com mídia real e faster-whisper large-v3 local; verificar a causa acústica do trecho “frutas”; medir qualidade de palavras e alinhamento/timestamps; comparar latência/VRAM e efeitos de `multilingual` em benchmark equivalente. Os testes aqui não medem acurácia, WER nem ganho de latência de inferência. Apenas verificam limites determinísticos de custo e preservação de evidências.

Importações sem rótulo que contenham traduções não podem ser reconhecidas como tradução sem evidência acústica ou proveniência fornecida. Não há aprovação de áudio, publicação ou legendas implícita nas novas flags/metadados. O esquema de estados e gates existente continua aplicável.
