# Reestruturação do L.D.PORTO — 2026-10-12

Entrega de engenharia com validação offline. A infraestrutura antiga saiu do
projeto ativo; os engines existentes, caminhos públicos e gates foram preservados.
Homologação acústica, visual e editorial real é uma pendência distinta.

## A. Arquitetura e base de trabalho

Diretório: `C:\Users\leone\Documentos\Meus Projetos\LDPORTO_VIDEO_ANALYZER`.
Branch: `baseline/ldporto-20261012-prompt01`; HEAD inicial: `2f4634f`.
Não houve commit, troca de branch, staging, reset ou manipulação direta de `.git`.

Antes das mudanças, `orquestrador.py` e `automacao/prompts/ETAPA_01.txt` já estavam
excluídos. Os três `.package/PROJECT_EXPORT_*` estavam modificados, e
`automacao/execucao/` continha uma auditoria anterior não versionada. Essas mudanças
foram identificadas e preservadas. Os hashes iniciais estão em
[inventory_before.json](inventory_before.json); a conferência final fica em
[final_integrity.json](final_integrity.json).

Havia uma GUI Python e o serviço Ollama abertos; não havia pytest nem análise
identificados em execução. Nenhum processo do usuário foi encerrado.

O inventário inicial registrou 1251 arquivos fora das raízes protegidas, incluindo
522 arquivos em `automacao/`. `.git`, `.venv`, modelos, mídias de entrada, análises e
pacotes locais foram registrados por metadados de raiz, sem varrer seus conteúdos.
Essa restrição evita ler dados pessoais/pesos como se fossem lixo técnico.

| Antes | Depois | Motivo |
| --- | --- | --- |
| GUI/CLI na raiz; engines em `src/ldporto/` | Mesmos caminhos | Preservar contratos e consumidores |
| Ferramentas em `scripts/windows`, `dev`, `export` | Mesmas implementações públicas | Wrappers ainda têm consumidores reais |
| Infraestrutura e cópias de fontes em `automacao/` | Legado fora do projeto | Aposentadoria operacional autorizada |
| ZIPs históricos sob automação | `src/tests/fixtures/historical_evidence/` | Regressão independente com os mesmos bytes |
| Auditoria/checkpoint anterior sob automação | `docs/archive/automation_20261012/` | Histórico identificado, sem executor |
| Relatório anterior na raiz | `docs/archive/FINAL_HOMOLOGACAO_20261009.md` | Separar prova anterior de validação atual |
| README acumulando releases anteriores | README operacional e `docs/README.md` | Referência principal clara por finalidade |

Foram mantidos `requirements/`, `config/`, `schemas/`, as pastas pessoais existentes
e `src/tests/fixtures/autopilot_historico/`. O Prompt 02 continua byte a byte nessa
fixture e é referenciado em `docs/briefings/`, sem duplicar a coleção ou criar fila.
Não se impôs a árvore conceitual sugerida sobre a arquitetura já modular.

## B. Limpeza, backup e proveniência

Backup externo:

`C:\Users\leone\Documentos\Meus Projetos\LDPORTO_LEGACY_BACKUP_20261012\orquestrador_legado.zip`

SHA-256:

`9263b50c70791968212b966d7c3415de8cfba82fb4e154a5875615cce106971c`

São 528 entradas verificadas individualmente por SHA-256, além da verificação CRC
do ZIP. Manifestos interno/externo, checksum e relação completa estão em
[backup.json](backup.json) e na pasta externa. A validação procurou nomes protegidos
e assinaturas de credenciais também nos ZIPs internos. Não se incluiu `.env`,
credenciais, `.venv`, `.git`, modelos ou mídias originais nesse procedimento.
Os dois arquivos previamente excluídos foram arquivados a partir dos blobs Git
`2f4634f`, exclusivamente como histórico; nenhum código foi restaurado sobre fontes.

O comando combinado de limpeza foi rejeitado pela revisão automática antes da
execução. A alternativa executada foi mover a árvore original para
`LDPORTO_LEGACY_BACKUP_20261012/retired_working_tree`, após verificar o ZIP. Assim,
nenhum apagamento recursivo foi necessário. Os caminhos absolutos de origem e
destino foram validados antes de cada movimentação no PowerShell.

[cleanup.json](cleanup.json) lista cada arquivo retirado/movido, motivo e hash.
Foram feitas 17 movimentações de evidências/documentos para seus locais definitivos.
As cópias de código da auditoria anterior, estados, logs, snapshots e schema de
execução ficaram no arquivo externo. Também saíram do projeto ativo:

