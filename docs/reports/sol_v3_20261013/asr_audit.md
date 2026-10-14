# SOL V3 — ASR localizado e revisão da fonte

Data: 13/10/2026. Escopo desta implementação: comparação e revisão de hipóteses de transcrição, sem chamada de modelos, GPU, Ollama ou pipeline audiovisual por este agente. Nenhuma palavra original foi corrigida e nenhum resultado de audição humana foi produzido.

## Evidência realmente consultada

O pacote `SECOND_CURATION_PARTIAL_jNQXAC9IVRw_20261013_035536_877801_09f678.zip` foi lido sem extração e com checagem de paths. Seus 65 arquivos declarados foram conferidos por SHA-256; o manifesto é o 66º membro. A transcrição contém inglês, incluindo `really, really, really long trunks.`. `task=transcribe`, `text_kind=original_asr_hypothesis`, hint inicial inglês com probabilidade 0,97802734375, traduções vazias. Esses dados pertencem à execução histórica do produtor; não representam nova inferência nesta sessão.

Na inspeção inicial, o pacote ANTES `SECOND_CURATION_PARTIAL_jNQXAC9IVRw_20261012_232326_642182_7f5d97.zip` estava ausente e a tentativa retornou `FileNotFoundError`. O usuário posteriormente restaurou esse arquivo em `pacotes_para_enviar/`; o responsável pela auditoria dos pacotes verificou e comparou ambos. O replay ASR aqui descrito utiliza exclusivamente o pacote DEPOIS e não atribui a si essa comparação adicional.

Dos 37 tokens do pacote disponível, 36 estavam sinalizados. Apenas dois tinham probabilidade de modelo abaixo de 0,60: `Alright,` (0,541015625) e `The` (0,57861328125). As razões originais particionavam as flags em 20 palavras com divergência acústica, 14 com divergência acústica e de fonte, e duas com divergência acústica e baixa probabilidade. `have` era a única palavra sem flag. Nenhuma dessas contagens é WER ou contagem de erro confirmado.

A primeira alternativa, janela 0–7,04s, omite apenas `they` após normalização de caso e pontuação. O intervalo canônico dessa palavra termina em 7,26s, além do áudio recortado: é uma comparação de fronteira incompleta, não evidência de erro em todas as 19 palavras da janela. A segunda janela, 7,72–19,014s, contém `front` em vez de `trunks` e uma repetição adicional de `that's`; o restante mantém os mesmos vocábulos com diferenças de caso, pontuação e pequenas variações de alinhamento.

O piloto de fonte em 10–19,014s reconheceu apenas a frase final na hipótese original e mais conteúdo na fonte limpa. As palavras desse piloto não foram preservadas na exportação histórica, somente texto. Sua discrepância continua **não localizada por palavra**; não se inventaram timestamps nem se assumiu qual hipótese está certa.

## Causas comprovadas e mudanças

| Problema | Causa no código anterior | Correção | Estado |
|---|---|---|---|
| 36/37 flags apesar de duas palavras com baixa probabilidade | Qualquer diferença da string sinalizava todas as palavras que sobrepunham a janela; piloto divergente sinalizava toda a região | Alinhamento monotônico de tokens com timestamps como desempate para repetições; substituição/omissão/inserção localizadas | VERIFIED em fixtures e replay JSON |
| Pontuação, caso e pequenos ajustes temporais tratados como palavra diferente | Comparação literal de string | Normalização somente de caso/pontuação; razões temporais e cosméticas separadas; acentos e vocábulos permanecem distintos | VERIFIED em fixtures |
| Palavra cortada no limite do áudio tratada como discrepância geral | Propriedade por intervalo completo sem distinguir clip | `comparison_clip_boundary` apenas no token afetado; nenhuma escolha de correção | VERIFIED em fixture e caso `they` histórico |
| Alternativa antiga sem palavras/timestamps | Evidência textual sem suporte a localização | Região `unlocalized_text_difference`; nenhuma associação inventada a word IDs | VERIFIED em fixture e piloto histórico |
| Shortlist vazia sem dossiê de audição da fonte | Fila candidata explícita retornava vazia | Dossiê `source_audio_review` independente da shortlist, com palavras originais, alternativas já medidas e orçamento | VERIFIED em fixture de fila vazia |
| Multipass executado aparentava conflito com revisão humana pendente | Resumos mostravam somente fila candidata e flags genéricas | `acoustic_multipass` mantém custo observado; `human_audio_review_status=pending`; zero chamadas novas do dossiê | VERIFIED por contrato; audição humana PENDING |
| Limpeza de flags poderia apagar observação humana | Flags automáticas e externas compartilhavam booleano | Recomposição explícita remove somente razões automáticas conhecidas, preservando flags externas, baixa probabilidade, idioma e timestamps | VERIFIED em fixture |

