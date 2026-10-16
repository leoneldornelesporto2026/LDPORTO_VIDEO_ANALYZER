# Auditoria da arquitetura R6 — 16/10/2026

## Escopo e proteção

Trabalho realizado no Analyzer atual, branch `baseline/ldporto-20261012-prompt01`, sem commits/push/reset ou extração de fontes antigos. A inspeção inicial foi somente leitura e dividida entre legendas/handoff, câmera/pessoas e armazenamento. O inventário de imports, funções, tamanhos e hashes está em `ARQUITETURA_INVENTARIO_R6.json`.

Antes de editar: `git status --short` estava vazio; branch/HEAD foram registrados em `BASELINE_R6.json`. Foram inventariados 1.133 arquivos protegidos por caminho/tamanho/mtime e calculados 99 SHA256 de artefatos importantes. Fontes e schemas rastreados foram preservados em `rollback_sources.zip`. A recuperação deve selecionar os arquivos necessários desse snapshot e comparar o diff; não extrair o ZIP sobre a árvore inteira nem usar reset destrutivo.

Tamanho inicial medido: **11.426.145.600 bytes**. Escopo consistente: árvore de trabalho, excluindo `.git`, `.venv`, `models`, diretórios com links e arquivos de credenciais. A mídia foi apenas inventariada por metadados; seu conteúdo não foi lido ou re-hasheado. O SHA256 do vídeo usado nos contratos é o informado pela análise de origem, com esse escopo explicitado.

## Arquitetura reaproveitada

| Área | Componentes reais | Integração e observação |
| --- | --- | --- |
| Entradas | `app.py`, `analyze.py`, `pipeline.py` | GUI Tk chama CLI; pipeline usa Context/ProvenanceContext e checkpoints por estágio. Novas ações de dossiê/validação não entram no pipeline de inferência. |
| Percepção visual | `vision.py`, `person_reid.py`, `person_motion.py`, `face_quality.py`, `visual_sampling.py` | Tracking/tracklets, qualidade, recuperação facial, Re-ID conservador e movimento já existem. Não foram substituídos ou executados nesta rodada. |
| Voz/pessoa | `active_speaker.py`, `asd_backend.py`, `camera_evidence.py`, `speaker_signals.py` | Evidência acústica/local/global e abstenções são distintas. Nenhum locutor foi ligado nominalmente a rosto por título ou aparência. |
| Câmera | `camera_director.py`, `camera_timeline.py`, `global_camera_planner.py`, `camera_geometry.py`, `camera_motion.py`, `camera_preflight.py` | Motor existente preservado; correção de deadzone editorial e adaptador de handoff compartilhado. Geometria/preflight continuam exigidos. |
| Preview | `preview_renderer.py`, `preview_verifier.py`, `preview_integration.py`, `zoom_delivery.py` | Render técnico e inspeção de frames já existem. Render técnico amplo usa padding; blur amplo pertence ao Curator. Zoom renderizado deixou de equivaler a movimento final comprovado. |
| Áudio/texto | `transcription.py`, `targeted_asr.py`, `subtitle_review.py`, `timeline.py`, `subtitle_style.py` | Texto original, alternativas e traduções permanecem separados. ASR localizado continua opt-in. S7 detalhado continua selecionado; triagem R6 alcança todos os candidatos exportados sem ASR adicional. |
| Curadoria | `understanding.py`, `editorial.py`, `editorial_intelligence.py`, `editorial_outcome.py`, `second_curation.py` | Catálogo, shortlist, alternates, cortes e filas humanas são preservados. Ranking não é probabilidade de viralização. |
| Narrativa/Stories | `narrative_relations.py`, `narrative_handoff.py`, `semantic_narrative.py`, `semantic_replay.py`, `story_visual_handoff.py`, `social_output.py` | Relações e séries existentes continuam canônicas. Séries não contíguas mantêm intervalos separados e revisão de montagem. Não se chamou modelo para criar histórias/títulos novos. |
| Entrega | `reports.py`, `second_curation_export.py`, `compact_artifacts.py`, `semantic_package.py`, `execution_receipts.py` | Formatos legados e recibos mantidos; master aditivo, hashes, schemas e verificação do conteúdo exportado. Derivações preservam o master pai. |
| Armazenamento | `paths.py`, `storage.py`, `storage_dialog.py`, `core.py` | Known Folder Vídeos, inventário read-only, proteção de fonte, leases/estado/caminhos, quarentena e restauração no recurso existente. |

## Novos componentes e responsabilidades