- `src/tests/test_autopilot_orquestrador.py`: 12 testes do executor aposentado.
- `scripts/dev/baseline_etapa01.py`: produz baselines exclusivamente da antiga fila.
- `scripts/dev/verificar_liberacao_etapa66.py`: depende de estados/locks de etapas.
- Dois bytecodes exclusivos dos módulos aposentados, conservados na árvore externa.

Não foram encontradas duplicações de conteúdo entre documentação, scripts e
fixtures originais. A inspeção AST não encontrou funções idênticas grandes nem
imports relativos para módulos ausentes; não foi encontrado arquivo existente
versionado maior que 1 MB. [code_audit.json](code_audit.json) registra o alcance
preciso. Isso não constitui prova universal de ausência de código morto ou imports
dinâmicos. Componentes desconhecidos e caches funcionais foram preservados.

Não havia dependência de terceiros exclusiva do executor a eliminar nos grupos de
requirements; suas bibliotecas padrão continuam utilizadas pelo Analyzer. Não se
removeu uma dependência apenas para reduzir a lista.

## C. Independência da infraestrutura aposentada

`orquestrador.py` e `automacao/` estão ausentes do projeto ativo. Não foram executados
nem recriados executor, fila, estados, locks, aprovações DONE/ALREADY_OK ou snapshots
automáticos. `AGENTS.md` foi atualizado para desenvolvimento direto com Git/testes.

Os consumidores legítimos dos ZIPs foram atualizados nos testes de explicabilidade,
replay editorial, handoff e palavras incertas. `audit_qa.py` protege a nova pasta de
fixtures contra escrita. A integridade dos 52 prompts históricos e dos dois ZIPs é
testada sem importar qualquer executor. Os manifestos `ORIGEM.json` preservam as
origens anteriores e os hashes atuais dos mesmos bytes.

Ferramentas de auditoria/recuperação funcionais foram mantidas. Referências históricas
em `round62_audit.py` e o contrato fixado de `curation_recovery.py` agora apontam ao
arquivo histórico. O snapshot Stage 63 já estava ausente: essa recuperação continua
bloqueada quando exige aquela evidência; não se substituiu o checksum nem o gate.
Isso é uma limitação de recuperação histórica, não dependência do executor ativo.

[verification.json](verification.json) registra 100 módulos importados sem falha,
`analyze.py --help`, `exportar_ldporto.py --help` e `compare_runs.py --help` com exit 0,
e inicialização de Tk/App oculta com atualização Ollama suprimida. Não houve carga de
pesos, inferência ou execução de pipeline para essa prova. O pytest completo também
exercita exportação para diretórios temporários, contratos, replays e GUI sintética.

## D. Melhorias funcionais e limites

