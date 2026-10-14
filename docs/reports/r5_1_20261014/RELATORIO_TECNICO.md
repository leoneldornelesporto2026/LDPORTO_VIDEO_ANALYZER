# R5.1 — relatório técnico

Estado: **SEMANTIC_HANDOFF_PARTIAL**. Integridade: **VERIFIED**. Implementação e pacote para revisão; homologação editorial integral ainda pendente.

## A — Base

HEAD inicial `3a301576064d9e34b8e4e3385bd7a0d8f61f3e4b`, branch `baseline/ldporto-20261012-prompt01`. Git inicialmente limpo na primeira etapa; na retomada preservaram-se todas as alterações parciais. Não houve reset, limpeza, commit, push, instalação ou download. O MASTER foi lido integralmente; o usuário confirmou o checkpoint persistido como continuidade.

## B — Limitações confirmadas

O sanitizador confundia `s:/` de HTTPS com drive Windows. Campos antigos `unresolved` e contexto pouco seletivo prejudicaram a resolução; propostas do Qwen também acrescentaram nomes/expansões sem citação e frases não literais. Esses resultados ficaram arquivados. Não foram convertidos em fatos por aumento de scores ou redução de gates.

## C — P0

Schemas exportados mantêm a URI Draft 2020-12 e são validados inteiros. Proveniência original versus replay classificada como **explained** pelos checkpoints; `build_mismatch=true`, as razões e o estágio20 permanecem preservados. Texto novo, replay CPU e inferência audiovisual histórica têm escopos distintos.

## D — Implementação

`semantic_narrative.py`: recuperação hierárquica, relações, QA, completude por tipo, séries e abstenções. `semantic_runtime.py`: cliente Ollama existente, limites, cache por contexto/prompt/schema/modelo/código, reparação JSON limitada e ledger. `semantic_replay.py`: fases separadas, manifests atômicos, revisões e reaproveitamento de propostas válidas. `semantic_package.py`: exportação aditiva e consumidor offline com schemas, hashes, referências e gates. `story_visual_handoff.py` e dois novos schemas: títulos, fala temporizada, destaques, sequência, capa, CTA e layout desconhecido. CLI: `analyze.py --semantic-replay`.

## E — Relações reais

Três propostas `CONTINUES`: STORY_0018→STORY_0031, STORY_0031→STORY_0032 e STORY_0018→STORY_0032. Citações e referências foram verificadas. Relações causais sem fala causal foram rejeitadas; continuidade semântica exige revisão. O grafo R5 de208 nós/203 arestas permanece intacto.

## F — QA

Q_0015 tem uma associação **ANSWER_PROPOSED**, com trechos de resposta referenciados e transcrição literal. Resumos abstrativos com fatos extras foram substituídos por excertos canônicos, com transformação e hashes registrados; isso não promove a associação a confirmação. O QA canônico não mudou:29 perguntas históricas permanecem unresolved. As outras33 entradas semânticas não foram avaliadas nesta homologação direcionada. O contrafactual tardio sobre “essa antena” requer contexto anterior e escuta; não fundamenta causalidade observada.

## G — Completude

Zero narrativas e zero explicações foram certificadas como completas. O modelo não entregou proposta de completude que passasse por todas as verificações. A revisão textual de126–132 identifica pergunta, mecanismo e fecho local; não equivale ao desfecho da história do acidente nem à revisão audiovisual.

## H — Série

Uma série com **um Story real**: SEG_00126–SEG_00132. São7 intervalos, união42,64s e janela44,80s. A proposta anterior válida foi reutilizada quando nova inferência se absteve; SHA e revalidação estão no pacote. A duração final depende da montagem no Curator. Nenhum Reel ou shortlist foi forçado.

## I — Story Visual Handoff

Um título principal e duas alternativas, hook, caption separado da fala, CTA, capa proposta, partes1/1,118 palavras com tempos originais e3 destaques. Os títulos finais são **rascunhos assistidos de autoria Codex**, não saídas Qwen aprovadas nem revisão humana. O script `draft_titles.py`, payload, hashes e proveniência estão salvos. As tentativas Qwen foram preservadas e recusadas pelos validadores. Duas paráfrases herdadas (posição/rota e disponibilidade geográfica do GPS) foram substituídas por texto da fonte, com registro das versões. Safe areas e regiões de rostos permanecem UNKNOWN; sem crop/zoom autorizado, MP4, ASS, SRT ou PNG novos.

# Resumo executivo de consumo

