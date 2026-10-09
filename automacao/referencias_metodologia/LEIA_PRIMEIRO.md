# Prompts para evoluir o LDPORTO Video Analyzer

São 12 etapas de análise no Work. Cada uma tem um prompt de implementação correspondente para o ChatGPT normal. O pacote foi preparado com base no ZIP enviado em 8 de outubro de 2026.

O objetivo é obter diagnóstico e especificações concretos no Work e aplicar as correções no projeto atual depois. Esta entrega contém prompts; o código do analisador não foi alterado.

## Como usar

1. No Work, anexe o SECOND_CURATION_READY e envie 00_PROMPT_MESTRE_WORK.txt. Ele inicia a D01. O prompt D01 separado é uma alternativa; não precisa reenviar ambos para fazer a mesma análise.
2. Continue na mesma conversa com os prompts WORK/D02 até WORK/D12, um por vez. Salve os relatórios e checkpoints de cada etapa. Os prompts são completos e podem funcionar sozinhos; em uma conversa nova, anexe também os relatórios necessários.
3. Se tiver o código atual, anexe o ZIP completo ao Work para localizar funções e validar causas. O SECOND_CURATION_READY contém análises, não os arquivos executáveis.
4. Ao final, envie ao ChatGPT normal o ZIP atual do projeto e as entregas da D12; use 13_PROMPT_NORMAL_CONSOLIDADO.txt para implementar a evolução.
5. Se preferir correções em blocos, use os 12 prompts NORMAL correspondentes com seus relatórios, respeitando as dependências. Não execute o consolidado e todos os prompts por etapa sobre versões antigas sem checkpoints, pois isso pode duplicar trabalho.
6. Para retomar uma execução interrompida, use 98_RETOMADA_WORK.txt ou 99_RETOMADA_NORMAL.txt junto do último checkpoint.

O código pode ser anexado no começo ou na implementação; sem ele, os diagnósticos continuam possíveis, mas causas na implementação e alterações de funções ficam a confirmar. Para escutar/validar percepção e render, acrescente vídeo/áudio real ou amostras adequadas. Não é necessário reenviar inferências pesadas se as evidências já existem.

Os D01–D12 organizam estas sessões. Não substituem nem renumeram as etapas internas do programa ou as sessões S1–S11 anteriores.

## Etapas

| Etapa | Análise principal |
| --- | --- |
| D01 | Integridade do pacote e contratos do pipeline |
| D02 | Transcrição diarização e alinhamento temporal |
| D03 | Tracking e identidade persistente de pessoas |
| D04 | Active speaker e associação entre voz e pessoa |
| D05 | Shots câmera movimento zoom e layouts |
| D06 | Compreensão global tópicos arcos e perguntas |
| D07 | Candidatos limites ranking e seleção |
| D08 | Áudio música eventos e classificação comercial |
| D09 | Legendas títulos stories e apresentação |
| D10 | Handoff decisões replay render e preview |
| D11 | Desempenho cache GUI e observabilidade |
| D12 | Testes prioridades e briefing final para implementação |

Execute D01–D11 na ordem apresentada para uma auditoria completa e D12 para consolidar. As dependências estão em cada prompt. Correções podem ser priorizadas pelo grafo real e backlog produzido.

## O que já motivou estes prompts

- 55 candidatos, 52 após dedup e 1 na shortlist.
- Active speaker confirmado com cobertura zero; foco resolvido de câmera aproximadamente 1,95%.
- YOLO indisponível no run auditado e 653 identidades persistentes reportadas.
- Rank 1 com hook ausente e gate fechado; fragmento de 1,46 s em posição alta.
- Revisão de legendas com 0 candidatos avaliados, apesar de 1 story final.
- Perguntas Q_0114/Q_0115 do selecionado sem registro no qa_pairs exportado.

O diagnóstico completo e as métricas estão em DIAGNOSTICO_PACOTE_ATUAL.md e BASELINE_VERIFICADA.json dentro do ZIP. Essas métricas pertencem ao export, não certificam precisão perceptiva.

## Organização dos arquivos

- 00_PROMPT_MESTRE_WORK.txt: objetivo, regras e entrega padrão.
- WORK/D01 a D12: auditorias com exemplos reais, evidências, dependências e aceitação.
- NORMAL/D01 a D12: instruções para aplicar cada plano no código existente.
- 13_PROMPT_NORMAL_CONSOLIDADO.txt: implementação consolidada depois da auditoria.
- 98_RETOMADA_WORK.txt e 99_RETOMADA_NORMAL.txt: continuidade após interrupção.
- CONTRATO_ACHADOS_D01_D12.json: estrutura proposta para diagnóstico; não altera o schema de decisões.
- EXEMPLO_DECISOES_VAZIO.json: exemplo estrutural compatível, sem aprovações ou outras ações.

Os relatórios citados nos prompts serão produzidos quando as etapas forem executadas. Eles não estão prontos neste kit.
