# Restore historical evidence ONLY from byte-identical local copies.
# Usage: .\scripts\windows\testing\RESTAURAR_FIXTURES_HISTORICAS.ps1 -SearchRoot "C:\Users\leone\Videos"
param(
    [string]$ReviewZip = "",
    [string]$CurationZip = "",
    [string]$SearchRoot = ""
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$targetDir = Join-Path $root "src\tests\fixtures\historical_evidence"
$items = @(
    @{ Name="CHATGPT_REVIEW.zip"; Bytes=[long]26956533; Hash="5a9da201f984d63de2c68dbd9aee4c03365b9e0815b1fb041130d4da02b5f073"; Explicit=$ReviewZip },
    @{ Name="SECOND_CURATION_READY.zip"; Bytes=[long]1864261; Hash="8339e90f41cce13f93bc61cc6417cecc1058ad37df272d194d7f62060d860349"; Explicit=$CurationZip }
)
function Test-Exact {
    param([string]$Path, [hashtable]$Item)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    if ((Get-Item -LiteralPath $Path).Length -ne $Item.Bytes) { return $false }
    return ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ieq $Item.Hash)
}
$missing = @()
foreach ($item in $items) {
    $target = Join-Path $targetDir $item.Name
    if (Test-Path -LiteralPath $target -PathType Leaf) {
        if (-not (Test-Exact -Path $target -Item $item)) {
            throw "Fixture existente com integridade divergente. Preservada: $target"
        }
        Write-Host ("VERIFICADO: " + $item.Name) -ForegroundColor Green
        continue
    }
    $candidates = [System.Collections.Generic.List[string]]::new()
    if ($item.Explicit) { $candidates.Add($item.Explicit) }
    foreach ($base in @((Join-Path $root "automacao\evidencias"), (Split-Path $root -Parent))) {
        $candidate = Join-Path $base $item.Name
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { $candidates.Add($candidate) }
    }
    if ($SearchRoot) {
        if (-not (Test-Path -LiteralPath $SearchRoot -PathType Container)) {
            throw "Pasta -SearchRoot ausente: $SearchRoot"
        }
        Get-ChildItem -LiteralPath $SearchRoot -Recurse -File -Filter $item.Name -ErrorAction SilentlyContinue |
            ForEach-Object { $candidates.Add($_.FullName) }
    }
    $found = $null
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-Exact -Path $candidate -Item $item) { $found = $candidate; break }
    }
    if (-not $found) {
        Write-Warning ("Original ausente: " + $item.Name)
        $missing += $item.Name
        continue
    }
    if (-not (Test-Path -LiteralPath $targetDir)) {
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    }
    $temporary = Join-Path $targetDir (".verify-" + [guid]::NewGuid().ToString("N") + ".tmp")
    try {
        Copy-Item -LiteralPath $found -Destination $temporary -ErrorAction Stop
        if (-not (Test-Exact -Path $temporary -Item $item)) {
            throw "Erro de integridade na copia; original preservado: $found"
        }
        Move-Item -LiteralPath $temporary -Destination $target -ErrorAction Stop
        Write-Host ("RESTAURADO (SHA256 OK): " + $item.Name) -ForegroundColor Green
    }
    finally {
        if (Test-Path -LiteralPath $temporary -PathType Leaf) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}
if ($missing.Count -gt 0) {
    Write-Host "Ainda faltam ZIPs originais. Use -SearchRoot ou -ReviewZip e -CurationZip."
    exit 2
}
Write-Host "Originais historicos conferidos: 2/2." -ForegroundColor Green