| Série / parte | Título principal | Alternativas | Função | Fonte (s absolutos) | Legenda | Destaques | Revisão | Artefato |
|---|---|---|---|---|---|---|---|---|
| SEM_SERIES_0ab8edbb24f957bd 1/1 | COMO O ADF VAI APONTAR A DIREÇÃO? | FREQUÊNCIAS DE RÁDIO: PARA ONDE VOAR? / O PILOTO E OS AUXÍLIOS DE RADIONAVEGAÇÃO | EXPLANATION | 709.46–714.72, 714.94–722.38, 722.48–730.92, 731.08–734.92, 735.12–739.66, 739.90–752.10, 753.34–754.26 | word | 3 | PROPOSED; revisão humana pendente | social/story_visual_handoff.json#SEM_STORY_9698de3fd86bc2ed |


## J — Testes

Regressão de entrega: **2290 aprovados, 3 skips, 0 falhas, 0 erros** em257.48s. Todas as identidades R5 preservadas; testes anteriormente aprovados não reproduzidos: 0. Focos e JUnit estão neste diretório. O teste de interface também passou isoladamente. O consumidor real de ZIP possui teste de integração que verifica preservação legada e referências novas de proveniência.

## K — Inferência e desempenho

19 chamadas textuais novas ao Ollama/Qwen3:14b, inclusive tentativas rejeitadas; 11 reutilizações de tarefas registradas. Serviço0.35.1, digest bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8. Tempos e tokens reais por requisição no ledger; medições ausentes ficam desconhecidas. O rascunho assistido não conta como chamada Ollama. Nenhuma inferência ASR/YOLO/ASD/Director/OCR ou render nova. Uso de GPU não foi medido nesta rodada textual.

## L — Preservação

621 arquivos originais/2,689,113,718bytes e27 checkpoints conferidos; sete renders preservados por stat, sem abrir os MP4. 122 documentos legados byte a byte; somente schemas e manifesto do ZIP derivado recebem atualização. ZIP R5 original preservado. Scores, shortlist, QA, gates, previews, direitos e autorizações não foram promovidos.

## M — Pendências

Cobertura semântica direcionada, não auditoria completa de todos os tópicos/perguntas. Completude automática e títulos Qwen ainda precisam melhorar: houve citações inventadas, extrapolações e bloqueios conservadores de vocabulário/negação. Não reduzir esses filtros para obter READY. Escuta/ASR, semântica, fatos, direitos, composição visual, câmera, preview e publicação exigem suas revisões. Importação automática desses campos na versão instalada do Curator não foi modificada nem homologada; foi validado o contrato offline e preservada a compatibilidade legada.

## N — Arquivos e SHA-256

ZIP: `docs/reports/r5_1_20261014/semantic_replay/package/SECOND_CURATION_R5_1_zd_wjssZ7mc_20261014_193320_488278_a2efe8.zip`

SHA-256: `3d64e70aa28a6ee3f3c16c4ce198302e567ab6501bb270ffe9a7ee3e42bc2733`

Validação: valid; 187 hashes no manifesto; CRC íntegro; referências pendentes0. Veja `review_packet/SEMANTIC_REVIEW.html`, `review_packet/social/story_visual_handoff.json`, seu schema, `FINAL_INTEGRITY.json`, `final_validation.xml` e `test_evidence_final.json`.

## O — Readiness e consumo

**SEMANTIC_HANDOFF_PARTIAL**, `publication_ready=false`. Não declarar R5.1 integralmente homologada. Abra `README_R51_CURATOR.md` e `SECOND_CURATION_SEMANTIC_HANDOFF.json`, valide o visual handoff pelo schema enviado, resolva IDs nos segmentos/units, vincule mídia pelo SHA e use os tempos absolutos. O Curator aplica seus presets, valida montagem e preview e solicita aprovação. Nenhuma importação desses metadados exige novamente Whisper, Qwen, visão ou Director.

Repetição do pacote com cache (sem inferências):

```text
.venv/Scripts/python.exe analyze.py --semantic-replay docs/reports/r5_20261014/release_replay/package/SECOND_CURATION_PARTIAL_zd_wjssZ7mc_20261014_140253_762578_0b9a68.zip --semantic-output docs/reports/r5_1_20261014/semantic_replay --semantic-phase package --semantic-config docs/reports/r5_1_20261014/semantic_config_final.json --semantic-test-evidence docs/reports/r5_1_20261014/test_evidence_final.json
```