| Prioridade | Problema/causa constatada | Implementação e arquivos | Evidência e limite |
| --- | --- | --- | --- |
| P0 ASR | `language: pt` forçava português; idioma do backend era descartado | `config.py`, YAML, `transcription.py`, `inference_smoke.py`: auto, `transcribe` explícito, multilíngue, idioma desconhecido `null`, proveniência por hipótese | 32 novos testes ASR; a causa acústica exata de “frutas” não foi confirmada |
| P0 fidelidade | Import alterava o objeto recebido; alinhamento/segmentação perdiam metadados | Import por cópia, âncoras literais/timestamps originais, traduções separadas; `diarization.py`, `pipeline.py`, `targeted_asr.py` | PT/EN/mistura sintéticos; nenhum texto foi corrigido por adivinhação |
| P0 revisão | Escolha clean por probabilidade permitia texto divergente; multipass sem limite total claro | Original preservado em divergência textual/idiomática; alternativas e avisos; limites de 16 chamadas/180 segundos de áudio revisado | Orçamentos validados com fixtures; não equivalem a limite de latência de GPU |
| P0 semântica | Incerteza se perdia na projeção, junção de tópicos e expansão de candidatos | `semantic.py` e `understanding.py`: dados originais e revisão passam por prompts, caches, tópicos e candidatos finais | Regressões de tópico mesclado e fronteira incerta; nenhum score recalibrado |
| P1 visão | Formato YOLO esperado não ficava explícito no diagnóstico | `vision.py`: caminho tentado, `.pt`, `detect`, classe 0, motivo específico; configuração/dispositivo/fallback existentes preservados | Backend ausente/inválido testado com mocks; recall/YOLO/CUDA reais não medidos |
| P1 Active Speaker | Colisão simultânea anulava pessoa mas conservava status/método/confiança de aceitação | `active_speaker.py`: estado UNRESOLVED, confiança aceita anulada e causa específica propagada | Testes positivos/sequenciais, colisão, abstinência; sincronismo real pendente |
| P1 câmera | Auditoria não distinguia sempre proposta de enquadramento efetivamente entregue | `camera_evidence.py`, `camera_director.py`: proposta/entrega por janela, motivos e agregados de supressão/rejeição | Testes de hold, perda de rosto e crop inseguro; movimentos não foram forçados |
| P1 Qwen | Telemetria incompleta e chamadas de reparo podiam esconder custo anterior | `ollama_local.py`, `semantic.py`: carga/prompt/geração separados, TPS, bytes, falhas/reparos, cobertura de medições e números finitos | API simulada e benchmark CPU; `max` e limites originais preservados |
| P1 editorial | Resultado vazio não tinha categoria global clara | Novo `editorial_outcome.py`: nenhum elegível, evidência insuficiente, vídeo curto, erro técnico, baixa qualidade; `reports.py` e GUI propagam diagnóstico final | Critérios, scores, limites de duração e gates mantidos |
| P1 handoff | Projeção descartava idioma/revisão; faltavam traduções/proveniência exportáveis | `second_curation_export.py`, `reports.py`, `handoff.py`, `compact_artifacts.py`: sidecars separados, âncoras, referências, SHA-256 e guardas contra texto traduzido/reescrito como original | ZIPs rehashados incoerentes e sidecars adulterados são rejeitados |
| P2 GUI | Revisão global podia mostrar 99%/etapa 100%; ETA misturava configurações diferentes | `progress.py`, `runtime_metrics.py`, `semantic.py`, `app.py`: fase semântica explícita, reserva de 5% até sucesso final, ETA por configuração/trabalho equivalente | Relógio/eventos sintéticos e inicialização Tk; interação humana extensa pendente |

Detalhes e comandos de cada bloco: [ASR](asr_audit.md),
[visão/câmera](vision_integrity.md), [runtime](runtime_review.md).

O idioma inicial detectado pertence ao bloco; o backend instalado não expõe idioma
verificado para cada segmento multilíngue. A fala pode permanecer com idioma `null`
e uma pista de bloco. Isso é representado como limitação, sem inventar precisão.
Traduções importadas referenciam as âncoras originais, mesmo quando a diarização
reagrupa os IDs canônicos. Não foi acrescentada geração automática de traduções.

A nova verificação de TXT/SRT expôs uma diferença LF/CRLF no Windows. Os writers
usam LF explícito e o validador aceita apenas a equivalência de quebras de linha;
texto literal, timestamps e marcadores de original continuam verificados.

Instrumental “Eu Não Vou Parar”, prioridade da voz, preservação da música original,
marcas d'água e exportação vertical tiveram seus módulos/contratos preservados.
Nenhuma transformação de áudio/renderização foi imposta à análise perceptiva.

## E. Testes executados

O baseline fornecido **1627 passed / 4 skipped / 0 failed**, commit `2f4634f`, é
histórico. O título do commit menciona outra contagem; os resultados novos abaixo
são obtidos de execução e JUnit, sem reinterpretar registros anteriores.

| Execução | Resultado | Tempo/alcance |
| --- | --- | --- |
| Primeira suíte original | 1 erro de coleta | 0,56 s; import do executor já excluído; exit não persistido no registro inicial |
| Base atual antes dos fontes | 1616 passed, 3 skipped, exit 0 | 189,62 s; somente o módulo aposentado ignorado |
| Fixtures/migração histórica | 36 passed | 8,61 s; caminhos, hashes, replay, handoff e auditoria |
| Visão/câmera | 155 passed | 1,50 s; 12 testes novos e contratos existentes |
| ASR/semântica inicial finalizada | 132 passed | 2,93 s; sem inferência real |
| ASR/candidatos após revisão cruzada | 136 passed | 3,92 s; propagação na fronteira final |
| Runtime/handoff/recibos direcionados | Ver relatório runtime | Inclui falhas intermediárias reais e correções |
| Primeira regressão completa | 1710 passed, 3 skipped, exit 0 | 203,09 s; uma fixture mudou durante a execução; first_full_run.json |
| Regressão completa final | **1711 passed, 3 skipped, 0 failed, 0 errors; exit 0** | **204,48 s**; sem filtros/ignores e sem alteração de fonte durante a suíte |

