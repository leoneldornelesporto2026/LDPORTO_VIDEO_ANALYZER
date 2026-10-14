# Foquinha — triagem editorial provisória

Escopo: dados originais do ZIP Foquinha, produtores de segunda curadoria e fila humana existente. Nenhuma nova inferência, revisão humana, análise completa ou edição do ZIP/análise original.

## Problema demonstrado antes da alteração

O ZIP original contém 80 membros do catálogo, 77 unidades de revisão e três alternativas. A seleção avaliou 77 e selecionou zero. A fila já começava pelos quatro candidatos de maior interesse indicado no pedido; não havia prova de erro em sua primeira ordenação.

| ID | Score registrado | Duração | Gates locais que permanecem |
|---|---:|---:|---|
| MOMENT_00022_0001 | 0,734 | 22,76 s | Hook sem evidência; fora do alvo 30–90 s |
| MOMENT_00002_0002 | 0,715 | 20,98 s | Hook sem evidência; fora do alvo 30–90 s |
| MOMENT_00008_0002 | 0,713 | 28,74 s | Hook sem evidência; fora do alvo 30–90 s |
| MOMENT_00002_0000 | 0,610 | 44,66 s | Hook/standalone sem evidência; fronteira de tema cruzada |

Abertura/finalização limpas e comercial verificado não suprem estes gates. `editorial_verified=true` registra disponibilidade/integridade editorial, não confirmação humana de completude. Nenhum bloqueio global P1/ASD foi necessário para explicar esses quatro casos. O piso registrado continua 0,5.

A limitação comprovada era a acionabilidade: a fila antiga mostrava motivos genéricos de aprovação humana/prévia, omitindo os bloqueios locais, texto literal, contexto e instruções de áudio. `human_review_provisional=false` tinha escopo de integridade/comercial; podia ocorrer apesar da inelegibilidade editorial automática.

## Implementação

- Fila existente recebe schema aditivo 1.1, motivos locais, texto literal e contexto real, intervalo do áudio original, tarefas de revisão, fallback de enquadramento original e prioridade explícita. Sua ordenação usa scores registrados, bloqueios locais e rank original; não cria scores nem altera os intervalos.
- `human_review_queue(candidates, schema_version='1.0')` preserva exatamente o contrato e a ordem antigos, permitindo validar ZIPs legados contra sua própria versão. Versões desconhecidas falham explicitamente.
- Novo `review_state` distingue `DISCOVERED`, `PROVISIONAL_HUMAN_REVIEW` e elegibilidade automática sustentada pelos campos registrados. Aprovações humana, prévia e publicação permanecem falsas. O booleano legado de revisão provisória conserva seu escopo anterior.
- Candidatos recebem `selection_gate_diagnostics` e `review_plan`. O pacote e `editorial_result` recebem `human_review_summary`, com contagens e referência à fila existente; nenhuma segunda fila é persistida.
- Propostas de extensão ficam para avaliação humana; nenhuma recuperação de fronteira ou redução do piso foi aplicada neste pacote.

## Evidências

Replay em memória: `editorial_queue_replay.json`, fonte ZIP SHA-256 `0c6cd22d4892fddbb23ab71e6c12997c2a47709ebd919c12b8ebeaaeaec2f4ff`. A fila 1.0 regenerada corresponde exatamente ao JSON original. A fila 1.1 mantém 77 unidades, três alternativas e o mesmo conjunto de IDs; shortlist oficial continua zero. Os quatro primeiros permanecem na mesma ordem, agora com razões específicas. As 77 unidades estão em revisão editorial provisória; nenhuma foi aprovada.

Os motivos são multi-label: 73 abaixo do piso, 74 standalone sem evidência, 43 fora do alvo de duração, seis fora dos limites rígidos e 62 com estado comercial pendente na fila. O último denominador é unidade editorial, distinto da contagem de inspeções visuais/OCR. A matriz de exportação integrada é responsabilidade da raiz.

Focused final: **111 passed em 25,47 s, exit 0**. Comando/argv reais em `editorial_focused_final_run.json`; stdout em `editorial_focused_final.log`; JUnit em `editorial_focused_final.xml`. Testes cobrem o piso inalterado, completude positiva e negativos com score alto, triagem textual sem ASD, preservação de literal/contexto, aprovação separada, fila legada, prioridade, proveniência local e 80 membros/77 unidades/três alternativas. Freeze e contagem dos casos novos: `editorial_freeze.json`.

Integridade/contratos focados e transformação da fila: **VERIFIED**. Precisão editorial humana: **NOT_MEASURED**. Q&A, narrativa, recuperação de fronteiras, prévias reais e regressão completa ficam na integração coordenada pela raiz; este relatório não apresenta o episódio antigo como execução dos fontes atualizados.
