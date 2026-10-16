# Relatório final do incremento R6 — 16/10/2026

## Entrega e alcance

O Analyzer atual recebeu um incremento de proteção, triagem de legendas, contratos comuns de câmera/pessoas, dossiê organizado/PDF, central de resultados e gestão segura de projetos. O show `9UCGZia2p1k` foi exportado de seus resultados existentes para Vídeos, com ZIP importado pelos importadores reais do Curator. Não se reexecutou percepção audiovisual nem se declarou concluída a homologação integral das quinze fases.

Os caminhos absolutos e hashes das revisões estão em `R6_ARTIFACT_INDEX.json`. A revisão final é `20261016T180302510442Z_0796ac`, em `Vídeos/LDPORTO_VIDEO_ANALYZER`, com título editorial fornecido no pedido. O guia tem 13 páginas; existem 70 relatórios de Reels e 49 relatórios de propostas de séries, além de transcrição, partes, imagens existentes e arquivos estruturados. A revisão anterior foi preservada como evidência da melhoria de apresentação.

O dossiê está **READY_FOR_REVIEW**, com `preview_approved=false` e `publication_ready=false`. A qualidade de origem continua parcial/P1_DEGRADED. O nome legado `SECOND_CURATION_READY.zip` identifica pacote de revisão; não afirma prontidão para publicação ou existência de MP4 social final.

## Alterações principais

- Preflight evidencial de legenda para todo o catálogo/Stories, com seis estados e lacunas. Revisão S7 selecionada e ASR opt-in continuam separados.
- Master referencial com hashes/IDs/run/source e validação derivada dos dados efetivamente exportados. Revisões semânticas preservam o master pai.
- Um contrato de câmera para Reels/Stories, adaptando o Director existente; seis intenções e fallback amplo/preservado. Não se criou outro renderer.
- Correção do deadzone em zoom deliberado e separação estrita entre proposta, geometria, preflight, timeline, render e movimento final comprovado.
- Contratos conservadores de tracks/aparições/participantes/instrumentos e fila humana. Nomes/papéis não foram reconhecidos a partir do título ou semelhança de rostos.
- Exportação Windows em revisão exclusiva, PDFs pesquisáveis com Unicode/índice/bookmarks/links/imagens, manifest/checksums e verificação de completude/pacote/revisão. Snapshot imutável evita validar um ZIP e copiar outro.
- Central de resultados, exportação opcional ao finalizar, progresso/cancelamento e ações de reabertura/verificação. Rotas baratas de dossiê, ZIP e índice sem reexecutar ASR/visão.
- Fonte original removida das opções de limpeza rotineira. Inventário read-only, proteção de caminhos/links/hashes/uso, quarentena/restauração e cancelamento. Quarentena libera zero bytes físicos; não foi feita limpeza real.

## Antes/depois do show

| Indicador | Origem | Após este incremento |
| --- | --- | --- |
| Candidatos | 70 | 70; IDs/intervalos preservados |
| Shortlist automática | 1 | 1; gates não relaxados |
| Revisão S7 detalhada | Concentrada na shortlist | Preservada; não confundida com triagem global |
| Preflight R6 por candidato | Não disponível | 70/70: 68 revisão de alinhamento, 2 revisão de áudio |
| Candidatos CAPTION_READY no preflight real | Não medido pelo novo contrato | 0; todos continuam sujeitos a revisão |
| Cobertura temporal de transcrição | Aproximadamente 16,9% | 16,917707%; não aumentada artificialmente |
| Smart Camera | 56 decisões históricas | Mesma evidência histórica; nenhum novo render do show |
| Zoom proposto / entregue | 1 proposto, 0 entregue | 0 movimentos finais comprovados; correção de movimento comprovada em fixtures |
| Foco visual resolvido | Aproximadamente 1,063% | Sem nova medição audiovisual |
| Speaker/person confirmado | Nenhum | Nenhum promovido automaticamente |
| Identidades civis confirmadas | Sem confirmação comprovada | Pendentes de fonte e confirmação humana |
| Contact sheets | 12 no ZIP | 12 preservadas por hash, sem decodificar nova mídia |
| Dossiê organizado/PDF | Não existia esse recurso | Guia/resumo/transcrição + 70 Reels + 49 propostas de séries |
| Fonte selecionável na limpeza | Sim | Sempre protegida |