`src/ldporto/asr_comparison.py` implementa o comparador e dossiê sem dependências novas. `transcription.py` preserva palavras de pilotos em execuções novas, aplica comparação localizada e mantém IDs/proveniência ligados ao código do comparador. `targeted_asr.py` disponibiliza o dossiê da fonte mesmo sem fila candidata; as condições de opt-in, hashes e aprovações da fila candidata continuam obrigatórias. `subtitle_review.py` inclui as métricas de razões, custo acústico observado e status humano separado. A integração de pipeline, relatórios e ZIP foi coordenada com os responsáveis pelos respectivos módulos.

## Replay local real de artefatos históricos

Comando executado:

```powershell
.venv\Scripts\python.exe docs/reports/sol_v3_20261013/asr_replay.py
```

O replay lê o ZIP verificado e trabalha em cópias dos JSONs. **Não modifica o ZIP, a análise original, o áudio, a transcrição, os timestamps nem as probabilidades.** Sua categoria é `integration_local_historical_json_reclassification`, com zero chamadas novas de inferência e zero revisões humanas.

As flags passam de **36 para 6**: duas de baixa probabilidade, uma de fronteira (`they`) e três de divergência localizada (`trunks.`, `that's`, `cool.`; os dois últimos são âncoras locais para uma inserção). A região de piloto sem timestamps permanece incerta como região. Isso é uma redução de marcação excessiva do algoritmo, **não uma melhora comprovada de acurácia acústica**. Palavras verificadas corretas e WER permanecem `null`.

O dossiê registra as duas chamadas históricas de multipass e 18,334s de áudio processado. Esse custo não é atribuído ao replay. O dossiê novo não consome GPU, contém intervalos de audição e exige revisão humana. Observações de fala sobreposta também podem pedir audição sem tornar automaticamente o texto uma palavra errada.

Arquivos de evidência: `asr_historical_replay.json`, `asr_historical_replay_log.txt` e `src/tests/fixtures/sol_v3_asr_historical.json`. A fixture é uma projeção compacta dos 37 tokens e hipóteses efetivamente exportados, com SHA-256 do pacote de origem, sem mídia nem ground truth humano.

## Testes e comandos reais

Foram adicionados 16 casos em `src/tests/test_sol_v3_asr_review.py`: equivalência de caso/pontuação, drift pequeno, uma palavra divergente, tokens repetidos/inserção, clip parcial, drift temporal grande, alternativa sem timing, code switch/acentos, ausência de tokens canônicos, preservação de flags externas, dossiê sem candidata, orçamento, inglês literal e replay histórico. Nenhum teste anterior foi removido.

1. Conjunto inicial de comparação/ASR/cache/fila candidata: **100 passed in 3.23s**, log `asr_targeted_tests.txt`.
2. Conjunto ampliado após incluir a fixture histórica e integração de legendas:

```powershell
.venv\Scripts\python.exe -m pytest -q src/tests/test_sol_v3_asr_review.py src/tests/test_transcription_fidelity.py src/tests/test_transcription_report_integrity.py src/tests/test_v42_perception.py src/tests/test_v42_cache.py src/tests/test_v44_targeted_asr.py src/tests/test_stage49_on_demand_asr.py src/tests/test_stage20_targeted_shortlist.py src/tests/test_stage19_uncertain_words.py src/tests/test_stage21_subtitle_alignment.py src/tests/test_stage22_subtitle_style.py src/tests/test_s7_subtitle_review.py
```

Resultado inicial: **174 passed in 14.88s**. Após explicitar que incerteza de fronteira/timestamp também torna o estágio `partial`, o mesmo comando passou com **174 passed in 14.57s**, saída final `asr_final_tests.txt`. As saídas foram capturadas com `Tee-Object`; `exit $LASTEXITCODE` preservou o código de saída do pytest. Testes são `unit_mocked` e `integration_local` com arquivos/fixtures, não homologação acústica nova.

## Limitações restantes

