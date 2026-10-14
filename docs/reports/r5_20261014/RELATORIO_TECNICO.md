# Analyzer R5 — Narrative Intelligence & Second Curation Handoff

Decisão: **SECOND_CURATION_PARTIAL**. Integridade final: **VERIFIED**. O replay real foi executado em CPU sobre os dados persistidos do vídeo VARIG; nenhuma inferência audiovisual, chamada Qwen, renderização ou publicação nova.

## A. Diagnóstico e causas confirmadas

O [baseline](../../audits/ANALYZER_R5_BASELINE.md) foi escrito antes da implementação. Os 485 fontes da V4.1 estavam intactos. A análise possui 621 arquivos, 383 segmentos, 34 perguntas e 50 arcos. [data_diagnostic.json](data_diagnostic.json) registra caminhos, hashes e exemplos.

46 itens no catálogo são 45 principais avaliados em S3 e 1 alternativa preservada (MOMENT_00001_0000 → MOMENT_00001_0001); não houve perda. A shortlist zero decorre dos gates registrados, incluindo hook/clareza não medidos, contexto, limites, QA e evidência comercial insuficiente. Nenhum threshold foi reduzido.

Frequências dos principais motivos registrados nos candidatos: automatic_shortlist_gate_not_passed: 46; ineligible_by_quality_gate: 45; missing_required_score:hook: 35; missing_required_score:standalone_clarity: 35; below_editorial_quality_floor: 31; commercial_review_pending: 30; outside_target_duration: 26; story_payoff_not_grounded: 20.

28 discussões tinham IDs de miolo da seção em narrative_structure.development, mas nenhum desenvolvimento narrativo validado. Isso era diferença de escopo, não prova de 28 histórias completas. Outro problema real afetava oito arcos: o desenvolvimento podia anteceder/incluir o setup.

Na classificação comercial, “20 mil pés” gerava price e “9 vezes a força da gravidade” gerava installment. A busca QA aceitava todos os segmentos e perguntas, mas não reconhecia duas autorrespostas locais muito específicas. As demais abstenções não provam ausência de resposta semântica.

## B. Alterações e contratos

O desenvolvimento canônico agora fica após o setup e respeita o narrador e o payoff. section_layout guarda posições da seção; structure_contract 1.0 declara que layout não é evidência narrativa. narrative_structure deriva dos componentes canônicos. Os arquivos originais permanecem intactos, e o contrato derivado explicita essa migração de significado.

Foi criado um handoff narrativo 1.0, com schema, grafo, unidades, propostas QA, agrupamentos, títulos, plano ASR, diagnósticos e auditoria independente. O grafo separa ordem de apresentação e cronologia dos fatos; nenhuma aresta lexical vira causalidade. Duas referências de entidade entre seções são recuperação de contexto, sujeitas a revisão, sem afirmar continuidade do mesmo evento.

O fluxo normal de relatórios habilita R5 quando há SHA-256 canônico; fontes legadas sem hash válido continuam no contrato anterior, com motivo de indisponibilidade R5. Exportação direta mantém opção explícita. Cache/fingerprints incluem módulos e schema novos. O VIDEO CURATOR não foi modificado.

## C. Antes e depois no vídeo real

| Medida | Antes | Depois |
|---|---:|---:|
| Arcos | 50 | 50 |
| Arcos completos sustentados | 0 | 0 |
| Conflitos temporais nos componentes | 8 | 0 |
| QA canônico unresolved / not_expected | 29 / 5 | 29 / 5, preservados |
| Propostas novas de autorresposta | 0 | 2, não confirmadas |
| Unidades para revisão | 0 no contrato R5 | 117 |
| Agrupamentos provisórios | 0 no contrato R5 | 50 |
| Sementes literais de títulos | 0 | 178 |
| Candidatos standalone / shortlist | 46 / 0 | 46 / 0 |
| Novas inferências | — | 0 |

O QA derivado possui 27 casos ainda sem proposta para perguntas esperadas e duas propostas de autorresposta. Não foram convertidos em respostas canônicas resolvidas: Q_0000 liga SEG_00003 (“Como a gente lê?”) a SEG_00004 (“270.”), exigindo também SEG_00002 (“número 0270”). Q_0004 liga SEG_00013 à confirmação “Sim, a gente contou…” de SEG_00014. Não houve observação de tela nem escuta para confirmar esses vínculos. [Diagnóstico QA e exemplos](varig_qa_abstention_focus.md).

Os tipos dos arcos continuam 28 discussion_segment, 14 anecdote e 8 partial_story; os 50 não ganharam payoff artificialmente. A limitação de compreensão semântica global continua explícita: explicações plausíveis sem os vínculos estritos, como Q_0015, ainda exigem inspeção ou um resolver semântico mais amplo. Não se mediu precisão/recall humano.

## D. Unidades, sequências e câmera

