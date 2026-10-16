# Resultado dos testes R6 — 16/10/2026

## Regressão final executada

**552 passaram, 1 ignorado; 553 coletados; 91,58 segundos.** Python 3.11 do `.venv` já instalado. Evidências: `integrated_final.junit.xml` e `integrated_final.log`. Não foi executada a suíte inteira nem um pipeline completo.

Comando real (a saída foi gravada com `Tee-Object` no log indicado):

```powershell
.venv/Scripts/python.exe -m pytest src/tests/test_r6_project_export.py src/tests/test_r6_project_integrity_safety.py src/tests/test_r6_storage_safety.py src/tests/test_r6_caption_handoff.py src/tests/test_r6_camera_performer_handoff.py src/tests/test_sol_v3_gui_review.py src/tests/test_stage54_ocr_gui.py src/tests/test_v43_handoff.py src/tests/test_v44_second_curation.py src/tests/test_v44_ops.py src/tests/test_s7_subtitle_review.py src/tests/test_stage21_subtitle_alignment.py src/tests/test_s6_camera_director_smart_zoom.py src/tests/test_stage50_visual_review.py src/tests/test_r51_semantic_package.py src/tests/test_r51_story_visual_handoff.py src/tests/test_r51_semantic_replay.py src/tests/test_r5_narrative_handoff.py src/tests/test_r5_narrative_relations.py src/tests/test_r5_replay_export.py src/tests/test_transcription_report_integrity.py src/tests/test_transcription_fidelity.py src/tests/test_runtime_fidelity_contracts.py src/tests/test_stage65_execution_receipts.py src/tests/test_v44_reporting_robustness.py src/tests/test_sol_v4_checkpoint_storage.py -q --tb=short --junitxml=docs/reports/r6_20261016/integrated_final.junit.xml
```

O único skip é criação de symlink real no Windows sem o privilégio necessário. Reparse em antecessor foi exercitado por simulação; isso não substitui homologação de symlink/junction real no ambiente de uso.

## Ensaios adicionais reais

- ZIP original do show: validação estrutural aprovada sem alterações.
- Reconstrução somente do pacote: 70 candidatos, shortlist 1, 12 contact sheets reaproveitadas com fonte/ID/intervalos/hashes verificados. Nenhuma imagem nova de mídia foi decodificada.
- Preflight do pacote real: **68 ALIGNMENT_REVIEW_REQUIRED, 2 AUDIO_REVIEW_REQUIRED**, cobrindo todos os 70 candidatos; 1 Story clássico também triado; zero chamadas novas de ASR.
- Dossiê final em Vídeos: 70 PDFs de Reels, 49 PDFs de séries existentes, 86 referências de partes com preflight próprio, guia/resumo/transcrição e ZIP. Revisão final validou 1.772 arquivos antes de anexar os relatórios desta auditoria. Partes/IDs podem ser reutilizados como contexto entre propostas; essas quantidades não significam 49 séries completas aprovadas.
- `read_package` e `smoke_import` do Curator real passaram no pacote do show com 70 candidatos e no fixture sintético de três candidatos. Sem modelo, render ou acesso à mídia. `show_curator_import_r6.json` e `caption_curator_import_r6.json` registram limites e hashes.
- Leitor independente `Windows.Data.Pdf`: PDF sintético de cinco páginas renderizado; depois correção de CID e comparação de PNGs idênticos. Guia final do show tem 13 páginas e Reel 001 tem 5; primeiras quatro páginas de cada um foram renderizadas e vistas. Não se afirma inspeção visual de todos os 122 PDFs.
- GUI Tk real aberta oculta com subprocessos/threads de inferência e refresh de rede bloqueados: construção da central e estados iniciais verificados. Não é ensaio completo de todos os cliques/progresso/cancelamento de uma análise longa.
- Preservação: `PRESERVACAO_R6.json`: 99 hashes iguais e metadados dos 1.133 arquivos protegidos iguais. Mídia original apenas por metadados, sem nova leitura de conteúdo.

## Critérios A–K e limites

| Critério | Resultado comprovado |
| --- | --- |
| A — show degradado | Dossiê real gerado com dados existentes e análise parcial/P1_DEGRADED preservada. Não reexecutou inferência do show. |
| B — foco no artista | Geometria/contrato e regressões sintéticas passaram. Crop real atualizado com rosto/tronco/instrumento continua pendente. |
| C — banda completa | Fallback blur no contrato comum e preservação da fonte. Render social real do Curator não executado. |
| D — troca de integrante | Histerese/movimento do motor existente preservados; associação incerta não promovida. Homologação audiovisual real pendente. |
| E — canto/instrumental | Sem substituição de áudio ou legenda fabricada; classificação só com evidência. Reconhecimento musical/instrumental real não executado. |
| F — ASR/captions | Todos os candidatos reais triados antes do handoff; casos de legenda longa sem word alignment cobertos. Curator instalado ainda não aplica os novos gates automaticamente. |
| G — Stories | Contratos de intervalos, sequência, duração e preflight testados; 86 partes exportadas de propostas existentes. Títulos/limites/continuidade continuam revisão humana, sem geração nova de títulos/episódios. |
| H — PDFs | Unicode pesquisável, índice/bookmarks/links/imagens/paginação testados e amostras do show vistas em leitor independente. Qualidade visual total dos PDFs não foi inspecionada página a página. |
| I — Vídeos | Known Folder resolvida no Windows, revisões exclusivas, hashes e arquivos obrigatórios validados. Reabertura suportada pela central; fluxo completo de operação humana permanece a homologar. |
| J — Curator | Importadores reais aceitaram ZIP do show e sintético. Sem alteração de seus fontes; novos gates e render final continuam pendentes no consumidor. |
| K — limpeza | Cópias temporárias: dry-run/negação, fonte protegida, confirmação, busy/lease/lock, hash, caminhos, reparse, colisão, falha de cópia/disco/recibo, cancelamento, quarentena e restauração. Nenhuma limpeza real foi iniciada. |

## Falhas intermediárias preservadas e corrigidas

Os relatórios focados guardam falhas reais encontradas: master obsoleto após derivação semântica; aprovação recursiva do contrato Story; CID compartilhado por caracteres Unicode; fixture de GUI sem os novos atributos; schema de dossiê rejeitando SHA literal sintético; e verificador aceitando export sem PDFs após reindexação. Não foram tratadas como aprovação. As correções e testes de regressão correspondentes passaram na execução integrada final.

Uma tentativa inicial da chamada integrada usou `test_r6_camera_performer.py`, nome inexistente: nenhum teste foi coletado e o comando falhou. O nome correto, `test_r6_camera_performer_handoff.py`, foi usado no comando final acima. A tentativa global de pytest do agente de câmera também falhou porque pytest só estava no `.venv`; nada foi instalado.

Não foram executados: pipelines completos, download de vídeo/pesos, instalação de pacotes, serviços pagos, Ollama/GPU para regressão, publicação, aprovação humana, renderização social final ou novos canários do vídeo original. As análises históricas, inclusive João Gordo, não são prova de execução audiovisual deste código.
