# Legendas — auditoria individual do pacote canônico

Auditoria somente leitura executada em 17/10/2026. Pacote: `pacotes_para_enviar/SECOND_CURATION_READY_9UCGZia2p1k_20261016_200541_367803_f6b214.zip`, SHA256 `d090841905222237b282af8b25caa02aa8b2bfcb946baae1a6f4ae0f3ab3779c`. Fonte SHA256 `5d089e1825b396dafd6b5918274f3a785eb2d8be2f622497cb7d06fdd7b3b7ea`.

Foram auditados os setenta IDs individualmente, intervalos, status no catálogo, IDs canônicos de palavras/segmentos e motivos de bloqueio. Todos os IDs de palavras e segmentos referidos foram resolvidos no próprio ZIP. Os intervalos do preflight coincidem com os candidatos e permanecem dentro da fonte. Nenhum status foi promovido.

| Escopo | ALIGNMENT_REVIEW_REQUIRED | AUDIO_REVIEW_REQUIRED | Prontos para legenda |
|---|---:|---:|---:|
| Setenta candidatos | 68 | 2 | 0 |
| Story independente legado | 1 | 0 | 0 |

O `status_counts` original registra 69+2 porque soma candidatos e o Story legado. Isso não significa 71 candidatos.

Os dois casos de áudio são `MOMENT_00007_0002` em `[2442,63;2445,01)` e `MOMENT_00014_0002` em `[4079,28;4080,14)`. Seus motivos originais são categoria de áudio indisponível e alinhamento de palavra não verificado. Não foi inferida classificação de fala, canto, música ou silêncio para esses casos.

Todos os setenta têm `allowed_caption_mode=none`, karaoke desabilitado e zero palavras com alinhamento ou áudio certificados. Sessenta e dois candidatos incluem pelo menos um segmento longo sem alinhamento confiável. Vinte e seis informam rascunho de legenda por frase disponível; esse rascunho não modifica o gate nem autoriza karaoke/render final. A falta de categoria de áudio aparece explicitamente como `unknown` no JSON da auditoria.

O ZIP contém 386 segmentos e 2.382 palavras canônicas. A união temporal dos segmentos é 988,01 s: **16,9177%** dos 5840,094 s da fonte. A união dos intervalos de palavras é 881,18 s: **15,0885%**. Esses números medem evidência ASR disponível. As lacunas não foram classificadas automaticamente como instrumental, silêncio ou letra ausente. Timestamps de palavras continuam estimativas do ASR, com confiança não calibrada.

O arquivo `CAPTION_CANDIDATE_AUDIT_baseline.json` contém os setenta registros, texto literal herdado, intervalos, IDs, cobertura por candidato, gaps, motivos, ação humana e hashes dos artefatos originais. Texto literal herdado pode conter erro ASR; não foi corrigido sem escuta. Ação necessária: ouvir o trecho original, verificar texto e limites de frase, alinhar palavras antes de permitir karaoke e validar posição após o crop final. Um bloqueio pertence ao ID correspondente; não foi criado bloqueio adicional de lote.

Comando real:

```powershell
./.venv/Scripts/python.exe docs/reports/r6_20261016/R6_2_FINAL_HANDOFF/audit_caption_narrative.py --package pacotes_para_enviar/SECOND_CURATION_READY_9UCGZia2p1k_20261016_200541_367803_f6b214.zip --label baseline
```

Resultado: PASS para identidade dos setenta IDs, referências, tempos, estados e preservação do hash do pacote. Novas chamadas ASR: zero; nova escuta de áudio nesta auditoria: nenhuma; aprovações criadas: zero. Contagens de revisão ASR existentes no pacote são históricas e não representam execução nesta tarefa.

O cotejo do pacote editorial derivado será registrado separadamente quando a revisão final existir. Este relatório não afirma que um pacote ainda não testado preservou os estados.