- **PENDING REAL-VIDEO/HUMAN:** ouvir regiões divergentes e a possível segunda voz. Nenhuma voz foi colapsada, confirmada ou ligada a pessoa por esta implementação.
- **PARTIAL:** localização depende dos timestamps estimados do Whisper; o desempate temporal não é alinhamento fonético verificado. Diferenças grandes de timing ficam explícitas, não são corrigidas.
- **PARTIAL:** pilotos históricos sem palavras não permitem reconstrução acústica; há região incerta sem inventar IDs.
- **RESOLVIDO em outra auditoria desta rodada:** pacote ANTES restaurado pelo usuário, com verificação/comparação dos dois pacotes pelo responsável por exportação. O replay deste relatório continua restrito ao pacote DEPOIS.
- **VERIFIED, canário real inglês:** o responsável pela homologação executou o CLI curto descrito abaixo; original inglês e contrato transcribe passaram. PT/code-switch acústico, audição humana, WER e benchmark repetido permanecem pendentes. O replay e os testes não comprovam WER nem ganho de latência.
- Gates de legendas, preview e publicação permanecem separados; nenhum campo novo aprova correção ou publicação automaticamente.

## Diagnóstico ASR real curto preparado

`scripts/dev/smoke_source_asr.py` utiliza os APIs atuais: `media.inspect(...)["data"]`, `audio.ffmpeg_audio` para WAV temporário mono 16k e `TranscriptionEngine.recognize`. Resolve somente modelo já existente, usa offline/local-files-only, limita duração, preserva a fonte e grava JSON com criação exclusiva. Registra hashes, tempos de extração/carregamento/inferência, dispositivo/compute efetivos, texto, palavras e probabilidades originais. Argumentos `--expect-text`/`--forbid-text` verificam fragmentos sem corrigi-los.

O `--help` foi executado passivamente, com exit 0. A primeira tentativa real feita pelo responsável pela homologação parou antes da inferência devido a uso incorreto do wrapper de `inspect` (`KeyError: duration`); `asr_real_smoke.json` foi preservado. O helper foi corrigido e recebeu um teste CPU com APIs mockados que valida formato de metadata, parâmetros de áudio e recusa de sobrescrita, interrompendo deliberadamente antes de carregar o modelo: **1 passed, 16 deselected in 0.21s**. Isso acrescenta um caso aos 16 testes desta implementação. Nenhuma inferência GPU foi executada por este agente.

Comando preparado para a execução sequencial pelo responsável pela GPU, usando outro arquivo de evidência:

```powershell
.venv\Scripts\python.exe scripts/dev/smoke_source_asr.py "CAMINHO_LOCAL_VIDEO_19S" --output docs/reports/sol_v3_20261013/asr_real_smoke_retry.json --model large-v3 --device cuda --expect-text "long trunks" --forbid-text "frutas"
```

O responsável executou a tentativa seguinte e preservou `asr_real_smoke_retry.json`: **passed**, inferência efetivamente executada em **CUDA / int8_float16**, 1,734s de inferência e 6,063s de carregamento. Os checks de transcribe, original hypothesis, tradução separada vazia, automatic multilingual, presença de `long trunks` e ausência de `frutas` passaram. O processo retornou exit 0. Esta é evidência de inferência real curta da fonte inglesa; não é audição humana, WER, benchmark repetido nem homologação de active speaker/câmera. Nenhuma execução GPU concorrente foi feita por este agente.

## Revisão da integração após diarização

Uma checagem independente encontrou que o agrupamento de locutores descartava incerteza de regiões sem word mapping: no replay histórico, o último segmento passava de `needs_review=true` para `false`, mesmo com região de piloto incerta em 10–19,014s. Foi introduzido `propagate_unlocalized_review` compartilhado entre `annotate_review` e `align_speakers`. Ele reaplica a revisão somente aos segmentos sobrepostos; não marca palavras novas nem modifica texto, probabilidades ou WER. `refresh_review_word_refs` atualiza IDs de segmento e speaker dos snapshots de review por word ID, sem nova classificação de confiança.

Dois casos adicionais verificam o histórico real (o último segmento mantém motivo de source uncertainty com `uncertain_word_ids=[]`, as seis flags de palavra permanecem idênticas) e sobreposição limitada com fronteiras exatas. Comando:

```powershell
.venv\Scripts\python.exe -m pytest -q src/tests/test_sol_v3_asr_review.py src/tests/test_transcription_fidelity.py src/tests/test_v42_perception.py src/tests/test_v42_cache.py
```

Resultado: **79 passed in 2.44s**, log `asr_diarization_region_tests.txt`. O arquivo SOL V3 contém agora **19 casos**: 16 de comparação/review, um do CLI sem inferência e dois de integração após diarização. A regressão integral é registrada pelo responsável pela entrega.
