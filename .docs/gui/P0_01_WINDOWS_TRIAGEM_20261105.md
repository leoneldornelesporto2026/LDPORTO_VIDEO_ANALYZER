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
