# Stories e narrativas — escopos e lacunas reais

Auditoria somente leitura de 17/10/2026 sobre o pacote canônico `SECOND_CURATION_READY_9UCGZia2p1k_20261016_200541_367803_f6b214.zip`, SHA256 `d090841905222237b282af8b25caa02aa8b2bfcb946baae1a6f4ae0f3ab3779c`.

O pacote tem **49 sequências provisórias, 86 unidades editoriais e um Story independente legado**. As unidades não são 86 Stories aprovados. O Story legado `STORY_001` corresponde a `MOMENT_00012_0003`, dura 55,2 s e continua REVIEW_REQUIRED com alinhamento de legenda pendente.

| Evidência narrativa | Quantidade |
|---|---:|
| Sequências `complete_supported=true` | 0 |
| `discussion_without_narrative` | 43 |
| `partial_supported` | 6 |
| Unidades de contexto | 71 |
| Unidades de setup | 6 |
| Unidades de desenvolvimento | 9 |
| Unidades de payoff | 0 |

Os 49 conjuntos mantêm ordem de apresentação na fonte, sem erros de ordenação detectados, e referem unidades existentes. Dezesseis registram divulgação obrigatória da montagem de intervalos; a ordem de apresentação não prova cronologia de eventos nem uma história completa. As unidades ficam abaixo de sessenta segundos, máximo 55,2 s. Nenhuma recebeu revisão humana, PREVIEW_APPROVED ou prontidão de publicação nesta auditoria.

O conjunto `SEQUENCE_f67d3f46c979d3ad` tem setup referenciado por `SEG_00156` em `[3070,57;3083,67)` e desenvolvimento por `SEG_00158..SEG_00161` em `[3085,61;3092,84)`. O próprio contrato marca falta de payoff. Ele fornece uma proposta parcial rastreável para revisão; a incerteza da transcrição e a ausência de desfecho impedem certificá-lo como narrativa completa. Nenhuma identidade visual foi atribuída a nomes mencionados no texto.

Os rótulos legados de arcos — 43 `discussion_segment`, cinco `anecdote` e um `partial_story` — foram preservados como classificações da fonte. Eles não foram convertidos em aprovação narrativa. O JSON `STORIES_NARRATIVE_AUDIT_baseline.json` lista individualmente as 49 sequências, seus intervalos, referências, suporte, bloqueios e componentes ausentes, além das 86 unidades originais.

Há 86 registros de sugestões de títulos por unidade. São excertos ASR literais, com incerteza e revisão obrigatória. Foram detectados três grupos de títulos repetidos, abrangendo dez unidades (grupos de cinco, três e duas). Não foram inventadas alternativas nem alegações de viralidade para disfarçar repetições. Isso permanece pendência para a segunda curadoria; títulos das futuras partes precisam ser contextualizados e revisados.

Os futuros Visual Frame Handoffs de unidades/partes provisórias devem preservar `unit_id`, `sequence_id`, intervalos originais e vínculos, indicando seu caráter provisório. Exportar imagens, storyboard e geometria de uma unidade não a promove a Story final nem completa uma sequência.

Comando real:

```powershell
./.venv/Scripts/python.exe docs/reports/r6_20261016/R6_2_FINAL_HANDOFF/audit_caption_narrative.py --package pacotes_para_enviar/SECOND_CURATION_READY_9UCGZia2p1k_20261016_200541_367803_f6b214.zip --label baseline
```

Resultado: referências e intervalos válidos; zero narrativas promovidas, instrumentos inventados, associações de identidade novas ou aprovações. Estado final desta auditoria: **PARTIAL / REVIEW_REQUIRED**. O cotejo da revisão editorial derivada será acrescentado quando seu pacote final for testado.