Foram retirados 12 testes exclusivos do mecanismo aposentado, com íntegra no backup.
Dois testes independentes preservam os requisitos de proveniência das fixtures.
O teste de allowlist da raiz deixou de aceitar o executor aposentado. Os testes
funcionais anteriores permaneceram na suíte; apenas os caminhos dos quatro
consumidores de evidência foram atualizados. Oito novos testes de relatório cobrem
sidecars assinados nas rotas com/sem exportação automática.

Contagens completas, casos adicionados/removidos/modificados, comandos, exit codes,
skips e duração final: [tests_summary.json](tests_summary.json),
[after_full_run.json](after_full_run.json) e os JUnits/logs locais.
Contagens direcionadas se sobrepõem; não devem ser somadas ao resultado completo.

Foram adicionados **95 casos**: ASR 32, visão/câmera 12, runtime/handoff 41,
proveniência histórica 2 e recibos de relatório 8. Nenhum caso funcional da base
ativa foi removido. O total final é 1714 casos coletados. Os três skips mantidos são
dois testes que exigem privilégio de symlink no Windows e um canário Tesseract opt-in.
Não houve falha nem erro final; os fontes permaneceram congelados durante a suíte.

A revisão final também corrigiu a projeção de palavras legadas sem `raw`, omitindo
esse campo quando ausente em vez de exportar `null` incompatível com o consumidor.
A indicação da revisão global na GUI permanece neutra quando pode haver cache.
Uma nova regressão completa congelada valida os bytes finais após essas correções.

Houve uma falha intermediária de integração real (LF/CRLF) e erros iniciais em fixtures
novas, registrados nos relatórios de cada bloco. Não foram ocultados com filtros ou
afrouxamento de gates. A conclusão de regressão depende do resultado final registrado.

## F. Performance

Os 289,4 segundos de semântica em aproximadamente 19 segundos de vídeo são uma medida
fornecida do teste anterior. Nenhuma execução equivalente de Qwen/Whisper/YOLO real
foi feita nesta entrega: tempo posterior e ganho real permanecem `null`.

A instrumentação distingue carregamento, avaliação de prompt e geração, request
bytes, tokens observados, TPS e reparos. Ausência de métrica permanece `null`; uma
falha local anterior à requisição não conta como inferência. Somas/divisões inválidas
não produzem certeza artificial. Cache semântico, prompt compacto opt-in, orçamento
de contexto e perfil `max` foram preservados. A/B real é necessário antes de mudar
esses defaults. O [benchmark sintético](runtime_cpu_overhead.json) mede somente custo
CPU de instrumentação/serialização, sem estimar a aceleração de inferência real.

## G. Situação e homologação restante

| Item | Situação | Critério restante |
| --- | --- | --- |
| Aposentadoria operacional e backup | Resolvido | Ausência no workspace, bytes preservados, imports/CLIs verificados |
| Organização e proveniência histórica | Resolvido | Arquivos úteis preservados, fontes duplicadas retiradas do ativo |
| Contratos de original/tradução e propagação de incerteza | Resolvido no alcance offline | Regressões e validação de adulteração; não prova fidelidade acústica |
| Qualidade ASR PT/EN/mista em conteúdo real | Não validado | Mesma fonte/configuração, audição humana e referência anotada; não adivinhar “frutas” |
| YOLO/NVIDIA, pessoa sentada, oclusão/reentrada | Não validado | Modelo `.pt` local confiável e goldset com medições reais |
| Active Speaker real e sobreposição | Parcialmente resolvido | Consistência corrigida; validar sincronismo, falso vínculo, offscreen e ambiguidades |
| Ganho editorial de câmera/Smart Zoom | Parcialmente resolvido | Auditoria implementada; revisar previews e gain de movimentos reais |
| Latência Qwen antes/depois | Pendente | Benchmark equivalente com fonte/modelo/config/prompt/cache controlados |
| Integração audiovisual ponta a ponta | Não validado | ASR, diarização, OCR, visão e semântica reais, sem confundir mocks com inferência |
| Recuperação do contrato histórico Stage 63 | Bloqueado | Snapshot fixado ausente; manter checksum e demais requisitos |
| GUI interativa prolongada e interrupção real | Pendente | Teste manual de longa duração, parada/reprocessamento e abertura de resultados |
| Preview/aprovação/publicação | Pendente | Gates humanos e evidências de renderização; nenhuma publicação automática |

Não se executaram pipelines completos, instalações, downloads de pesos ou serviços
pagos. Os resultados do João Gordo continuam identificados como build antigo. Uma
regressão verde comprova o alcance dos testes, não homologação audiovisual real.
