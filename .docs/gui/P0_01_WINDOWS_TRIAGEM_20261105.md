# P0-01 — Triagem Windows 2026-11-05

Baseline testada: `6c8dec99c54d38b03e8d03dcada648f1216a49e0`.
Python 3.11.9; pytest 9.1.1. Resultado real: 15/15 testes P0,
39 passed + 12 subtests passed no gate focal; suite completa
**2622 passed, 10 failed, 5 skipped, 28 subtests passed** em 466.82s.

- **7 falhas:** ausentes CHATGPT_REVIEW.zip e SECOND_CURATION_READY.zip
  em src/tests/fixtures/historical_evidence/. Os arquivos nao foram
  versionados em develop (gitignore ignora *.zip). Requerem bytes originais
  e os SHA256 registrados em ORIGEM.json. Nunca gerar substitutos sinteticos.
- **1 falha:** stage55_commercial_synthetic.json foi convertido para CRLF
  pelo checkout Windows. SHA256 LF original
  `81298196b4006f83e1cf3bc9c25dd82b243fbcf877e294f0c0122c4dfba9b164`;
  CRLF coincide exatamente com a falha
  `fd475cdc3f32b856762a601b5b1304ae38c6ee88b98afcde316ead849fadd760`.
  .gitattributes agora define eol=lf especificamente nesse arquivo.
- **2 falhas:** testes legados exigem encaminhamento
  `call "%~dp0..." %*` nos diagnosticos. Os wrappers e scripts
  canonicos em scripts/windows/diagnostics foram restaurados.

Para restaurar os ZIPs, executar o script PowerShell
`scripts/windows/testing/RESTAURAR_FIXTURES_HISTORICAS.ps1` com
`-SearchRoot` ou caminhos `-ReviewZip` e `-CurationZip`.
A restauracao confere tamanho e SHA256, nao substitui arquivos existentes.

Depois do pull, se o JSON nao tiver edicoes suas:
```powershell
git status --short -- src/tests/fixtures/stage55_commercial_synthetic.json
git restore --source=HEAD --worktree -- src/tests/fixtures/stage55_commercial_synthetic.json
git check-attr text eol -- src/tests/fixtures/stage55_commercial_synthetic.json
Get-FileHash src/tests/fixtures/stage55_commercial_synthetic.json -Algorithm SHA256
```
Somente apos evidencias reais Windows e todos os ZIPs integrais
a suite pode ser considerada aprovada. Nao alterar main/release.

## Preflight adicional de 2026-11-05

O validador P0 com -FullSuite passa a verificar primeiro existencia, tamanho e
SHA256 dos dois ZIPs originais e da fixture stage55 LF. Sem integridade
comprovada interrompe antes da longa suite, sem ignorar nenhum teste.

## Correcao complementar de 2026-11-05 (apos revalidacao Windows)

O Windows aprovou 57 testes, ignorou 1, aprovou 14 subtestes e encontrou
mais 2 falhas focais. O teste de allowlist da raiz nao incluia .gitattributes:
a configuracao Git era valida, mas o teste tinha inventario desatualizado.
A lista foi corrigida incluindo .gitattributes e retirando CHANGELOG_V43.md,
ja movido para .docs/.

O JSON stage55 continuou CRLF mesmo apos git restore. Para preservar
os bytes exatos, .gitattributes passou a marcar somente essa fixture
como -text, desabilitando qualquer conversao automatica de EOL.
Adicionada ferramenta REPARAR_EOL_FIXTURE_STAGE55.py que somente transforma
CRLF em LF se o SHA256 resultante for exatamente o registrado; nenhuma
mudanca de conteudo ou atualizacao do hash esperado e permitida.

No Windows, depois de git pull, execute explicitamente:

~~~powershell
.\.venv\Scripts\python.exe scripts/windows/testing/REPARAR_EOL_FIXTURE_STAGE55.py --repair
Get-FileHash src/tests/fixtures/stage55_commercial_synthetic.json -Algorithm SHA256
.\.venv\Scripts\python.exe -m pytest -q src/tests/test_v43_runtime.py src/tests/test_windows_batch_paths.py src/tests/test_stage55_commercial_evidence.py src/tests/test_fixture_newline_policy.py
~~~

Os ZIPs R4.9-S4 permanecem ausentes. Isso ainda bloqueia a suite historica,
independentemente do resultado das correcoes focais. Nao criar substitutos.

## Nova evidencia Windows — 2026-11-05

Commit testado: `de79399a807f96f19f1640f8eea165ae20c5a78a`.
Operador confirmou `git status --short` vazio antes do pull, branch develop,
e correção da fixture stage55 com o script verificando
SHA256 `81298196b4006f83e1cf3bc9c25dd82b243fbcf877e294f0c0122c4dfba9b164`.

Resultado da regressao focada Windows:
**65 passed, 1 skipped, 14 subtests passed, 1 warning em 6.31s.**
As duas falhas anteriores (allowlist e CRLF) foram resolvidas nessa bateria.
O warning e um `DeprecationWarning: invalid escape sequence '\\.'` do docstring
do utilitario de reparo; corrigido tornando a docstring uma raw string.

**Status de aceite P0-01: parcial.** Os testes focais foram comprovados,
mas a suite completa segue bloqueada pela falta de
`CHATGPT_REVIEW.zip` e `SECOND_CURATION_READY.zip` originais.
Tambem falta homologar abertura e navegacao visual da GUI.
Nao desabilitar testes nem alterar hashes para conceder aceite.