- `camera_handoff.py`: projeção do Director existente para Reels/Stories; intenções de composição, geometria e estágios de evidência. Não planeja por um motor independente nem renderiza.
- `performer_evidence.py`: projeções conservadoras de observações/tracks/participantes e fila de confirmação. Não reconhece automaticamente nomes, instrumentos ou papéis.
- `editorial_pdf.py`: documentos pesquisáveis com fonte Unicode local, índice, bookmarks, links de tempo, paginação e JPEGs reais já existentes. Sem nova dependência.
- `project_export.py`: revisão exclusiva organizada, PDFs/JSONs/TXT/SRT/ZIP, cancelamento, manifest e verificação. Não abre mídia original nem cria MP4 social.
- Schemas aditivos: câmera, preflight clássico/semântico, master e manifest de dossiê.

## Causas principais verificadas

1. Pipeline S7 selecionava apenas a shortlist; o ZIP exportava todo o catálogo. O Curator podia descobrir legenda longa sem alinhamento só no render. Corrigido pelo preflight pré-exportação para todos os intervalos, sem reduzir gates.
2. `storage` aceitava fonte original externa como removível mediante opção rotineira. A opção foi removida e a fonte tornou-se incondicionalmente protegida.
3. Proposta de zoom, timeline, recibo de render e pixels finais podiam ser interpretados como o mesmo sucesso. Os contratos agora separam esses níveis; entrega final fica não comprovada sem medição correspondente.
4. Derivação semântica mantinha master/hashes da revisão anterior. A regressão foi reproduzida e corrigida preservando os bytes do master pai e reindexando a revisão derivada.
5. PDF inicialmente compartilhava CID por glyph de espaço/NBSP e hífens; render era correto, mas extração não. CIDs por codepoint corrigiram a busca/extração Unicode.
6. Export por pathname podia validar pacote A e copiar B se o arquivo fosse trocado. Agora valida, deriva, hasheia e copia o mesmo snapshot imutável.

## Duplicações e organização

Há coleções brutas volumosas de observações, mapping e diagnósticos em `analysis`, além de projeções compactas, evidências de revisão, exports e snapshots históricos. Isso não prova obsolescência. Os contratos/recibos referenciam parte delas; nenhuma foi removida. `docs/reports` contém evidências atuais e `docs/archive` permanece histórico. `src.zip` e ZIPs de fixtures foram tratados como dados protegidos, nunca fonte de implementação.

`config/config.yaml` tem chaves repetidas de contexto comercial com valores iguais; não foram alteradas incidentalmente. A fronteira Analyzer/Curator mantém dois usos de render com finalidades diferentes: canário técnico local e produto social final. Não foi criado um segundo renderer de legendas/câmera no Analyzer.

## Cache e reprocessamento seletivo

Os fingerprints de estágio 21 incluem os novos helpers/schemas. Alterações de export não reexecutam ASR/visão. Dossiê/PDF, ZIP e índice podem ser reconstruídos por rotas independentes; cada saída usa nova revisão, preservando aprovações anteriores. O caminho `--director-only` e replays existentes continuam disponíveis, mas não foram usados para reprocessar mídia nesta sessão.

| Ação | Rota e limite |
| --- | --- |
| Dossiê/PDF | `analyze.py --export-project ZIP --project-destination RAIZ [--analysis PASTA] [--title TITULO]`; gera revisão nova. |
| Apenas ZIP | `analyze.py --rebuild-package PASTA --project-destination RAIZ --reuse-visuals ZIP`; sem fonte/modelos; preserva contact sheets verificadas quando fonte/ID/intervalos coincidem. |
| Índice | `analyze.py --rebuild-project-index analysis --project-destination RAIZ`; inventário read-only e JSON exclusivo. |
| Validar entrega | `analyze.py --verify-project PASTA`; schema, arquivos requeridos, hashes, pacote/fonte/run, IDs e gates. |
| Câmera | `analyze.py --director-only PASTA`; mecanismo existente, requer atenção à revisão e aos contratos de cache. Não executado no show. |
| ASR incerto | Fila/IDs e opt-in do `targeted_asr`; orçamento e hash da fonte existentes. Não executado. |
| Thumbnails/visuais | `generate_visuals_on_demand` existente; exige fonte validada e seleção explícita. Não executado. |
| Stories semânticas | `--semantic-replay` existente pode chamar modelo quando solicitado. Nesta rodada só se consumiram propostas existentes. |

Não se recriou executor de desenvolvimento, fila de prompts, estados ou locks de automação aposentada.

## Limites desta entrega

É um incremento auditável, não homologação integral de todas as fases R6. Restam reconhecimento instrumental/papéis com evidência visual nova, revisão/associação humana nominal, medição conclusiva de movimento nos frames finais, aplicação dos novos gates pelo Curator independente, confirmação de direitos e homologação dos cortes reais. Esses itens continuam pendentes e não foram convertidos em sucesso por configuração.
