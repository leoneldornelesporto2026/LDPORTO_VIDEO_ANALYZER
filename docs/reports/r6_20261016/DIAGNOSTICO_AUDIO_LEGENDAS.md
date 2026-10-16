# Diagnóstico de áudio e legendas R6 — 2026-10-16

Auditoria do código atual e regressão sintética offline. Nenhum pipeline, modelo, GPU, Ollama, escuta real ou mídia local foi executado neste trabalho. Os números do show apresentados no pedido são evidências anteriores, não resultados da execução dos fontes R6.

## Causa concreta

1. `pipeline.py`, etapa `17e_subtitle_review_s7`, entrega `editorial_shortlist` como `selected_ids`. `subtitle_review.review_selected_clips` respeita a seleção explícita; lista vazia significa nenhum corte. A revisão S7 detalhada ficar restrita à shortlist resulta desse contrato, não de uma falha de ASR no export.
2. `second_curation._candidate_source` inclui os candidatos principais e seus alternates. `build_core_package` preserva esse catálogo inteiro, mesmo com shortlist pequena. Antes desta mudança, o export somente copiava `subtitles/subtitle_review_s7.json`; não criava uma triagem de legendas para os demais intervalos.
3. A transcrição literal de um candidato sem palavras usa texto de segmentos canônicos. O SRT integral igualmente preserva segmentos completos; isso pode produzir texto extenso sem evidência granular de palavras. É um fallback documental existente, não alinhamento palavra a palavra.
4. O Curator real adjacente contém a mensagem reportada em `ldporto_curator/subtitles.py`, linha 235 na leitura desta sessão. Seu render tenta `_collect_aligned_words`; quando não consegue, testa o encaixe do texto completo com `_fitted_text`. Se o texto não cabe, levanta `Legenda longa sem alinhamento confiável`. O erro ocorre tarde porque o catálogo anterior não indicava esse risco por corte antes da renderização.
5. O export antigo de `relevant_words.jsonl` também omitia `alignment_verified`, `audio_verified`, `timestamp_repaired`, `speech_overlap` e `suspected_hallucination`. Agora preserva esses campos quando presentes. Isso mantém evidências para consumidores conservadores; não significa que o renderizador instalado já valide todos esses campos.

`targeted_asr.run_on_demand_review` já exige fila humana explícita, opt-in e SHA256 esperado. A revisão acústica global existente é um dossiê separado. Nenhum desses mecanismos foi substituído ou ampliado para executar reconhecimento automático sobre todos os candidatos.

## Correção incremental

`subtitle_review.build_caption_preflight` reaproveita o agrupador e os diagnósticos S7, sem alterar `review_selected_clips`, seu CSV, SRT ou gates de aprovação. O export gera `subtitles/caption_preflight_r6.json` para todos os candidatos realmente presentes no catálogo, inclusive alternates, e para cada Story preservado pelo gate editorial. Stories são avaliados com os próprios limites.

O relatório registra IDs canônicos, intervalos, quantidade de palavras, evidência temporal em segundos, lacunas sem timestamp por palavra, segmentos longos sem alinhamento, categorias de áudio observadas, motivos e modo permitido. As lacunas significam falta de evidência de palavras, não silêncio ou fala ausente comprovados. O texto não é corrigido e não recebe timestamps interpolados.

`build_story_interval_preflight` acrescenta triagem por intervalo de origem para séries semânticas. `export_semantic_package` gera `subtitles/semantic_caption_preflight_r6.json`, reaproveitando IDs de Stories existentes. Cada parte mantém `source_intervals` e uma lista `interval_reviews`; o agregado usa `start=null/end=null`, sem inventar uma janela contínua que inclua os espaços entre intervalos. Palavras nesses espaços não entram no dossiê da montagem. Mesmo se todos os intervalos tiverem evidência granular verificada, o agregado de vários intervalos continua exigindo revisão das transições. Intervalos sobrepostos, reordenados, ausentes ou soma superior a 60 segundos são bloqueados. A política de confiança e agrupamento do pacote de origem é preservada.

