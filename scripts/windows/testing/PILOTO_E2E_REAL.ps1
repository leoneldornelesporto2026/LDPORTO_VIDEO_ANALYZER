# P0/P1 real Windows pilot: one YouTube video -> Analyzer -> Curator inbox.
# No git operations, no final render, no implicit download, no editorial approval.
[CmdletBinding(DefaultParameterSetName="New")]
param(
    [Parameter(Mandatory=$true,ParameterSetName="New")]
    [string]$SourceUrl,
    [Parameter(Mandatory=$true,ParameterSetName="Reuse")]
    [string]$AnalysisDir,
    [string]$MediaPath="",
    [switch]$AllowDownload,
    [switch]$AnalyzerCanaryPreviews,
    [string]$CuratorRoot="",
    [ValidateRange(1,5)]
    [int]$SmokeCount=2
)
$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$analyzer=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
$curator=if ($CuratorRoot) { (Resolve-Path -LiteralPath $CuratorRoot).Path }
         else { Join-Path (Split-Path $analyzer -Parent) "LDPORTO_VIDEO_CURATOR" }
$ap=Join-Path $analyzer ".venv\Scripts\python.exe"
$cp=Join-Path $curator ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $ap -PathType Leaf)) {
    throw "Python .venv do Analyzer ausente: $ap"
}
if (-not (Test-Path -LiteralPath (Join-Path $curator "ldporto_studio\core.py") -PathType Leaf)) {
    throw "Curator nao encontrado: $curator"
}
if (-not (Test-Path -LiteralPath $cp -PathType Leaf)) { $cp=$ap }
foreach ($required in @("test_r6_review.py","test_r6_workflow.py",
                        "test_r6_smoke.py","test_r6_media_audit.py")) {
    if (-not (Test-Path -LiteralPath (Join-Path $curator ("tests\"+$required)) -PathType Leaf)) {
        throw "Curator esta desatualizado; falta $required. Atualize a develop antes de executar o piloto."
    }
}
function Assert-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step falhou: codigo $LASTEXITCODE" }
}
foreach ($repoRoot in @($analyzer,$curator)) {
    $branch=(& git.exe -C $repoRoot branch --show-current).Trim()
    Assert-Exit "git branch"
    if ($branch -ne "develop") { throw "O piloto exige develop em $repoRoot; branch=$branch" }
}
& $ap -c "import sys; assert sys.version_info[:2] == (3,11)"
Assert-Exit "Python 3.11 Analyzer"

$media=""
if ($MediaPath) {
    $media=(Resolve-Path -LiteralPath $MediaPath).Path
    if (-not (Test-Path -LiteralPath $media -PathType Leaf)) {
        throw "Midia nao encontrada: $media"
    }
}
if ($PSCmdlet.ParameterSetName -eq "New" -and -not $AllowDownload -and -not $media) {
    throw "Informe -MediaPath com a fonte local ou -AllowDownload explicitamente."
}

Write-Host "[0/5] Regression: Analyzer and Curator" -ForegroundColor Cyan
Push-Location $analyzer
try {
    & $ap -m pytest -q src/tests/test_local_curator_handoff.py
    Assert-Exit "Analyzer handoff tests"
}
finally { Pop-Location }
Push-Location $curator
try {
    foreach ($test in @("test_r6_review.py","test_r6_workflow.py",
                        "test_r6_smoke.py","test_r6_media_audit.py")) {
        & $cp -m unittest discover -s tests -p $test -v
        Assert-Exit "Curator $test"
    }
}
finally { Pop-Location }

if ($PSCmdlet.ParameterSetName -eq "New") {
    if ($SourceUrl -notmatch "^https://") {
        throw "URL invalida. Use HTTPS de video autorizado."
    }
    $folder=Join-Path $analyzer ("analysis\pilot_e2e_" + (Get-Date -Format "yyyyMMdd_HHmmss_fff"))
    if (Test-Path -LiteralPath $folder) { throw "Destino ja existe: $folder" }
    $arguments=@("analyze.py",$SourceUrl,"--output",$folder)
    if ($media) {
        $hash=(Get-FileHash -LiteralPath $media -Algorithm SHA256).Hash.ToLowerInvariant()
        $arguments+=@("--media-path",$media,"--media-sha256",$hash)
    }
    if ($AllowDownload) { $arguments+="--allow-download" }
    if ($AnalyzerCanaryPreviews) { $arguments+="--preview" }
    Write-Host "[1/5] Running REAL Analyzer pipeline (may be expensive)" -ForegroundColor Cyan
    Push-Location $analyzer
    try {
        & $ap @arguments
        Assert-Exit "Analyzer pipeline"
    }
    finally { Pop-Location }
} else {
    $folder=(Resolve-Path -LiteralPath $AnalysisDir).Path
    Write-Host "[1/5] Reusing existing analysis: $folder" -ForegroundColor Cyan
}
$exportFile=Join-Path $folder "second_curation_export.json"
if (-not (Test-Path -LiteralPath $exportFile -PathType Leaf)) {
    throw "Analyzer nao gerou recibo oficial: $exportFile"
}
$export=Get-Content -LiteralPath $exportFile -Raw | ConvertFrom-Json
if (-not $export.path) { throw "Analyzer nao disponibilizou ZIP oficial." }
$zip=[string]$export.path
if (-not [IO.Path]::IsPathRooted($zip)) { $zip=Join-Path $analyzer $zip }
if (-not (Test-Path -LiteralPath $zip -PathType Leaf)) {
    throw "ZIP nao encontrado: $zip"
}

Write-Host "[2/5] Real Windows delivery gate" -ForegroundColor Cyan
$gate=Join-Path $analyzer "scripts\windows\testing\VALIDAR_ENTREGA_CURATOR.ps1"
& $gate -AnalysisDir $folder -CuratorRoot $curator
Assert-Exit "Physical Analyzer-to-Curator gate"
$receiptFile=Join-Path $folder "curator_delivery.json"
if (-not (Test-Path -LiteralPath $receiptFile -PathType Leaf)) {
    throw "Recibo Curator ausente: $receiptFile"
}
$receipt=Get-Content -LiteralPath $receiptFile -Raw | ConvertFrom-Json
if ($receipt.delivery_status -notin @("DELIVERED","ALREADY_DELIVERED")) {
    throw "Entrega nao confirmada: $($receipt.delivery_status)"
}
$inbox=[string]$receipt.destination
if (-not (Test-Path -LiteralPath $inbox -PathType Container)) {
    throw "Inbox nao localizada: $inbox"
}

Push-Location $curator
try {
    Write-Host "[3/5] Real R6 candidates -> automatic TEST-ONLY draft -> preflight" -ForegroundColor Cyan
    $smokeRaw=& $cp -m ldporto_studio r6-smoke --inbox $inbox --count $SmokeCount
    Assert-Exit "R6 smoke"
    $smoke=$smokeRaw | Out-String | ConvertFrom-Json
    if ($smoke.status -ne "SMOKE_PASSED_WITH_PENDING_HUMAN_REVIEWS" -or
        $smoke.render_ready -ne $false) {
        throw "Smoke R6 falhou o contrato de seguranca."
    }
    Write-Host "Technical draft: $($smoke.draft_path)"
    Write-Host ("Test candidates: " + ($smoke.test_candidate_ids -join ", "))

    Write-Host "[4/5] Exact source-media SHA audit, no download" -ForegroundColor Cyan
    $auditArgs=@("-m","ldporto_studio","r6-media-audit","--inbox",$inbox)
    if ($media) { $auditArgs+=@("--media",$media) }
    $auditRaw=& $cp @auditArgs
    Assert-Exit "Media SHA audit"
    $audit=$auditRaw | Out-String | ConvertFrom-Json
}
finally { Pop-Location }

$next=if ($audit.status -eq "EXACT_SOURCE_FOUND") {
    "EXACT_SOURCE_FOUND_PREVIEW_ADAPTER_NOT_YET_IMPLEMENTED"
} elseif ($audit.status -eq "ALTERNATE_MEDIA_ONLY_REVIEW_REQUIRED") {
    "BLOCKED_FROM_AUTOMATIC_RENDER_DIFFERENT_SOURCE_SHA"
} else {
    "BLOCKED_FROM_PREVIEW_SOURCE_NOT_FOUND_IN_MANAGED_FOLDERS"
}
$report=[ordered]@{
    schema_version="1.0"
    status="P0_P1_REAL_PILOT_PASSED_P2_PENDING"
    analysis_dir=$folder
    analysis_state=[string]$receipt.analysis_state
    analyzer_commit=(& git.exe -C $analyzer rev-parse HEAD).Trim()
    curator_commit=(& git.exe -C $curator rev-parse HEAD).Trim()
    zip_sha256=(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    curator_inbox=$inbox
    curator_delivery_status=[string]$receipt.delivery_status
    technical_test_ids=@($smoke.test_candidate_ids)
    technical_draft_path=[string]$smoke.draft_path
    media_status=[string]$audit.status
    exact_source_count=[int]$audit.exact_matches_count
    next_gate=$next
    render_ready=$false
    human_approved=$false
    published=$false
}
$reportPath=Join-Path $folder "PILOT_E2E_REPORT.json"
[IO.File]::WriteAllText($reportPath,($report | ConvertTo-Json -Depth 8),
    (New-Object Text.UTF8Encoding($false)))
Write-Host "[5/5] Local report: $reportPath" -ForegroundColor Green
Write-Host "P0/P1 PASS; media=$($audit.status); next=$next" -ForegroundColor Green
Write-Host "No R6 video render or final publication was executed."
