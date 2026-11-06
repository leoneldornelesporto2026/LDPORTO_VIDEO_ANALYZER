# FULL-defaults physical Windows acceptance:
# Full Analyzer suite + full Curator suite + real short YouTube video
# -> native ZIP -> local Curator inbox -> exact SHA -> technical preview.
# NO R57 final, NO Git change, NO config overrides.
[CmdletBinding()]
param(
    [string]$SourceUrl = "https://www.youtube.com/watch?v=Eo2bUJcxASI",
    [string]$MediaPath = "",
    [string]$FixtureSearchRoot = "",
    [switch]$AllowDownload
)
$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$analyzer=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
$curator=Join-Path (Split-Path $analyzer -Parent) "LDPORTO_VIDEO_CURATOR"
$ap=Join-Path $analyzer ".venv\Scripts\python.exe"
$cp=Join-Path $curator ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $ap -PathType Leaf)) {
    throw "Analyzer sem ambiente Python 3.11: $ap"
}
if (-not (Test-Path -LiteralPath (Join-Path $curator "ldporto_studio\core.py") -PathType Leaf)) {
    throw "Curator ausente: $curator"
}
if (-not (Test-Path -LiteralPath $cp -PathType Leaf)) {
    $cmd=Get-Command python -ErrorAction SilentlyContinue
    $cp=if ($cmd) { $cmd.Source } else { $ap }
}
function Assert-Exit([string]$description) {
    if ($LASTEXITCODE -ne 0) {
        throw "$description falhou. Abortado antes da etapa seguinte (exit=$LASTEXITCODE)."
    }
}
function Run-Suite([string]$repoPath, [scriptblock]$block) {
    Push-Location $repoPath
    try { & $block }
    finally { Pop-Location }
}
foreach ($root in @($analyzer,$curator)) {
    $name=Split-Path $root -Leaf
    $branch=(& git.exe -C $root branch --show-current).Trim()
    Assert-Exit "git branch $name"
    if ($branch -ne "develop") {
        throw "Suite completa requer develop no $name. Branch atual=$branch"
    }
    Write-Host "$name - SHA: $((& git.exe -C $root rev-parse HEAD).Trim())"
    Assert-Exit "git SHA $name"
}
$config=Join-Path $analyzer "config\config.yaml"
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
    throw "Configuracao padrao ausente: $config"
}
$before=(Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash
$ffmpegLocal=Join-Path $analyzer "tools\ffmpeg\bin"
if (Test-Path -LiteralPath $ffmpegLocal -PathType Container) {
    $env:PATH=$ffmpegLocal+[IO.Path]::PathSeparator+$env:PATH
}
foreach ($tool in @("ffmpeg","ffprobe")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool indisponivel. Suite de renderizacao nao pode ser homologada."
    }
}
& $ap -c "import sys; assert sys.version_info[:2] == (3,11); print('Analyzer Python',sys.version.split()[0])"
Assert-Exit "Python 3.11"

Write-Host ""
Write-Host "[0/5] RECUPERACAO DE FIXTURES HISTORICAS REAIS - SEM MOCKS" -ForegroundColor Cyan
$requiredFixtures=@(
    "src\tests\fixtures\historical_evidence\CHATGPT_REVIEW.zip",
    "src\tests\fixtures\historical_evidence\SECOND_CURATION_READY.zip"
)
$fixtureMissing=@($requiredFixtures | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $analyzer $_) -PathType Leaf)
})
if ($fixtureMissing.Count -gt 0) {
    $restore=Join-Path $analyzer "scripts\windows\testing\RESTAURAR_FIXTURES_HISTORICAS.ps1"
    if (-not (Test-Path -LiteralPath $restore -PathType Leaf)) {
        throw "Restaurador oficial indisponivel: $restore"
    }
    $search=if ($FixtureSearchRoot) {
        (Resolve-Path -LiteralPath $FixtureSearchRoot).Path
    } else {
        Split-Path -Path $analyzer -Parent
    }
    Write-Host "Buscando copias exatas (SHA256) em: $search"
    Write-Host "A busca pode levar mais tempo em pastas com muitos projetos."
    & $restore -SearchRoot $search
    Assert-Exit "Restauracao de fixtures originais"
}
# Always verify provenance and exact hashes; do not accept wrong copies.
$expectedFixtures=@(
    @{ Name="CHATGPT_REVIEW.zip"; Bytes=[long]26956533; SHA="5a9da201f984d63de2c68dbd9aee4c03365b9e0815b1fb041130d4da02b5f073" },
    @{ Name="SECOND_CURATION_READY.zip"; Bytes=[long]1864261; SHA="8339e90f41cce13f93bc61cc6417cecc1058ad37df272d194d7f62060d860349" }
)
foreach ($fixture in $expectedFixtures) {
    $target=Join-Path $analyzer ("src\tests\fixtures\historical_evidence\"+$fixture.Name)
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
        throw "BLOQUEADO: fixture original ausente: $($fixture.Name). Informe -FixtureSearchRoot com sua pasta de backups."
    }
    if ((Get-Item -LiteralPath $target).Length -ne $fixture.Bytes) {
        throw "BLOQUEADO: tamanho da fixture diferente: $target"
    }
    $actual=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if ($actual -ine $fixture.SHA) {
        throw "BLOQUEADO: SHA256 da fixture diferente: $target"
    }
    Write-Host ("Fixture original OK: "+$fixture.Name) -ForegroundColor Green
}