| Estado | Significado operacional |
| --- | --- |
| `CAPTION_READY` | Palavras com alinhamento e escuta sinalizados na evidência, conteúdo compatível, limites válidos e gate granular satisfeito; ainda requer revisão do artefato final. |
| `PHRASE_SUBTITLE_ONLY` | Evidência de escuta nas palavras, mas alinhamento granular não verificado; somente modo por frase. |
| `INSTRUMENTAL_NO_CAPTION` | Observação explicitamente instrumental cobre todo o intervalo, sem texto/palavras ou categoria conflitante. Ausência de palavras ou rótulo genérico `music` nunca basta. |
| `ALIGNMENT_REVIEW_REQUIRED` | Segmento longo não representado por palavras alinhadas, limites atravessando palavras, sobreposição ou outro problema temporal crítico. |
| `AUDIO_REVIEW_REQUIRED` | Texto disponível, mas escuta/confiança insuficientes, canto, coro, sobreposição ou classificação incerta. |
| `BLOCKED` | Intervalo inválido/fora da fonte, texto indisponível ou bloco que viola limites textuais sem truncamento. |

As políticas padrão continuam em 5 palavras, 38 caracteres, 2,8 segundos, intervalo de 0,45 segundo e confiança 0,60; não houve redução de thresholds. A configuração usada fica no relatório. A comparação de texto canônico e palavras é conservadora e não completa palavras ausentes por contexto. Classificação musical permanece indisponível quando faltam observações explícitas.

Todos os estados mantêm `human_approved=false`, `subtitle_publish_ready=false`, `publication_ready=false` e `review_required=true`. `CAPTION_READY` descreve evidência disponível; não equivale a aprovação de SRT, preview ou publicação. A revisão S7 legada continua exportada sem ser inflada artificialmente.

## Verificação executada

Comando final, execução real em Windows:

```powershell
.venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider src/tests/test_r6_caption_handoff.py src/tests/test_v43_handoff.py src/tests/test_v44_second_curation.py src/tests/test_s7_subtitle_review.py src/tests/test_stage21_subtitle_alignment.py src/tests/test_v44_targeted_asr.py
```

Resultado: **70 passed in 14.14s**. Inclui seis estados, instrumento não inferido de música genérica, áudio misto explícito, token longo, alinhamento parcial insuficiente, limites próprios de Stories, alternates fora da shortlist, preservação de S7/transcrição e rejeição de preflight adulterado, candidato omitido, hash falso e gate de publicação alterado. As regressões existentes de export/visuais usam fixtures sintéticas; não houve leitura das mídias do usuário.

A primeira execução registrou `1 failed, 54 passed`: a fixture nova de S7 omitia `selected_candidate_count` e acionou corretamente `subtitle_review_count_disagreement`, esvaziando a shortlist. A fixture foi corrigida para representar o contrato existente; o gate não foi afrouxado. Rodadas intermediárias passaram 26, 67 e 69 testes. A revisão independente também localizou descarte indevido de `MIXED_AUDIO` e câmera ausente em Stories de snapshots antigos; ambos receberam correção e regressão.

Uma rodada adicional com `test_r51_semantic_package.py`, `test_r6_caption_handoff.py`, `test_v43_handoff.py` e `test_v44_second_curation.py` terminou em **62 passed in 15.04s** após corrigir a renovação do master na derivação semântica. O preflight é rederivado mesmo quando os hashes do master e do manifesto externo são atualizados por um adulterador; esses hashes por si sós não aprovam uma alegação falsa.

Após incluir a triagem de Stories semânticas, a verificação final reuniu os sete arquivos (os seis do primeiro comando mais `src/tests/test_r51_semantic_package.py`) e terminou em **109 passed in 16.21s**. Cobriu IDs e intervalos semânticos reais das fixtures, exclusão de palavras entre intervalos, transições humanas e preservação byte a byte do master pai na derivação.

O comando `.venv/Scripts/python.exe -B docs/reports/r6_20261016/verify_caption_curator.py` passou com pacote temporário sintético de três candidatos e os importadores reais instalados. Evidência: `caption_curator_import_r6.json`. Não executou render nem modelos; os hashes dos quatro módulos Curator observados permaneceram iguais.

## Homologação pendente

Escuta de fala/canto, identificação instrumental, sincronismo perceptual, fonte real do show, fidelidade de transcrição, tipografia medida e preview final continuam pendentes. O Curator instalado aceita os campos R6 adicionais, mas ainda não consome nem aplica automaticamente o novo preflight, incluindo a revisão de transições semânticas. Nenhuma melhoria de cobertura/precisão do show foi alegada a partir das fixtures.
