# Cross-repository P0 gate. Does not install anything or touch renderers.
# Optional -AnalysisDir causes real delivery of an ALREADY exported Analyzer ZIP.
param([string]$AnalysisDir = "", [string]$CuratorRoot = "")
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$analyzer = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$python = Join-Path $analyzer ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Analyzer Python .venv ausente: $python" }
$defaultCurator = Join-Path (Split-Path $analyzer -Parent) "LDPORTO_VIDEO_CURATOR"
$curator = if ($CuratorRoot) { $CuratorRoot } else { $defaultCurator }
if (-not (Test-Path -LiteralPath (Join-Path $curator "ldporto_studio\core.py") -PathType Leaf)) {
    throw "Curator nao encontrado. Use -CuratorRoot indicando o projeto existente."
}
$curator = (Resolve-Path -LiteralPath $curator).Path
function Assert-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step falhou com exit code $LASTEXITCODE" }
}
Push-Location $analyzer
try {
    $branch = (& git.exe branch --show-current).Trim()
    Assert-Exit "Git Analyzer branch"
    if ($branch -ne "develop") { throw "Analyzer deve usar develop, encontrado: $branch" }
    & $python -c "import sys; print('Python',sys.version.split()[0]); assert sys.version_info[:2]==(3,11)"
    Assert-Exit "Python 3.11"
    Write-Host "[1/4] Testes da entrega Analyzer - sinteticos e ZIP oficial sintetico"
    & $python -m pytest -q src/tests/test_local_curator_handoff.py
    Assert-Exit "Handoff Analyzer"
    Write-Host "[2/4] Testes focais GUI Analyzer"
    & (Join-Path $analyzer "scripts\windows\testing\VALIDAR_P0_GUI.ps1")
    Assert-Exit "GUI Analyzer"
}
finally { Pop-Location }
Push-Location $curator
try {
    $branch = (& git.exe branch --show-current).Trim()
    Assert-Exit "Git Curator branch"
    if ($branch -ne "develop") { throw "Curator deve usar develop, encontrado: $branch" }
    if (-not (Select-String -LiteralPath ".gitignore" -Pattern '^\s*/input/\s*$' -Quiet)) {
        throw "Curator .gitignore nao protege /input/"
    }
    $tracked = @(& git.exe ls-files -- input)
    Assert-Exit "Curator tracked input"
    if ($tracked.Count -ne 0) { throw "Arquivos de input estao no Git. Pare para investigar." }
    Write-Host "[3/4] Inspetor de inbox Curator - somente leitura"
    & $python -m unittest discover -s tests -p test_analyzer_inbox.py -v
    Assert-Exit "Inspetor Curator"
}
finally { Pop-Location }
if ($AnalysisDir) {
    Write-Host "[4/4] Teste fisico do ZIP oficial existente, sem inferencia"
    Push-Location $analyzer
    try {
        $analysisPath = (Resolve-Path -LiteralPath $AnalysisDir).Path
        & $python scripts/dev/retry_curator_delivery.py --analysis-dir $analysisPath --curator-root $curator
        Assert-Exit "Entrega local real"
        $receipt = Get-Content -LiteralPath (Join-Path $analysisPath "curator_delivery.json") -Raw | ConvertFrom-Json
        if ($receipt.delivery_status -notin @("DELIVERED", "ALREADY_DELIVERED")) {
            throw "Entrega nao confirmada; consulte curator_delivery.json"
        }
        $destination = $receipt.destination
    }
    finally { Pop-Location }
    Push-Location $curator
    try {
        & $python -m ldporto_studio.analyzer_inbox --path $destination
        Assert-Exit "Curator ZIP inspection"
        Write-Host "ZIP fisico conferido em: $destination" -ForegroundColor Green
    }
    finally { Pop-Location }
} else {
    Write-Host "[4/4] Entrega fisica opcional. Informe -AnalysisDir para usar ZIP real ja existente."
}
Write-Host "Gates concluidos. Nenhum render ou aprovacao humana foi acionado." -ForegroundColor Green
