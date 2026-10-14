# Revisão textual dirigida — evidência editorial R5.1

**Conclusão:** os sete segmentos `SEG_00126`–`SEG_00132` sustentam um Story de
explicação sobre radionavegação: pergunta, mecanismo e encerramento local estão
presentes na transcrição. Os três títulos propostos têm suporte textual dentro
do próprio Story. Esta revisão não aprova áudio, fatos históricos, layout,
preview, direitos ou publicação e não conclui a homologação R5.1.

Foram identificadas duas extrapolações nos metadados herdados da série, listadas
adiante para correção ou bloqueio editorial. A validade de IDs e citações não
elimina esses problemas de paráfrase.

## Escopo e origem

Revisão por Codex, somente leitura de JSONs e texto persistido. Nenhuma inferência
Ollama, escuta, inspeção de frames ou render foi executado nesta revisão. Somente
este relatório foi escrito. A referência foi lida diretamente do ZIP R5, sem
extração sobre fontes.

- Pacote de referência: `docs/reports/r5_20261014/release_replay/package/SECOND_CURATION_PARTIAL_zd_wjssZ7mc_20261014_140253_762578_0b9a68.zip`.
- SHA-256 esperado da referência: `a84ede22de5fe91b8a5e1abe7044229534fe55943777d769364ff58842ab9807`.
- Série: `SEM_SERIES_0ab8edbb24f957bd`.
- Story: `SEM_STORY_9698de3fd86bc2ed`, posição **1/1**, função `EXPLANATION`.
- Artefatos examinados: série, QA semântico, títulos e Story Visual Handoff em `docs/reports/r5_1_20261014/semantic_replay/artifacts/`.

Snapshot examinado, antes de qualquer reparo posterior deste metadado:

| Artefato | SHA-256 |
|---|---|
| `editorial/story_series_proposals.json` | `b6358b780c4b5b75fe21fae161c8f476cca3a1bfdd1b6e9426f88953e2b7fb0f` |
| `social/narrative_editorial_title_proposals.json` | `0d27f508ccedcee451d0c9b2845df74f6c67f51e63a5e9ec98575e58ce17d6f6` |
| `social/story_visual_handoff.json` | `17ecba7a30bef196917d2ff5eeea4b626ddc40ecfb33fe2d35f5b50950e7223c` |

`provenance/semantic_series_reuse.json` informa que o modelo atual se absteve e
uma proposta anterior foi preservada, com caminho e hash da revisão anterior.
Isso comprova reaproveitamento documentado, não uma nova confirmação do modelo.
Os títulos registram origem `codex_assisted_editorial_draft_from_canonical_source`,
autor `Codex`, `new_ollama_call=false` e `human_review_completed=false`.

## Encadeamento encontrado na fonte

| Segmento | Intervalo absoluto, segundos | Função textual observada |
|---|---:|---|
| `SEG_00126` | 709.46–714.72 | Pergunta como o piloto sabe a direção quando não há radar. |
| `SEG_00127` | 714.94–722.38 | Introduz auxílios de radionavegação na época anterior ao GPS. |
| `SEG_00128` | 722.48–730.92 | Descreve antenas emitindo sinais de rádio em frequências específicas. |
| `SEG_00129` | 731.08–734.92 | Explica que o avião capta as frequências mediante sintonia. |
| `SEG_00130` | 735.12–739.66 | Relaciona o plano de voo à frequência das antenas, com Belém como exemplo. |
| `SEG_00131` | 739.90–752.10 | Relaciona sintonia, instrumento ADF e indicação da direção da estação. |
| `SEG_00132` | 753.34–754.26 | Encerramento explícito e limitado: “Grosseiramente é isso.” |

O início contém a própria pergunta e o desenvolvimento oferece uma explicação
compreensível sem depender de um episódio anterior. O antecedente maior, sobre o
voo específico, está nos segmentos anteriores, mas não é necessário para
entender este mecanismo. O trecho não explica todo o voo nem seu desfecho.

O fechamento atende à promessa de explicar o recurso de orientação; não se exige
clímax dramático de uma explicação técnica. O estado `OPEN_ENDING_DECLARED` da
série permanece conservador e não transforma o acidente inteiro em narrativa
encerrada. Os dados correspondem a **uma série com um Story**, não a sete Stories.

O trecho `SEG_00131` mantém uma condição de utilização e a referência a uma
estação. Não sustenta promessa universal de localização precisa, correção da
rota ou prevenção do acidente. Os contrafactuais sobre outra antena pertencem a
passagens posteriores, especialmente `SEG_00142`–`SEG_00143`, fora deste Story.
Não devem ser convertidos em causalidade factual ou spoiler deste episódio.

## Títulos, caption e capa

| Uso | Texto proposto | Suporte local | Avaliação textual |
|---|---|---|---|
| Principal | COMO O ADF VAI APONTAR A DIREÇÃO? | `SEG_00131` | Pergunta sobre o mecanismo explicado no mesmo Story; não expande a sigla nem promete solução do voo. |
| Alternativa 1 | FREQUÊNCIAS DE RÁDIO: PARA ONDE VOAR? | `SEG_00128`, `SEG_00131` | Liga o sinal de rádio à direção indicada, com palavras presentes no material. |
| Alternativa 2 | O PILOTO E OS AUXÍLIOS DE RADIONAVEGAÇÃO | `SEG_00126`, `SEG_00127` | Apresenta o assunto e o participante genérico da pergunta, sem atribuir identidade. |