As 117 unidades preservam texto, IDs, intervalos separados, função/escopo, contexto, falantes acústicos e vínculos com os 46 candidatos. Unidades de contexto podem entrar na curadoria de uma sequência mesmo sem passar pelo gate de Reel. PROVISIONAL_REVIEW_READY significa evidência disponível para inspeção, não autorização de distribuição.

Cobertura: 383 segmentos canônicos exportados; 317 participam das unidades. O grafo contém 208 nós e 203 arestas. Referências pendentes no pacote final: 0. Unidades não são uma alegação de cobertura narrativa integral do episódio.

Os 50 agrupamentos seguem arcos registrados e preservam dependências transitivas. São recortes de contexto/discussão ou narrativas parciais; **zero** agrupamentos foram certificados como história completa. Não são 50 Stories finais. O Curator precisa decidir limites, montagem e ordem. Intervalos distantes permanecem individualizados.

O diagnóstico visual existente registra LOW_AFFINITY, OFFSCREEN_SPEAKER, TRACK_FRAGMENTATION e problemas de sincronismo/consenso. Esses códigos não provam identidade ou defeito global de áudio/vídeo. Active speaker 0% e foco resolvido ~5,77% não foram artificialmente aumentados. Contagens do Director são janelas/decisões, não observação contínua. O fallback R5 é SOURCE_PRESERVE, sem crop, zoom ou movimentos novos. [Diagnósticos visuais reaproveitados](visual_diagnostics_reused.json).

## E. Títulos, comercial e ASR

Foram geradas 178 sementes **extrativas**, com offsets, segmentos e trechos literais. São insumos conservadores; não equivalem a títulos publicitários finalizados ou fatos confirmados por áudio. Há duas variantes quando o texto permite, sem completar frases ou anunciar causalidade, revelação ou viralidade inexistentes.

Exemplos rastreáveis:

- “Só que hoje a gente vai recontar essa história um pouco mais” / “Só que hoje a gente vai” — fonte `SEG_00016`, revisão obrigatória.
- “Antes da gente ir para o voo, a gente precisa dar o” / “Antes da gente ir para o” — fonte `SEG_00017`, revisão obrigatória.
- “Por exemplo, até aquela data, quando você precisava voar para leste, O” / “Por exemplo, até aquela data, quando” — fonte `SEG_00019`, revisão obrigatória.

O helper comercial distingue anúncio, patrocínio, CTA de compra, afiliado, discussão de produto, preço factual e site contextual, além de incerteza. Foram corrigidos os dois falsos padrões físicos, preservando anúncios reais e OCR. Os 30 casos históricos com cobertura comercial insuficiente continuam pendentes; os gates e scores históricos não foram reescritos. Direitos permanecem desconhecidos, separados de classificação comercial.

As 116 palavras sinalizadas e suas hipóteses originais foram preservadas. O plano direcionado propõe 4 regiões, 54.00s de áudio e 5 palavras sinalizadas, dentro do orçamento de quatro regiões/60s. Prioriza contexto narrativo, perguntas, números e entidades mesmo quando a shortlist está vazia. **Nenhum reparo ASR foi executado.**

## F. Compatibilidade e handoff

Os contratos legados de candidatos, scores, gates, fila 1.2 e Stories independentes foram preservados. social/stories_candidates.json e social/title_suggestions.json continuam no escopo legado e podem permanecer vazios. As sequências e títulos R5 estão em editorial/story_sequence_candidates.json e social/narrative_title_suggestions.json, referenciados explicitamente no novo handoff, manifestos e README. Isso evita apresentar unidades dependentes como Stories independentes aprovados.

Os arquivos derivados story_arcs, catalog, selection_report, stories_manifest, índice, brief e manifesto carregam informações compatíveis e escopos explícitos. Referência resolvida é diferente de narrativa completa; preview técnico é diferente de aprovação. Todos os estados de revisão, preview e publicação permanecem separados.

## G. Testes e validação

Foco de integração final: **132 aprovados**. Regressão completa: **2078 aprovados, 3 skips, 0 falhas, 0 erros**, em 358.57s. Baseline: 1.972 aprovados/3 skips. Todos os 1975 casos anteriores foram preservados; 106 casos foram adicionados.

Cobertura: narrativas contínuas e entre seções; respostas imediatas/tardias, interrupção, retórica, parcialidade, perguntas concorrentes e contradição; discussão sem arco; múltiplos speakers/identidade desconhecida; dependência de contexto; títulos sem suporte; publicidade versus contexto físico; fonte sem vídeo; cache/retomada após falha; manifesto/referências quebradas; perda de referência do Planner; ciclos; timestamps booleanos; zero Stories justificado e compatibilidade legada. Testes sintéticos não foram usados como homologação humana do vídeo.

