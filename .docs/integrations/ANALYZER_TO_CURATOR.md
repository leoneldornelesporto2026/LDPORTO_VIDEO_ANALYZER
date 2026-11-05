# Entrega automática Analyzer → Curator (contrato 1.0)

Implementação apenas na branch develop do LDPORTO_VIDEO_ANALYZER.
Evento de integração: ReportEngine.run, após a validação do estágio 21_second_curation_handoff
e após finalize_report_receipt, sem reabrir/editar o ZIP oficial.

## Localização

- Default: repositório irmão LDPORTO_VIDEO_CURATOR, sem caminho absoluto fixo.
- Alternativa: export.curator_delivery_root em config.yaml ou variável de ambiente LDPORTO_VIDEO_CURATOR_ROOT.
- Desabilitar explicitamente: export.curator_delivery_auto: false.
- Entrega: <Curator>/input/analyzer/<video_id>/<run_id>/.
- Colisão de mesmo run_id e hashes distintos: pasta <run_id>--sha-<12 hex>.
- O Curator deve conter .gitignore e ldporto_studio/core.py; input/ ignorado pelo Git.

## Segurança

O exportador oficial build_core_package e validate_core_package continuam únicos.
O módulo local_curator_handoff valida novamente ZIP e SHA256 antes/depois da cópia.
Copiar para pasta temporária e renomear a pasta inteira quando completa.
Nenhuma entrega anterior é sobrescrita. Um ZIP já entregue e conferido é idempotente.
Falhas produzem curator_delivery.json em analysis/<run>, com DELIVERY_BLOCKED.
O ZIP original e os vídeos não são removidos ou modificados.

A entrega é de evidências, NÃO é formato R57 do Studio atual.
O Curator recebe ANALYZER_TO_CURATOR_HANDOFF.json e README_HANDOFF.md.
O importador continua CURATOR_IMPORT_PENDING. Nenhuma aprovação ou render foi criada.
Metadados só são transportados quando presentes no contrato canônico; faltas ficam nulas.

## Testes

Executar no Analyzer:

~~~powershell
git status --short
git pull --ff-only origin develop
.\.venv\Scripts\python.exe -m pytest -q src/tests/test_local_curator_handoff.py
.\scripts\windows\testing\VALIDAR_P0_GUI.ps1
~~~

Executar no Curator após pull da develop:

~~~powershell
python -m unittest discover -s tests -p test_analyzer_inbox.py -v
python -m ldporto_studio.analyzer_inbox --path ".\input\analyzer\<video_id>\<run_id>"
~~~

Para retentar uma entrega bloqueada sem rodar inferência, executar:

~~~powershell
.\.venv\Scripts\python.exe scripts/dev/retry_curator_delivery.py --analysis-dir "analysis\video_<id>"
~~~

Não é possível homologar entrega física em um computador Windows externo sem executar uma análise ou
reusar um ZIP original validado. Testes sintéticos de transporte não homologam conteúdo real.

## Gate integrado Windows

Na raiz do Analyzer, com ambos repositorios atualizados em develop:

~~~powershell
.\scripts\windows\testing\VALIDAR_ENTREGA_CURATOR.ps1
~~~

Para reutilizar um ZIP oficial ja exportado, sem inferencia de video:

~~~powershell
.\scripts\windows\testing\VALIDAR_ENTREGA_CURATOR.ps1 -AnalysisDir ".\analysis\video_<id>"
~~~

Opcional: -CuratorRoot aponta para o repo existente fora da pasta irma.
O script recusa outras branches, verifica /input/ ignorado e Git sem arquivos de input rastreados.
Sinteticos nao sao entrega fisica; somente -AnalysisDir faz copia real e verifica SHA no Curator.

## Confirmação na GUI e no CLI

O Analyzer exibe a confirmação de pacote entregue somente quando a cópia recebeu
DELIVERED ou ALREADY_DELIVERED. Inclui vídeo, ZIP, SHA256, destino, contagens
e CURATOR_IMPORT_PENDING. Erros geram DELIVERY_BLOCKED com o motivo,
sem eliminar o ZIP original do Analyzer.
