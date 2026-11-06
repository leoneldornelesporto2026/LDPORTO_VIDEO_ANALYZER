# Resume a REAL Analyzer run already completed to the R6 ZIP stage.
# Does NOT download or reanalyze video, repeat full suites, modify configs,
# change Git refs, delete unrelated files or publish any final media.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$AnalysisDir,
    [string]$MediaPath = "",
    [string]$CuratorRoot = "",
    [ValidateRange(1,5)]
    [int]$SmokeCount = 1
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$analyzer = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
$curator = if ($CuratorRoot) { (Resolve-Path -LiteralPath $CuratorRoot).Path } else {
    Join-Path (Split-Path $analyzer -Parent) "LDPORTO_VIDEO_CURATOR"
}
$folder = (Resolve-Path -LiteralPath $AnalysisDir).Path
$ap = Join-Path $analyzer ".venv\Scripts\python.exe"
$cp = Join-Path $curator ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $ap -PathType Leaf)) { throw "Analyzer .venv ausente" }
if (-not (Test-Path -LiteralPath $cp -PathType Leaf)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    $cp = if ($cmd) { $cmd.Source } else { $ap }
}
function Check-Exit([string]$step) {
    if ($LASTEXITCODE -ne 0) { throw "$step falhou (exit=$LASTEXITCODE)" }
}
foreach ($root in @($analyzer,$curator)) {
    $branch=(& git.exe -C $root branch --show-current).Trim()
    Check-Exit "Git branch"
    if ($branch -ne "develop") { throw "Branch diferente de develop: $root" }
}
$exportFile = Join-Path $folder "second_curation_export.json"
if (-not (Test-Path -LiteralPath $exportFile -PathType Leaf)) { throw "Recibo do ZIP original ausente: $exportFile" }
$export = Get-Content -LiteralPath $exportFile -Raw | ConvertFrom-Json
if (-not $export.path) { throw "Recibo sem pacote ZIP valido" }
$zip = [string]$export.path
if (-not [IO.Path]::IsPathRooted($zip)) { $zip = Join-Path $analyzer $zip }
if (-not (Test-Path -LiteralPath $zip -PathType Leaf)) { throw "ZIP nao encontrado: $zip" }
Write-Host "PILOTO R6: somente RETOMADA DO ZIP REAL, SEM INFERENCIA" -ForegroundColor Cyan
Write-Host "ZIP preservado: $zip"

# First distinguish a Windows directory-level denial from a temporary sharing
# violation, using only uniquely named, automatically cleaned probe folders.
Write-Host "[1/5] Windows: teste isolado de rename dentro da inbox Curator"
$diagnostic = Join-Path $analyzer "scripts\windows\testing\DIAGNOSTICAR_RENAME_CURATOR.ps1"
& $diagnostic -CuratorRoot $curator -VideoId "Eo2bUJcxASI"