As 49 séries e 86 referências de partes são propostas narrativas já existentes, com pendências e possível reutilização contextual de IDs. Não equivalem a 49 histórias completas aprovadas. Títulos/alternativas ausentes permanecem ausentes, em vez de se criar conteúdo sem sustentação.

## Verificações e preservação

Regressão final: **552 testes passaram e 1 foi ignorado**, 91,58 s, com log/XML. Os importadores reais do Curator passaram com os 70 candidatos do show e com fixture sintético. Fontes Curator observados e pacotes permaneceram inalterados. Leitor real do Windows renderizou PDFs; foram vistas as primeiras quatro páginas do guia e do Reel 001 finais, além do ensaio Unicode sintético. Detalhes/limites estão em `RESULTADO_TESTES_R6.md`.

`PRESERVACAO_R6.json` registra **99 hashes iguais e 1.133 arquivos protegidos com metadados iguais**. Mídia não foi lida/re-hasheada; o hash original nos contratos foi informado pela análise existente. Não houve commit, push, reset, limpeza real, movimentação de dados anteriores, instalação, download de pesos ou publicação. `.env`, credenciais, modelos e mídia original não foram alterados.

Tamanho inicial da árvore no escopo protegido da auditoria: **11.426.145.600 bytes**. O valor final, diferença e tamanho das duas revisões em Vídeos estão em `TAMANHOS_R6.json`. A métrica exclui `.git`, `.venv`, `models`, links e credenciais em ambas as medições. O crescimento corresponde a relatórios/evidências/ZIP/PDFs novos; espaço recuperado pela sessão: **0 bytes**. Não se copiou o vídeo-fonte inteiro.

## Pendências que não foram convertidas em sucesso

1. Homologar crops reais de artista/dupla/instrumentos, blur amplo, transições, rosto/cabeça/mãos, títulos e legendas no renderizador final do Curator.
2. Implementar/qualificar uma medição conclusiva de movimento por comparação com os frames finais. Até lá, zoom renderizado não é zoom entregue comprovado.
3. Obter observações visuais confiáveis de instrumentos/papéis e confirmar participantes com evidências/humano. Os contratos novos não são reconhecedores novos.
4. Revisar áudio, canto, letras incertas, palavras/limites e os 70 candidatos sinalizados. Cobertura de 16,92% não comprova transcrição integral do show.
5. Fazer o Curator independente aplicar os novos gates/índices R6. Sua aceitação de campos adicionais foi testada; consumo automático, render e publicação não foram homologados.
6. Validar continuidade, duração/encerramento e títulos individuais de cada proposta de Story, além de direitos/créditos musicais. Nenhum título criativo ou identidade foi aprovado automaticamente.
7. Completar homologação de UI com operação humana longa/cancelamento/reabertura e symlinks/junctions reais. Arquivamento/remoção integral de projetos, purga física de quarentena e nova inferência visual seletiva não foram adicionados como ações destrutivas genéricas.

## Documentos de entrega

`AUDITORIA_ARQUITETURA_R6.md`, `DIAGNOSTICO_CAMERA_SHOW.md`, `DIAGNOSTICO_PESSOAS_E_IDENTIDADES.md`, `DIAGNOSTICO_AUDIO_LEGENDAS.md`, `CONTRATO_ANALYZER_CURATOR_R6.md`, `PLANO_ORGANIZACAO_E_LIMPEZA.md`, `MAPA_EXPORTACAO_VIDEOS.md`, `RESULTADO_TESTES_R6.md` e este relatório. Evidências executáveis, hashes, XMLs e amostras visuais acompanham a mesma pasta.
