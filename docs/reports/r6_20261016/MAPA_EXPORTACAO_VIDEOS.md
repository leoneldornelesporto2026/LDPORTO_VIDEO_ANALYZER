# Mapa de exportação para Vídeos — R6

`paths.videos_directory()` consulta a Known Folder Vídeos do Windows, incluindo redirecionamento. O destino pode ser escolhido na GUI/CLI. O padrão é `Vídeos/LDPORTO_VIDEO_ANALYZER`.

A pasta é identificada pelo título, ID e revisão exclusiva. Caracteres inválidos/reservados do Windows são sanitizados. Um título fornecido pelo usuário é registrado como título editorial com proveniência; o título original do pacote permanece nos metadados. A revisão final usa a redação do pedido, incluindo o travessão; a original usava hífen. A checagem dos codepoints confirmou os acentos preservados nos arquivos: a aparência de caracteres de substituição em algumas saídas do console era uma limitação de exibição, não corrupção comprovada dos metadados. Não se corrigiu transcrição ou identidade a partir do título.

| Pasta | Conteúdo real |
| --- | --- |
| `00_RESUMO` | Guia e resumo executivo em PDF, melhores momentos estruturados e índice HTML. |
| `01_TRANSCRICAO` | Transcrição disponível pesquisável, TXT/SRT e segmentos/palavras JSONL; cobertura por união temporal, lacunas, tempos inválidos preservados para revisão. |
| `02_PESSOAS_E_CENAS` | Participantes, aparições, cenas quando disponíveis, instrumentos e fila de identidade. Ausência de observação é explícita. |
| `03_REELS/REEL_NNN` | Briefing com ID canônico, PDF individual, transcrição/words, plano de câmera, títulos propostos e imagens reais quando existentes. Índice de thumbnails indica necessidade de seleção humana. |
| `04_STORIES/SERIE_NNN/PARTE_NN` | Unidades/séries existentes, títulos próprios quando fornecidos com evidência, palavras/segmentos, câmera compartilhada e preflight por intervalo. Não se completam séries por invenção. |
| `04_STORIES/AVULSOS` | Stories independentes continuam independentes, sem inventar vínculo de série. |
| `05_CAMERAS` | Planos existentes, contrato comum, foco e estágios de validação. Não contém prova nova de zoom final. |
| `06_SEGUNDA_CURADORIA` | ZIP idêntico ao snapshot validado, master de referências, template de decisões e instruções. |
| `07_RELATORIOS_TECNICOS` | Qualidade, limitações, proveniência e ledger de SHA256. |
| `PROJECT_MANIFEST.json` | Schema, identidade da mídia/pacote/run, estado e inventário com hashes. |

Os intervalos TXT/SRT/JSONL continuam em segundos absolutos da fonte. PDFs são documentos de leitura; JSONs permanecem canônicos. O dossiê não inclui vídeo-fonte, não substitui áudio musical e não cria MP4 social final. Contact sheets reutilizadas permanecem vinculadas ao pacote de origem e não comprovam câmera atual renderizada.

Estados possíveis do dossiê: `PARTIAL`, `READY_FOR_REVIEW`, `CANCELLED`, `FAILED`. A integridade de um dossiê cancelado pode ser válida, mas isso não o torna pronto para revisão. `preview_approved=false` e `publication_ready=false` permanecem obrigatórios. O ZIP conserva seus nomes/estados legados para compatibilidade; “READY” significa disponibilidade para revisão, não publicação.

A geração roda em worker na GUI, com progresso por artefatos e cancelamento entre unidades. Cancelar conserva a revisão parcial com manifest explícito. Verificação e inventário também rodam em worker. `project_export.json` é um ponteiro gravado na análise apenas pela operação GUI/automática associada ao ZIP produtor; os comandos desta auditoria não alteraram a análise original.

O verificador confere schema, caminho da própria folha manifest e antecessores, conjunto exato de arquivos, hashes, artefatos obrigatórios, PDFs de cada candidato, catálogo, pacote/source/run e gates. Testes cobrem troca do pathname durante leitura, snapshot de outra revisão, adulteração, PDFs ausentes e estados indevidos.

Os caminhos e hashes reais das revisões geradas estão em `R6_ARTIFACT_INDEX.json`, produzido ao encerrar os testes. A revisão inicial de apresentação foi preservada; uma revisão final corrigiu a diagramação e usa o título editorial explicitamente fornecido no pedido. Não se duplicou a mídia-fonte em nenhuma delas.
