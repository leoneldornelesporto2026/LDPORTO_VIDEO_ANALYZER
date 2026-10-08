# R4.9 — Sessão 7: Transcrição, Targeted ASR e legendas

## Escopo e resultado

Evolução incremental da R4.9/S6, sem refazer pipeline, remover checkpoints ou substituir o áudio canônico. Os arquivos de saída da transcrição original permanecem intactos até uma correção explicitamente revisada pelo usuário.

**Não foi fornecido o run Emerson/Clóvis contendo as palavras ou áudio relacionados aos 24,2%.** Portanto não é possível atribuir causas quantitativas reais, afirmar que qualquer palavra específica está correta ou medir WER/CER com áudio anotado. Os valores de testes deste release se referem a fixtures e regressões, não a esse programa.

## Como investigar os 24,2%

`src/ldporto/transcription.py::annotate_review` marca `needs_review` quando o modelo retorna `confidence` ausente/abaixo de `low_confidence = 0.60`, há timestamp reparado, um padrão repetitivo suspeito ou alta probabilidade de não-fala. **Esse número não é uma taxa de erro de transcrição**. São sinais de revisão, e as probabilidades do Whisper não são calibradas para acurácia. A S7 mede separadamente:

- `original_review_fraction`: taxa original de `needs_review`, diretamente comparável à métrica antiga se o mesmo run e universo de palavras forem usados;
- `words_flagged_fraction`: fração ampliada incluindo overlap, palavras interrompidas e anomalias de tempo;
- `global_word_reasons`: contagem de motivos não exclusivos (não somar como porcentagens de palavras);
- `candidates[*].word_review_fraction`: taxa de risco apenas das palavras do corte;
- `source_scope`: `full_words` ou `partial_candidate_words` no auditor offline. Se parcial, **não interpretar como taxa do vídeo inteiro**.

Possíveis causas a investigar no áudio original: sobreposição de voz, risos próximos à fala, regionalismos/gírias, hesitação, corte de palavra, ruído, música e timestamps. Isso não prova que algum desses motivos explique o resultado de Emerson até inspecionar as amostras.

## Targeted ASR: o que mudou

O estágio `17d_targeted_asr` recebe agora a seleção real `understanding.editorial_shortlist`. Quando nenhum corte é selecionado, não gasta GPU revendo palavras do resto do vídeo. Quando há shortlist:

1. Revisita o hook e o final/desfecho de cada corte selecionado (inclusive quando o ASR original reportou confiança alta);
2. Prioriza também palavras suspeitas e janelas de fala sobreposta dentro da seleção;
3. Tem custo explícito limitado (`targeted_max_regions: 16`; `targeted_max_audio_seconds: 180`);
4. Relata `candidate_coverage` e `unreviewed_selected_candidates` quando o orçamento não cobre os cortes;
5. Faz reconhecimento no **áudio mono original**, preserva alternativa e confiança como hipótese (`raw_replacement_count = 0`), e NÃO substitui automaticamente uma palavra no original.

O replay que troca texto sem ouvir não é permitido. O trabalho de conferência exige escuta do áudio fonte, particularmente em punchlines, interrupções, palavrões, regionalismos e fala simultânea.

## Validação e renderização de legendas

Novo estágio leve `17e_subtitle_review_s7` depende da transcrição, entendimento e targeted ASR. Produz análise **por corte**, incluindo a alternativa e seus motivos, eventos de risada em janelas grosseiras, sobreposição de fala, palavras truncadas, gaps, timing e número de linhas. Preserva as frases originais: pontuação não é fabricada.

Saídas principais:

- `subtitle_review_s7.json`: índice completo e razões para revisão;
- `subtitle_review_s7/<ID>.draft.srt`: texto e timestamps **provisórios**;
- `subtitle_review_s7/subtitle_human_review.csv`: planilha para conferir as palavras e tempos de cada linha;
- `subtitle_review_s7/LEIA_ANTES_DE_REVISAR.txt`: contrato da aprovação;
- `SECOND_CURATION_*zip/subtitles/subtitle_review_s7.json`: propagação para a segunda curadoria;
- `social_output.stories[*].caption_plan`: `requested_preset`, `effective_preset`, `word_highlight_enabled`, `per_clip_review_required`.

Se karaokê é solicitado, mas os timestamps **e o texto** não foram verificados (`alignment_verified` e `audio_verified` em cada palavra), o preset efetivo é **simple** para evitar animação palavra a palavra falsa. Configurar `karaoke` por si só não habilita esse modo. Não há alinhador forçado autônomo neste release. O SRT por frases continua sujeito à revisão humana final. O arquivo SRT revisado é um artefato separado; o Curator/render final ainda precisa consumi-lo e validar o preview manualmente.

## Auditoria offline no Windows sem reexecutar a análise

Na pasta do projeto e com `.venv` ativo:

```powershell
.venv\Scripts\python.exe scripts\dev\audit_subtitles_s7.py "C:\analises\EMERSON_CLOVIS" --output "C:\analises\s7_review"
```

Funciona também com um ZIP que contenha `words.json`, `main_moments.json` (ou catálogo equivalente) e `editorial_shortlist` ou os IDs explícitos:

```powershell
.venv\Scripts\python.exe scripts\dev\audit_subtitles_s7.py "C:\analises\run.zip" --output "C:\analises\s7_review" --candidate-id MOMENT_00001
```

Uma vez conferido o áudio original e preenchidas **todas** as linhas do CSV (`verified_text`, `verified_start`, `verified_end`, `reviewer`, `audio_listened=YES`, `decision=APPROVED`):

```powershell
.venv\Scripts\python.exe scripts\dev\audit_subtitles_s7.py --output "C:\analises\s7_review\aprovados" --review-dir "C:\analises\s7_review" --apply-reviewed-csv "C:\analises\s7_review\subtitle_human_review.csv"
```

O importador valida timestamps monotônicos e confinados ao corte, ausência de linhas faltantes, duas linhas legíveis e assinatura de escuta; gera `.human_reviewed.srt` e `REVIEW_PROVENANCE.json`. A conferência da escuta é declarada pelo revisor, não verificada por IA. **Não marca vídeo pronto para publicação, não substitui o transcript canônico e não liga karaokê.**

## Testes

- Regressão integral Linux/Python 3.13: **555 aprovados, 2 ignorados**.
- Testes S7: revisão da taxa original, shortlist vazia, hooks/punchlines, orçamento, overlap, risada, interrupção, preservação do texto, anulação de karaoke não verificado, CSV injetado, geração SRT, pasta/ZIP e aprovação manual.
- Sintaxe Python 3.11 conferida via `ast.parse(feature_version=(3, 11))`.
- Pendências: homologação real Windows 3.11, execução original Emerson, validação visual de legendas, escuta humana, alinhamento word-level externo e benchmark contra transcrição de referência anotada.