Write-Host ""
Write-Host "[1/5] ANALYZER: suite COMPLETA com preflight de fixtures" -ForegroundColor Cyan
Run-Suite $analyzer {
    & (Join-Path $analyzer "scripts\windows\testing\VALIDAR_P0_GUI.ps1") -FullSuite
    Assert-Exit "Suite completa Analyzer (sem pular fixtures)"
}
Write-Host ""
Write-Host "[2/5] CURATOR: suite COMPLETA incluindo FFmpeg, camera e R6" -ForegroundColor Cyan
Run-Suite $curator {
    & $cp -m unittest discover -s tests -p "test_*.py" -v
    Assert-Exit "Suite completa Curator (incluindo preview R57 sintetico)"
}
$source=([uri]$SourceUrl)
if ($source.Scheme -ne "https" -or
    $source.Host.ToLowerInvariant() -notin @("www.youtube.com","youtube.com","m.youtube.com")) {
    throw "Piloto padrao exige URL https://www.youtube.com/watch?v=... autorizada."
}
$idMatch=[regex]::Match($SourceUrl,'[?&]v=([A-Za-z0-9_-]{11})(?:&|$)')
if (-not $idMatch.Success) { throw "URL nao contem ID YouTube valido." }
$id=$idMatch.Groups[1].Value

$media=""
if ($MediaPath) { $media=(Resolve-Path -LiteralPath $MediaPath).Path }
if (-not $media -and -not $AllowDownload) {
    throw "Autorize o download com -AllowDownload ou forneca -MediaPath."
}
Write-Host ""
Write-Host "[3/5] ANALYZER: video real CURTO, configuracao YAML padrao" -ForegroundColor Cyan
$started=Get-Date
$pilot=Join-Path $analyzer "scripts\windows\testing\PILOTO_E2E_REAL.ps1"
$pilotArgs=@("-SourceUrl",$SourceUrl,"-SmokeCount",1)
if ($media) { $pilotArgs+=@("-MediaPath",$media) }
if ($AllowDownload) { $pilotArgs+="-AllowDownload" }
& $pilot @pilotArgs
Assert-Exit "Piloto real Analyzer -> Curator"
$analysisRoot=Join-Path $analyzer "analysis"
$recent=Get-ChildItem -LiteralPath $analysisRoot -Directory -Filter "pilot_e2e_*" |
    Where-Object { $_.CreationTime -ge $started.AddMinutes(-1) } |
    Sort-Object CreationTime -Descending |
    Select-Object -First 1
