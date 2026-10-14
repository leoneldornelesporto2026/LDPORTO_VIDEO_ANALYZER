# Comandos e evidências reais — 2026-10-12

Executados no projeto atual pelo PowerShell, usando a `.venv` existente. Comandos
inline Python de auditoria/backup não constituem um novo executor de desenvolvimento.

## Inspeção inicial

```powershell
Get-Location
git status --short --branch --untracked-files=normal
git branch --show-current
git log -1 --format='%h %s'
git diff --stat
git ls-files --others --exclude-standard
Get-Content -LiteralPath AGENTS.md -Encoding UTF8 -Raw
Get-ChildItem -Force
Get-CimInstance Win32_Process
rg --files
rg -n 'orquestrador|automacao|MAPA_ETAPAS|estado\.json' src/ldporto src/tests scripts
```

Leitura do anexo do usuário, configuração, engines, entrypoints, docs e testes por
`Get-Content`/`rg`. A listagem de processos foi filtrada para Python/pytest/FFmpeg,
Ollama e Codex; nenhum processo do usuário foi encerrado. Resultados iniciais e
classificações: `inventory_before.json` e relatório técnico.

## Baseline real antes das mudanças de código

```powershell
.venv\Scripts\python.exe -m pytest -q --junitxml=docs/reports/restructuring_20261012/before_collection.xml
.venv\Scripts\python.exe -m pytest -q --ignore=src/tests/test_autopilot_orquestrador.py --junitxml=docs/reports/restructuring_20261012/before_active.xml
```

O primeiro comando encontrou um erro de coleta porque o arquivo do executor já
estava excluído antes da sessão; seu exit não foi persistido pelo wrapper inicial.
O segundo foi capturado com stdout/stderr, duração e exit 0 em
`before_active_run.json`/`.log`: 1616 passed, 3 skipped, 189,62 s.

## Inventário, backup e retirada

Scripts inline por `.venv\Scripts\python.exe -` executaram `os.walk`, classificação
por finalidade, análise AST, hashes SHA-256, leitura dos blobs históricos com
`git show 2f4634f:...`, criação de ZIP por `zipfile.ZipFile`, verificação CRC e hash
de cada membro. As raízes protegidas não foram varridas. As entradas de arquivo
foram examinadas para nomes/assinaturas de segredo, inclusive arquivos ZIP internos.

O primeiro comando combinado de movimentação/remoção foi rejeitado pela política
automática antes de executar. A retirada executada usou `Resolve-Path`,
`[IO.Path]::GetFullPath`, checagem dos prefixos absolutos autorizados,
`New-Item -ItemType Directory` e `Move-Item -LiteralPath -Destination` em PowerShell.
Não houve `Remove-Item` executado. Destinos existentes não foram sobrescritos.
`backup.json` e `cleanup.json` listam bytes, hashes, origens e destinos reais.

## Verificações direcionadas

```powershell
.venv\Scripts\python.exe -m pytest -q src/tests/test_historical_fixture_provenance.py src/tests/test_stage17_editorial_replay.py src/tests/test_stage18_handoff_audit.py src/tests/test_stage19_uncertain_words.py src/tests/test_stage62_round_homologation.py
.venv\Scripts\python.exe -m pytest -q src/tests/test_transcription_report_integrity.py src/tests/test_stage65_execution_receipts.py src/tests/test_stage13_explainability.py
```

Respectivamente: 36 passed em 8,61 s; 53 passed e 1 failed em 16,05 s na integração
inicial, que expôs LF/CRLF no pacote. As correções foram depois cobertas pelos testes
direcionados de runtime e pelas duas regressões completas. Comandos detalhados dos
agentes, primeiras falhas, correções e logs: `asr_audit.md`, `vision_integrity.md` e
`runtime_review.md`. Esses conjuntos se sobrepõem; não somar suas contagens.

## Imports, GUI e entrypoints

```powershell
.venv\Scripts\python.exe analyze.py --help
.venv\Scripts\python.exe exportar_ldporto.py --help
.venv\Scripts\python.exe compare_runs.py --help
git diff --check
```

As três CLIs retornaram exit 0. Um script inline importou os 100 módulos ativos
`ldporto.*`, instanciou `Tk` oculto e `App`, suprimiu a atualização de rede Ollama,
abriu a tela de execução, enviou um evento sintético e destruiu a janela. Essa
verificação não é execução de análise nem teste humano. Registros: `verification.json`.
A inspeção AST de 273 fontes Python não encontrou sintaxe inválida, import relativo
de módulo ausente nem grupos grandes de função AST idêntica; `code_audit.json`.
Versões instaladas foram lidas por `importlib.metadata`, sem carga de modelo;
`runtime_versions.json` não homologa CUDA nem inferência.

## Regressões completas

```powershell
.venv\Scripts\python.exe -m pytest -q -rs --junitxml=docs/reports/restructuring_20261012/after_full.xml
```

Executado duas vezes, sem filtros nem módulos ignorados. A primeira execução foi
preservada como `first_full.xml/.log`, `first_full_run.json` e
`source_before_first_full.json`: 1710 passed, 3 skipped, 203,09 s. Houve alteração
de uma fixture durante essa execução; uma compatibilidade legada de `raw` também
foi corrigida em seguida. O resultado final congelado fica em `after_full_run.json`,
`after_full.xml/.log` e `source_before_final_tests.json`. Os wrappers registraram
argv, exit, duração, casos JUnit e hashes dos fontes antes/depois.

O benchmark de `runtime_cpu_overhead.json` usou payloads e contadores sintéticos,
sem chamar API/modelos. O perfil `max` permaneceu com contexto 32768 e saída 6144.

Não foram executados commits, instalações, downloads de pesos, pipelines completos,
inferência audiovisual real, serviços pagos ou publicação de conteúdo.