Os títulos não introduzem pessoas, números, revelações, expansão inglesa de ADF
ou fatos de episódios futuros. São propostas editoriais identificáveis, sem
garantia de viralidade. O público geral pode precisar do desenvolvimento para
entender ADF; isso é uma decisão de clareza editorial, não evidência de identidade.

O hook visual reproduz a pergunta canônica de `SEG_00126`. A caption social
reproduz a fala de `SEG_00129`, sem nova afirmação. A capa reutiliza o título e
indica o intervalo de `SEG_00126` apenas como candidato; `frame_visual_verified`
é falso e direitos/identidade permanecem desconhecidos. Legibilidade, quebra de
linha, colisões, branding, safe areas e escolha de frame dependem do Curator.

## Alinhamento e destaques

Foram comparados os **118 tokens** exportados com
`transcript/relevant_words.jsonl` do ZIP de referência, por `word_id`, palavra,
segmento, início, fim e speaker label: **zero divergências** nesses campos e
**zero tokens fora do intervalo canônico de seu segmento**. São tempos ASR
persistidos, sem realinhamento nem verificação auditiva nesta revisão.

| Destaque | Palavra de origem | Intervalo absoluto, segundos |
|---|---|---:|
| radionavegação | `WORD_0001784`, `SEG_00127` | 721.04–722.38 |
| frequências | `WORD_0001803`, `SEG_00128` | 729.02–729.62 |
| ADF | `WORD_0001843`, `SEG_00131` | 745.66–746.48 |

Os três destaques existem na fala transcrita. A granularidade é `word`, mas
`audio_verified=false` e `requires_alignment_review=true`. A identidade civil
de `SPEAKER_00` não foi inferida. Tempos relativos continuam nulos; `edit_mapping`
mantém os sete intervalos para decisão posterior do Curator.

A união dos intervalos selecionados soma **42.64 s** de fonte. A janela entre o
primeiro início e o último fim mede **44.80 s**, incluindo lacunas. Nenhuma dessas
medidas comprova a duração final de um render. Os sete segmentos são adjacentes
na transcrição canônica; a revisão de pausas e cortes ainda exige a fonte.

## Pendências editoriais concretas do snapshot

1. **Resumo da série:** o trecho “determinar sua posição e rota” amplia a fonte.
   `SEG_00131` descreve direção relativa à estação, não determinação de posição
   nem rota completa. Preferir formulação limitada à direção/sintonia, ou manter
   bloqueio para revisão.
2. **Suggested ending do Story:** “em áreas onde o GPS não estava disponível”
   troca o contexto temporal de `SEG_00127` por uma condição geográfica não dita.
   A afirmação de que a tecnologia era “essencial” também é mais forte que a fala.
   O próprio encerramento de `SEG_00132` oferece opção fiel, sem essa extrapolação.
3. **Lacuna climática:** `missing_information` menciona condições climáticas, mas
   o hook não promete explicar clima. Trata-se de possível tema adicional, não
   componente obrigatório cuja falta torne esta explicação incompreensível.
4. **ASR/escuta:** `SEG_00126`, `SEG_00127` e `SEG_00131` têm revisão ASR pendente
   na origem. A coincidência dos tokens e tempos com o pacote não substitui escuta.
5. **QA15 de maior alcance:** o estado final observado é `ANSWER_PROPOSED`, com
   resumo extrativo separado por `[…]`, não `CONFIRMED`. O candidato inclui
   `SEG_00142`, cuja expressão “essa antena” depende de contexto anterior, como
   `SEG_00140`, fora dos IDs da resposta selecionada. Essa limitação deve continuar
   explícita; não transportar nomes ou conclusão contrafactual para o Story local.

O Story Visual Handoff observado está `COMPLETE_FOR_REVIEW`, com publicação
falsa, `CURATOR_VISUAL_REVIEW_REQUIRED`, regiões do sujeito `UNKNOWN` e bloqueios
de ASR, revisão editorial, direitos, layout e preview. Isso significa suficiência
de metadados para revisão, não aprovação humana ou comprovação visual.

**Estado desta revisão:** evidência textual local rastreável para um Story
explicativo, três títulos e três destaques; reparos de paráfrase e revisões
humanas permanecem pendentes. O estado de entrega deve continuar
`SEMANTIC_HANDOFF_PARTIAL` enquanto essas limitações e a cobertura direcionada
existirem.

## Adendo após a revisão

As duas extrapolações apontadas nos itens 1 e 2 foram corrigidas antes da
exportação final: o resumo usa a fala canônica de `SEG_00131` sobre direção à
estação e o encerramento usa `SEG_00132`. Os valores anteriores, substitutos,
hashes e autoria assistida estão registrados em
`semantic_replay/artifacts/provenance/editorial_metadata_repair.json`.
As ressalvas sobre escuta, contexto de QA15, cobertura e aprovação permanecem.
Este adendo preserva os achados da revisão da versão anterior.
