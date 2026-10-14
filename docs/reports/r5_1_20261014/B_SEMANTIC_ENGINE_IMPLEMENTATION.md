# Checkpoint B — implementação do motor semântico

Implementação aditiva em `src/ldporto/semantic_narrative.py`. O módulo recebe os
JSONs preservados do pacote e um callback de inferência; não lê mídia, não abre
cliente Ollama e não altera arquivos originais, QA canônico, scores ou gates.

API: `build_semantic_analysis(legacy, infer, *, cfg=None)` retorna mapa de caminho
para payload derivado. O callback `infer(task_id, context, schema)` retorna
`(payload, model_provenance)`. Contexto contém `instruction`, `data` e
`prompt_version`. `task_schema` expõe os schemas Draft 2020-12 reais de inferência.

Fases implementadas: mapa global hierárquico; recuperação incremental IDF e
vizinhos canônicos nos dois sentidos; relações entre arcos; propostas de QA;
completude conforme o tipo de conteúdo; séries variáveis de 1–7 Stories. A
homologação padrão investiga Q_0015 e até dois tópicos; perguntas não selecionadas
permanecem `UNRESOLVED` e `NOT_EVALUATED`. `qa_question_ids=None` permite investigar
todas. Cada etapa registra falha/abstenção própria, sem fabricar fallback.

IDs, citações literais, associação a arcos/units, intervalos e duração da fonte
são verificados. Tempos são reconstruídos exclusivamente dos segmentos
canônicos. Dependências futuras/circulares, repetição integral de fonte,
orçamento de duração e exclusão comercial registrada rejeitam a proposta de
série. Causa exige marcador causal explícito e rejeita evidência contrafactual.
Completude de explicação exige questão, explicação e resultado; não exige clímax.

`source_claim_issues` oferece bloqueios conservadores para números sem suporte,
negação sem fonte, nomes explicitamente fornecidos ausentes e promoção de
contrafactual a causa factual. Essas verificações **não provam entailment**.
O estado exportado é `SOURCE_QUOTES_VALIDATED_SEMANTIC_REVIEW_REQUIRED`; aprovação
humana, certificação de completude, preview e publicação continuam falsos.

Verificação real executada com o Python da `.venv`:

```text
.venv/Scripts/python.exe -m pytest src/tests/test_r51_semantic_narrative.py src/tests/test_r5_narrative_relations.py src/tests/test_r5_narrative_handoff.py -q --junitxml=docs/reports/r5_1_20261014/B_SEMANTIC_ENGINE_TESTS.xml
112 passed in 0.35s
```

São 40 casos B e 72 casos legados de relações/handoff. O JUnit e o JSON de
evidência adjacentes registram contagens e SHA-256. Os testes usam callbacks
sintéticos deliberadamente: comprovam contratos e bloqueios, não qualidade
semântica do vídeo real. A inferência local real e sua revisão de transcrição
pertencem ao replay/homologação registrado separadamente pelo responsável pela
execução. Nenhum Ollama foi invocado por este agente.

O fonte B foi congelado após os bloqueios acima e a inclusão de nós ANSWER e
arestas de QA no grafo derivado, antes da inferência real. Somente testes e
documentação foram ampliados depois do aviso de congelamento ao coordenador.

Limitações: sustentação semântica de paráfrases precisa de revisão editorial;
ASR, áudio, identidade e causalidade histórica não foram validados humanamente.
Homologação com voz/vídeo e safe areas continua no Windows/Curator, sem novas
análises audiovisuais neste motor.

## Revisão independente do runner/exportador

Após o início da inferência real pelo coordenador, os fontes B permaneceram
congelados. A leitura de `semantic_replay.py`, `semantic_package.py`,
`semantic_runtime.py` e da assinatura do validador C identificou dois problemas
funcionais comunicados ao responsável pelos respectivos arquivos:

- O manifesto inicial do replay era persistido apenas ao fim de B; uma
  interrupção durante a primeira tarefa deixaria cache/ledger num diretório sem
  `semantic_state.json`, recusado pela próxima execução. Solução indicada:
  persistir o estado inicial validado antes da inferência.
- O exportador passava somente o JSON visual a
  `validate_story_visual_handoff`, cuja API recebe o mapa completo de artefatos.
  Solução indicada: fornecer o mapa com visual, títulos e schema.

Também foram indicados reforços de consumidor para correspondência exata entre
intervalos e segmentos, gates comerciais, segurança dos caminhos de leitura e
separação entre validade estrutural e ausência total de propostas. A revisão
inicial foi somente leitura. Em seguida, o coordenador autorizou este agente a
corrigir exclusivamente `semantic_package.py` e seus testes, sem modificar o
motor B nem o runtime em uso pela inferência real.

Correções efetivamente feitas no consumidor/exportador:

- API C recebe o mapa completo de visual, títulos e schema.
- `source_intervals` precisa corresponder exatamente aos IDs e tempos canônicos;
  alinhamentos de palavras e destaques continuam com validação própria de subspan.
- Exclusão comercial registrada na unit é conferida independentemente.
- Handoff semântico valida pelo schema completo Draft 2020-12, confere origem,
  arquivos referenciados e JSON pointers.
- Exportação inclui o schema semântico; verificação independente inclui também
  completude visual e proveniência de compatibilidade.

```text
.venv/Scripts/python.exe -m pytest src/tests/test_r51_semantic_package.py src/tests/test_r51_story_visual_handoff.py src/tests/test_r51_semantic_narrative.py -q --junitxml=docs/reports/r5_1_20261014/B_PACKAGE_CONSUMER_TESTS.xml
125 passed in 2.94s
```

O JUnit e `B_PACKAGE_CONSUMER_TESTS.json` registram o comando, contagens e hashes.
O fonte do consumidor foi então congelado e devolvido ao coordenador para a
exportação. A correção de bootstrap/retomada do runner permaneceu com o
coordenador e não foi executada por este agente.

## Reparo do consumidor após evidência real de acrônimo externo

Em nova tarefa dirigida pelo coordenador, foi examinada somente a resposta QA15
em cache. Ela incluía expansão inglesa de ADF ausente da transcrição canônica e
citava GPS e Tucuruí sem incluir os segmentos correspondentes na evidência
selecionada. O cache original foi preservado; o motor B e runtime permaneceram
congelados.

O consumidor passou a bloquear, em `summary`/`reasoning_summary` com IDs de fonte,
siglas maiúsculas ausentes, termos capitalizados parentéticos sem suporte e
nomes capitalizados fora do início de frase ausentes dos segmentos citados.
Palavras de ligação e início de frase são tratadas prudentemente para reduzir
falsos bloqueios. Essa regra não prova a verdade de paráfrases em minúsculas.

Seis testes novos comprovam rejeição de expansão externa (inclusive em minúsculas), sigla sem citação e
nome sem fonte, além de aceitação quando a expansão/nome realmente consta na
evidência local. A última suíte acima inclui também testes C adicionados em
paralelo pelo responsável por C; não representa apenas casos deste agente.

Uma validação offline dos artefatos reais, após a primeira tentativa de reparo
QA, encontrou 11 bloqueios correspondentes a esses termos nas propostas e suas
arestas duplicadas. Encontrou também GPS no resumo de uma relação cujos IDs não
incluíam a fala sobre GPS. Os achados foram comunicados ao coordenador para
reparo dirigido ou abstenção; nenhum resultado foi aceito à força.