if (-not $recent) { throw "Pasta nova do piloto nao encontrada." }
$reportFile=Join-Path $recent.FullName "PILOT_E2E_REPORT.json"
if (-not (Test-Path -LiteralPath $reportFile -PathType Leaf)) {
    throw "Relatorio oficial P0/P1 nao encontrado: $reportFile"
}
$report=Get-Content -LiteralPath $reportFile -Raw | ConvertFrom-Json
if ($report.status -ne "P0_P1_REAL_PILOT_PASSED_P2_PENDING") {
    throw "P0/P1 nao aprovados no piloto real."
}
$inbox=[string]$report.curator_inbox
if (-not $media) {
    $download=Join-Path $analyzer ("input\youtube\"+$id+"\download.json")
    if (-not (Test-Path -LiteralPath $download -PathType Leaf)) {
        throw "Original nao localizado no cache do Analyzer: $download"
    }
    $record=Get-Content -LiteralPath $download -Raw | ConvertFrom-Json
    $filename=[string]$record.filename
    if (-not $filename -or $filename -ne [IO.Path]::GetFileName($filename) -or
        $filename.Contains("\") -or $filename.Contains("/") -or
        $filename.Contains(":") -or $filename.Contains("..")) {
        throw "Nome de arquivo inseguro no recibo do Analyzer."
    }
    $media=Join-Path (Split-Path $download -Parent) $filename
}
if (-not (Test-Path -LiteralPath $media -PathType Leaf)) {
    throw "Fonte original nao localizada: $media"
}
Write-Host ""
Write-Host "[4/5] CURATOR: verificar SHA256 exato da fonte Analyzer" -ForegroundColor Cyan
Run-Suite $curator {
    $summaryRaw=& $cp -m ldporto_studio r6-review --inbox $inbox --summary
    Assert-Exit "Resumo da nova analise R6"
    $summary=$summaryRaw | Out-String | ConvertFrom-Json
    $script:sha=(Get-FileHash -LiteralPath $media -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($sha -ne [string]$summary.source.source_sha256) {
        throw "BLOQUEADO: video baixado nao corresponde ao SHA do Analyzer."
    }
    $auditRaw=& $cp -m ldporto_studio r6-media-audit --inbox $inbox --media $media
    Assert-Exit "Auditoria exata do original"
    $script:audit=$auditRaw | Out-String | ConvertFrom-Json
    if ($audit.exact_matches_count -lt 1 -or $audit.status -ne "EXACT_SOURCE_FOUND") {
        throw "BLOQUEADO: auditoria nao confirmou a identidade exata da fonte."
    }
}
Write-Host ""
Write-Host "[5/5] CURATOR: PREVIA TECNICA REAL (6s, sem R57 nem publicacao)" -ForegroundColor Cyan
Run-Suite $curator {
    $raw=& $cp -m ldporto_studio r6-preview-smoke --inbox $inbox --media $media --seconds 6 --confirm-preview-test
    Assert-Exit "Preview tecnico de midia real"
    $script:preview=$raw | Out-String | ConvertFrom-Json
    if ($preview.status -ne "TECHNICAL_PREVIEW_REVIEW_REQUIRED" -or
        $preview.publication_ready -ne $false -or $preview.human_approved -ne $false) {
        throw "Previa sem estado seguro; falha de contrato."
    }
    Write-Host "PREVIA: $($preview.file_path)" -ForegroundColor Green
}
$after=(Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash
if ($before -ne $after) { throw "config/config.yaml foi alterado durante o piloto!" }
$final=[ordered]@{
    schema_version="1.0"
    result="FULL_SUITES_AND_REAL_TECHNICAL_PREVIEW_PASS"
    analyzer_commit=(& git.exe -C $analyzer rev-parse HEAD).Trim()
    curator_commit=(& git.exe -C $curator rev-parse HEAD).Trim()
    analyzed_url=$SourceUrl
    analysis_dir=$recent.FullName
    source_media=$media
    source_sha256=$sha
    curator_inbox=$inbox
    p0_p1_status=[string]$report.status
    media_identity=[string]$audit.status
    preview_file=[string]$preview.file_path
    preview_sha256=[string]$preview.preview_sha256
    analyzer_default_config_unchanged=$true
    suite_analyzer="PASS"
    suite_curator="PASS"
    editorial_r6_to_r57_ready=$false
    human_approved=$false
    publication_ready=$false
}
$target=Join-Path $recent.FullName "PILOT_FULL_DEFAULTS_REPORT.json"
[IO.File]::WriteAllText($target,($final | ConvertTo-Json -Depth 7),
    (New-Object Text.UTF8Encoding($false)))
Write-Host ""
Write-Host "PILOTO FISICO CONCLUIDO (ATE PREVIA TECNICA)" -ForegroundColor Green
Write-Host "Resumo: $target" -ForegroundColor Green
Write-Host "Ainda falta converter o roteiro R6 em pacote editorial renderizavel R57."
