# P0-01 Windows validation gate. No automatic dependency installation.
# Run from the repository root: .\scripts\windows\testing\VALIDAR_P0_GUI.ps1
# Optional: .\scripts\windows\testing\VALIDAR_P0_GUI.ps1 -FullSuite
param([switch]$FullSuite)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
function Assert-Success {
    param([string]$Stage)
    if ($LASTEXITCODE -ne 0) { throw "$Stage falhou (exit code $LASTEXITCODE)" }
}
Push-Location $root
try {
    if (-not (Test-Path $python)) {
        throw "Falta a .venv do projeto. Preserve o ambiente e use Python 3.11."
    }
    $branch = (& git.exe branch --show-current).Trim()
    Assert-Success "Git branch"
    if ($branch -ne "develop") { throw "Execute em develop (atual: $branch)" }
    Write-Host "Branch: $branch"
    & git.exe --no-pager log -1 --oneline
    Assert-Success "Git HEAD"
    & $python -c "import sys; print('Python', sys.version.split()[0], sys.executable); assert sys.version_info[:2] == (3, 11), 'Use Python 3.11'"
    Assert-Success "Python 3.11"

    Write-Host ""
    Write-Host "[1/3] Testes P0 GUI sem interface (stdlib)"
    & $python -m unittest discover -s src/tests -p test_p0_gui_baseline_contract.py -v
    Assert-Success "Classe P0 GUI"

    Write-Host ""
    Write-Host "[2/3] Verificacao do pytest"
    & $python -m pytest --version
    if ($LASTEXITCODE -ne 0) {
        throw "pytest nao instalado. Para instalar explicitamente: .\.venv\Scripts\python.exe -m pip install -r requirements\dev.txt"
    }

    Write-Host ""
    Write-Host "[3/3] Regressao focal da GUI"
    & $python -m unittest discover -s src/tests -p test_fixture_newline_policy.py -v
    Assert-Success "Regressao de integridade EOL"
    & $python -m pytest -q src/tests/test_r62_media_gui.py src/tests/test_stage54_ocr_gui.py src/tests/test_sol_v3_gui_review.py src/tests/test_windows_batch_paths.py
    Assert-Success "Regressao GUI"

    if ($FullSuite) {
        Write-Host ""
        Write-Host "[4/4] Preflight de integridade antes da suite completa"
        $expected = @(
            @{ File="src\tests\fixtures\historical_evidence\CHATGPT_REVIEW.zip"; Hash="5a9da201f984d63de2c68dbd9aee4c03365b9e0815b1fb041130d4da02b5f073"; Bytes=[long]26956533 },
            @{ File="src\tests\fixtures\historical_evidence\SECOND_CURATION_READY.zip"; Hash="8339e90f41cce13f93bc61cc6417cecc1058ad37df272d194d7f62060d860349"; Bytes=[long]1864261 },
            @{ File="src\tests\fixtures\stage55_commercial_synthetic.json"; Hash="81298196b4006f83e1cf3bc9c25dd82b243fbcf877e294f0c0122c4dfba9b164"; Bytes=[long]1598 }
        )
        foreach ($item in $expected) {
            $target = Join-Path $root $item.File
            if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
                throw ("Fixture nao encontrada: " + $target + ". Para os ZIPs use scripts\windows\testing\RESTAURAR_FIXTURES_HISTORICAS.ps1")
            }
            if ((Get-Item -LiteralPath $target).Length -ne $item.Bytes) {
                throw ("Tamanho divergente: " + $target + ". Preserve o original e confira a proveniencia.")
            }
            $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
            if ($actual -ine $item.Hash) {
                throw ("SHA256 divergente: " + $target + " (atual: " + $actual + ")")
            }
            Write-Host ("OK: " + $item.File)
        }
        Write-Host "Integridade aprovada. Iniciando suite completa..."

        & $python -m pytest -q src/tests
        Assert-Success "Suite completa"
    } else {
        Write-Host "Suite completa pendente. Use -FullSuite para o aceite."
    }
    Write-Host "P0-01: comandos selecionados aprovados. Validacao visual ainda pendente." -ForegroundColor Green
}
finally { Pop-Location }
