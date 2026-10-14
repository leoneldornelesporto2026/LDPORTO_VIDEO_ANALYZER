# Compreensão de diálogo e suporte narrativo — replay CPU

Fontes preservados: `src/ldporto/understanding.py` e novo `src/tests/test_sol_v4_post_dialogue.py`. Nenhum modelo, prompt, orçamento, mídia, checkpoint original ou limiar alterado. Os textos dos canários são sintéticos; não constituem anotações do vídeo.

`recover_dialogue_links(transcript, records, topics=None)` retorna `(questions_answers, dialogue_diagnostics)`. O argumento `transcript` contém `segments` canônicos; `records` e `topics` são as coleções semânticas existentes. A função preserva `question_id`, `stable_question_id`, registros já ligados e perguntas sem resposta esperada. As pontes exigem contexto literal do mesmo perguntador com duas âncoras lexicais ou reação reconhecida, propriedade de fala conhecida e intervalos não sobrepostos. A associação subsequente reutiliza os gates existentes de `semantic.questions_answers`. Vínculos novos são candidatos com revisão obrigatória, sem validação humana ou audiovisual.

A busca usa um prefixo contíguo e mantém os limites originais de 32 segmentos e 125 segundos: não salta fala longa, intervalo inválido, pergunta nova ou mudança de assunto. Uma confirmação polar não é descartada para atribuir resposta a terceiro falante. Um fim artificial por limite/intervalo inválido não autoriza `question_answer_complete`.

`run_understanding` devolve `questions_answers`, `question_candidates`, `question_answer_pairs`, `question_diagnostics`, `qa_metrics` e `dialogue_diagnostics` reconciliados. O checkpoint semântico anterior permanece intacto. O consumidor deve preferir esse contrato inteiro, preservando fallback para caches legados.

O suporte narrativo registra referências e ausência real de setup/development/payoff. Componentes com texto/tempo incompatíveis com os segmentos canônicos são removidos. Texto vazio, intervalos sobrepostos ou componentes invertidos não sustentam narrativa; `narrative_supported=True` é retirado quando falta suporte em qualquer tipo de arco. Componentes legados somente com IDs preservam seu formato canônico, com diagnóstico de conteúdo/tempo indisponível; isso não inventa evidência.

## Validação executada

Comando de foco final, registrado em `dialogue_focus_03.json`, com stdout e JUnit correspondentes:

```powershell
.venv/Scripts/python.exe -B -m pytest -q src/tests/test_sol_v4_post_dialogue.py src/tests/test_stage09_story_arcs.py src/tests/test_understanding_session1.py src/tests/test_v44_semantic_story.py src/tests/test_stage07_qa_audit.py src/tests/test_qa_reference_handoff.py --junitxml=docs/reports/sol_v4_pos_foquinha_20261013/dialogue_focus_03.junit.xml
```

Resultado: **98 passed em 5,21 s**, exit 0; 26 canários novos e 72 testes existentes. Os focos anteriores passaram e permanecem registrados; o último inclui as correções da revisão independente.

Replay somente de dados reais: `dialogue_real_cpu_replay_02.json`. Foram lidos `transcript_segments.json`, `questions_answers.json`, `topics.json` e `story_arcs.json` originais. Não houve áudio, inferência ou chamada a serviço.

- Q&A preservado integralmente: **98 unresolved, 181 not_expected e 1 linked_candidate**. Nenhum ganho de recall/precisão está demonstrado. As cinco pontes elegíveis mantiveram abstenção por relevância/pergunta nova. Três registros tinham owner ausente, sem divergência de texto/tempo canônico.
- As 98 abstenções originais: 42 intervention_relevance_unresolved, 23 new_question_before_answer, 18 answer_relevance_unresolved, 15 missing_speaker_evidence. O produtor semântico já busca o transcript inteiro; os 23 chunks não são barreiras dessa busca.
- Arcos preservados: **100 arcos e 0 narrativas sustentadas**. Diagnóstico: 100 no_payoff, 62 no_setup, 62 no_development, 3 cross_chunk_continuity_unresolved, 6 missing_speaker_evidence. Há 21 inversões da ordem temporal dos componentes atribuídos aos arcos; isso não demonstra sobreposição dos intervalos do transcript.
- IDs de Q&A, payloads de Q&A e entradas de replay permaneceram iguais. Amostra manual de 16 itens está marcada `unreviewed`; `verified_complete_qa_count=None` e `human_accuracy_measured=False`.

Pendências: escuta/anotação humana da amostra para medir acurácia e estabelecer respostas/desfechos reais; replay integrado/export e regressão completa são conduzidos pela raiz. Nenhum positivo sintético é apresentado como melhoria confirmada neste vídeo.

SHA-256 no foco final:

```text
understanding.py c2872463eb5234310a9777ad7862fc24519b93e15f7933d1a23abdcc1371f33b
test_sol_v4_post_dialogue.py 6261dc56ce6b4fb064c08ec007ef86b0787264a760c84428979d7fec33045588
```