As falhas intermediárias foram corrigidas sem afrouxar testes: timestamps bool, hook inventado, estados de revisão, fixture sem checkpoint, referência de teste em pacote sem unidades e SHA legado não canônico. A comparação real também bloqueou um pacote intermediário: o runner não havia carregado camera_plan.json, deixando 403 planner_ids sem resolução e derrubando elegibilidade humana. A correção reutiliza o Planner persistido e valida referências antes da exportação; não altera o gate. Um teste novo cobre a perda de Planner em snapshot compacto. Os logs e o pacote bloqueado permanecem preservados. [Foco](focused_release_02.log), [regressão final](release_full.json), [integridade](final_integrity.json).

## H. Execução e custo

Replay final: 41.00s; 28 entradas verificadas e 27 checkpoints reutilizados. ASR, diarização, YOLO, Active Speaker, OCR, Qwen e render não foram executados novamente. Os tempos históricos de Qwen pertencem ao processamento original e não foram apresentados como benchmark do código atual.

A nova API/CLI editorial calcula chave determinística dos dados, checkpoints, código, schema, configuração e evidência de testes. Retoma somente bundles com hash válido; saída anterior incompatível exige outra pasta. Targeted Repair permanece um plano de orçamento integrado ao mecanismo ASR existente; Full Processing continua no pipeline original e não é chamado automaticamente.

Repetição real do cache: {'cache_hit': True, 'actual_lookup_wall_seconds': 18.001032699947245, 'same_package': True, 'same_package_sha256': True, 'new_model_calls': 0, 'publication_ready': False}. O tempo de lookup é medido separadamente do tempo da primeira execução; não se declara uma nova execução dos modelos.

## I. Artefatos e preservação

- [ZIP final](release_replay/package/SECOND_CURATION_PARTIAL_zd_wjssZ7mc_20261014_140253_762578_0b9a68.zip) — 1,826,324 bytes, 124 arquivos com SHA-256 no manifesto, 125 membros incluindo o manifesto.
- SHA-256: `a84ede22de5fe91b8a5e1abe7044229534fe55943777d769364ff58842ab9807`.
- [Handoff](review_packet/SECOND_CURATION_NARRATIVE_HANDOFF.json), [HTML de revisão](review_packet/NARRATIVE_REVIEW.html), [auditoria](review_packet/CODEX_ANALYZER_REVIEW.md), [readiness](review_packet/STORY_READINESS_REPORT.json), [antes/depois](review_packet/NARRATIVE_BEFORE_AFTER.json).
- [Replay e proveniência](release_replay/replay_result.json), [schema](../../../schemas/narrative_handoff.schema.json), [baseline](../../audits/ANALYZER_R5_BASELINE.md).

Preservados: 621 arquivos originais (2,689,113,718 bytes), 27 checkpoints, ZIP original e três arquivos .package. Os 495 fontes congelados conferem com a versão testada. HEAD/branch permanecem iguais; não houve commit, instalação, download, exclusão ou acesso aos sete renders do Curator. A mídia local está presente e seu hash confere.

Fontes alterados nesta missão:
- `src/ldporto/build_provenance.py`
- `src/ldporto/editorial.py`
- `src/ldporto/pipeline.py`
- `src/ldporto/reports.py`
- `src/ldporto/second_curation_export.py`
- `src/ldporto/understanding.py`

Fontes/contratos adicionados:

- `docs/audits/ANALYZER_R5_BASELINE.md`
- `schemas/narrative_handoff.schema.json`
- `src/ldporto/commercial_context.py`
- `src/ldporto/narrative_handoff.py`
- `src/ldporto/narrative_relations.py`
- `src/ldporto/narrative_replay.py`
- `src/tests/test_r5_commercial_context.py`
- `src/tests/test_r5_narrative_handoff.py`
- `src/tests/test_r5_narrative_relations.py`
- `src/tests/test_r5_replay_export.py`

## J. Pendências e próximo passo

Abrir o HTML e revisar as duas autorrespostas com seus contextos, depois selecionar uma narrativa/explicação para validar começo e fechamento. Ouvir somente as regiões ASR propostas se forem editorialmente relevantes. Nenhum termo foi corrigido por fluidez textual.

O handoff é tecnicamente válido e parcial: ainda não comprova a reconstrução semântica global do episódio nem um payoff para os 50 arcos. É possível aprofundar relações e classificações por replay dos dados sem refazer percepção. Associação visual e sincronismo exigem inspeção/novas janelas específicas se forem necessários; isso não bloqueia revisão textual na câmera original. Contexto comercial, direitos, títulos, limites, preview e publicação precisam de decisões humanas separadas.

O próximo incremento semântico deve tratar explicações/autorrespostas sem marcadores explícitos, começando por Q_0015 e preservando a abstenção em negativas e contradições. Não há autorização automática de publicação nem necessidade de reprocessar o episódio inteiro.
