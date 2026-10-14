# R5 — relações textuais provisórias e contrato de estrutura

Alterados somente `src/ldporto/understanding.py`, novo `src/ldporto/narrative_relations.py` e novo `src/tests/test_r5_narrative_relations.py`. Nenhuma execução de modelo, GPU, serviço ou pipeline completo. Nenhum artefato histórico foi regravado.

## APIs para integração

`build_question_answer_links(segments, questions, topics=None, sections=None, entities=None, cfg=None)` devolve uma lista independente do QA canônico. Cada registro contém `link_id`, `question_id`, `question_segment_ids`, `answer_segment_ids`, `question_interval`, `answer_interval`, `association_type`, `evidence_status`, `rationale`, `alternatives`, `uncertainties`, `requires_review=True`, `confirmed=False`, `causality_confirmed=False` e `changes_canonical_qa=False`. Sem proposta elegível, a pergunta canônica tem `association_type='unresolved'`, `answer_segment_ids=[]` e `answer_interval=None`. Perguntas inválidas/IDs duplicados não criam referências inventadas. Perguntas de confirmação genérica (`tag_question`) continuam sem resposta esperada; perguntas retóricas recebem apenas propostas de contexto, quando há marcador explicativo compatível.

O limite padrão é 256 segmentos posteriores/600 segundos e quatro propostas por pergunta, configurável pelos campos `max_search_segments`, `max_search_seconds`, `max_proposals_per_question`. Esses limites pertencem somente à nova coleção de propostas: o QA existente e seus gates de 32 segmentos/125 segundos permanecem intactos. Propostas tardias, após mudança literal de assunto ou entre seções exigem referência explícita à pergunta e duas âncoras literais. Semelhança lexical isolada não produz vínculo. Duas perguntas compatíveis ou respostas polares divergentes ficam como alternativas/incertezas, sem escolha automática. Resposta no mesmo segmento usa offsets literais do texto e os tempos integrais do segmento, com incerteza explícita sobre tempos das palavras.

`build_arc_context_links(segments, arcs, topics=None, sections=None, entities=None, cfg=None)` propõe retomadas posteriores explícitas do mesmo narrador com pelo menos duas âncoras. Campos de integração: `source_arc_id` (evento anterior), `target_arc_id` (arco posterior contendo a retomada, ou `None`), `evidence_segment_ids`, `relation='references_previous_event'`, `evidence_status='proposed_context_link'`, `requires_review=True`. O alvo posterior referencia o evento anterior. Arcos amplos que já contêm o evento anterior não são usados como alvo independente. Os campos `extends_canonical_arc=False` e `promotes_narrative_support=False` impedem interpretar a proposta como ampliação ou completude narrativa. Limites padrão: 256 segmentos/600 segundos e duas propostas por arco (`max_proposals_per_arc`).

As duas APIs reutilizam normalização lexical, marcadores tipados e propagação de incerteza da transcrição existentes. Validam também os intervalos dos segmentos omitidos entre referências canônicas, evitando saltar bloqueadores temporais. Entidades ou nomes de seções não provam identidade do evento nem causalidade.

## Correção de estrutura

No produtor de arcos, `development` passa a conter somente segmentos do narrador depois do fim do setup e antes do início do payoff, quando existente. Isso remove desenvolvimento atribuído a trechos anteriores ao setup. IDs dos arcos e gates permanecem preservados; a utilidade legada de `qa_arc` continua calculada como antes.

`narrative_structure` passa a refletir os componentes efetivos. `section_layout` preserva a descrição posicional do início/meio/fim do tópico. `structure_contract` declara `narrative_structure_basis='canonical_component_ids'`, `section_layout_basis='source_position_only'` e `section_layout_is_narrative_evidence=False`. Uma discussão com meio posicional não passa a ter desenvolvimento narrativo.

## Evidência executada

Foco final: **121 passed em 6,75 s, exit 0**. São 23 canários novos sintéticos e 98 testes existentes. Comando, hashes e duração real registrados em `narrative_focus_03.json`; stdout e JUnit no mesmo prefixo. Focos anteriores aprovados permanecem registrados. Três achados de revisão independente receberam correções e canários: mudança de assunto sem referência explícita, bloqueador temporal entre refs descontínuas e alvo de retomada que também contém o evento anterior.

```powershell
.venv/Scripts/python.exe -B -m pytest -q src/tests/test_r5_narrative_relations.py src/tests/test_stage09_story_arcs.py src/tests/test_understanding_session1.py src/tests/test_v44_semantic_story.py src/tests/test_sol_v4_post_dialogue.py src/tests/test_stage07_qa_audit.py src/tests/test_qa_reference_handoff.py --junitxml=docs/reports/r5_20261014/narrative_focus_03.junit.xml
```

Nenhum resultado sintético é prova de recall ou acurácia do vídeo VARIG. Replay real, grafo/unidades/export, fingerprints de pipeline e regressão integrada são responsabilidade da raiz; resultados reais ainda precisam de revisão humana.

```text
understanding.py eaa02900285664d52d91dc60b8f759f324380c2b804c0b93732596cd773abcf5
narrative_relations.py 9ab819c90f56b184c5f320567c540b7d9556441244e79f4c2fe611d0cbcea850
test_r5_narrative_relations.py 47ef7c7d4a225dd6a62a7e9601e96885cf1b5cbb40345b25f7a05420ca1a09cf
```