Write-Host "[2/5] P0/P1: gate real existente, sem nova analise"
$real = Join-Path $analyzer "scripts\windows\testing\PILOTO_E2E_REAL.ps1"
& $real -AnalysisDir $folder -CuratorRoot $curator -SmokeCount $SmokeCount
$receiptPath = Join-Path $folder "PILOT_E2E_REPORT.json"
if (-not (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
    throw "Relatorio do handoff ausente: $receiptPath"
}
$handoff = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
if ($handoff.status -ne "P0_P1_REAL_PILOT_PASSED_P2_PENDING") {
    throw "Handoff nao validado"
}
$inbox = [string]$handoff.curator_inbox
Write-Host "Inbox verificada: $inbox" -ForegroundColor Green

Write-Host "[3/5] Localizar original EXATO no cache do Analyzer"
Push-Location $curator
try {
$summaryRaw = & $cp -m ldporto_studio r6-review --inbox $inbox --summary
Check-Exit "Leitura R6"
$summary = ($summaryRaw | Out-String | ConvertFrom-Json)
$id = [string]$summary.source.url
$match = [regex]::Match($id, '[?&]v=([A-Za-z0-9_-]{11})(?:&|$)')
if (-not $match.Success) { throw "ID nao encontrado no pacote R6" }
$videoId = $match.Groups[1].Value
$media = ""
if ($MediaPath) {
    $media = (Resolve-Path -LiteralPath $MediaPath).Path
} else {
    $download = Join-Path $analyzer ("input\youtube\"+$videoId+"\download.json")
    if (-not (Test-Path -LiteralPath $download -PathType Leaf)) {
        throw "Fonte local nao encontrada no cache legado: $download. Informe -MediaPath com o original exato."
    }
    $cache = Get-Content -LiteralPath $download -Raw | ConvertFrom-Json
    $filename = [string]$cache.filename
    if (-not $filename -or $filename -ne [IO.Path]::GetFileName($filename) -or
        $filename.Contains('\') -or $filename.Contains('/') -or
        $filename.Contains(':') -or $filename.Contains('..')) {
        throw "Nome de arquivo inseguro no cache legado"
    }
    $media = Join-Path (Split-Path -Path $download -Parent) $filename
}
if (-not (Test-Path -LiteralPath $media -PathType Leaf)) { throw "Fonte de video ausente: $media" }
$mediaSha = (Get-FileHash -LiteralPath $media -Algorithm SHA256).Hash.ToLowerInvariant()
if ($mediaSha -ne [string]$summary.source.source_sha256) {
    throw "BLOQUEADO: MP4 local difere da fonte analisada (SHA256)."
}
Write-Host "SHA256 exato confirmado: $mediaSha" -ForegroundColor Green

Write-Host "[4/5] Curator: auditoria e PREVIA TECNICA isolada"
$mediaAuditRaw = & $cp -m ldporto_studio r6-media-audit --inbox $inbox --media $media
Check-Exit "Auditoria de midia"
$audit = ($mediaAuditRaw | Out-String | ConvertFrom-Json)
if ($audit.status -ne "EXACT_SOURCE_FOUND" -or $audit.exact_matches_count -lt 1) {
    throw "Curator nao confirmou a fonte original"
}
$previewRaw = & $cp -m ldporto_studio r6-preview-smoke --inbox $inbox --media $media --seconds 6 --confirm-preview-test
Check-Exit "Geracao de preview tecnico"
$preview = ($previewRaw | Out-String | ConvertFrom-Json)
if ($preview.status -ne "TECHNICAL_PREVIEW_REVIEW_REQUIRED" -or
    $preview.publication_ready -ne $false -or $preview.human_approved -ne $false) {
    throw "Previa tecnica com estado inseguro"
}
Write-Host "PREVIA REAL: $($preview.file_path)" -ForegroundColor Green
}
finally {
    Pop-Location
}

Write-Host "[5/5] Relatorio local de retomada"
$report = [ordered]@{
    schema_version="1.0"
    status="HANDOFF_RECOVERED_AND_R6_TECHNICAL_PREVIEW_GENERATED"
    analyst_inference_reexecuted=$false
    analyzer_commit=(& git.exe -C $analyzer rev-parse HEAD).Trim()
    curator_commit=(& git.exe -C $curator rev-parse HEAD).Trim()
    source_zip=$zip
    source_zip_sha256=(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    curator_inbox=$inbox
    source_media=$media
    source_sha256=$mediaSha
    technical_preview_file=[string]$preview.file_path
    technical_preview_sha256=[string]$preview.preview_sha256
    analyzer_current_baseline_previous_suite="2693_PASS_6_SKIPPED_7_HISTORICAL_PENDING"
    curator_previous_suite="94_PASS"
    historical_full_suite_passed=$false
    human_approved=$false
    publication_ready=$false
    final_reels_rendered=$false
    source_preserved=$true
}
$path = Join-Path $folder "PILOT_RECOVERED_PREVIEW_REPORT.json"
[IO.File]::WriteAllText($path,($report | ConvertTo-Json -Depth 6),
    (New-Object Text.UTF8Encoding($false)))
Write-Host "RELATORIO: $path" -ForegroundColor Green
Write-Host "Nota: R6->R57 editorial e a verificacao de legendas/camera ainda estao pendentes."
