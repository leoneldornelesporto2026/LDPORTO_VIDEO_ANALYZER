# Backfill existing Analyzer R6 ZIPs without a new inference or YouTube download.
# Default: read-only inventory; -Aplicar explicitly enables validated atomic delivery.
[CmdletBinding()]
param(
    [switch]$Aplicar,
    [string]$ScanRoot = "",
    [string[]]$AnalysisDir = @(),
    [string]$CuratorRoot = ""
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$analyzer = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
$python = Join-Path $analyzer ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python virtualenv do Analyzer ausente: $python"
}
if ($Aplicar) {
    $branch = (& git.exe -C $analyzer branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne "develop") {
        throw "Aplicacao permitida somente na develop do Analyzer"
    }
    $curator = if ($CuratorRoot) { $CuratorRoot } else {
        Join-Path (Split-Path $analyzer -Parent) "LDPORTO_VIDEO_CURATOR"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $curator "ldporto_studio\core.py") -PathType Leaf)) {
        throw "Curator ausente; informe -CuratorRoot"
    }
    $curatorBranch = (& git.exe -C $curator branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $curatorBranch -ne "develop") {
        throw "Aplicacao permitida somente na develop do Curator"
    }
}
$arguments = @("scripts/dev/sync_historical_curator_delivery.py")
if ($ScanRoot) { $arguments += @("--scan-root", $ScanRoot) }
foreach ($dir in $AnalysisDir) { $arguments += @("--analysis-dir", $dir) }
if ($CuratorRoot) { $arguments += @("--curator-root", $CuratorRoot) }
if ($Aplicar) { $arguments += "--apply" }
Push-Location $analyzer
try {
    & $python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Inventario/entrega encontrou um bloqueio; verifique o relatorio JSON acima."
    }
} finally {
    Pop-Location
}
