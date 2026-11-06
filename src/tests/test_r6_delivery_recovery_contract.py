"""Contracts for non-destructive R6 delivery recovery after a real Analyzer run.

Only filesystem/PowerShell structure is tested here; a physical Win11 rename
probe and original ZIP receipt remain required to claim actual recovery.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECOVERY = ROOT / "scripts/windows/testing/RETOMAR_R6_NASA_SEM_REANALISE.ps1"
DIAGNOSTIC = ROOT / "scripts/windows/testing/DIAGNOSTICAR_RENAME_CURATOR.ps1"
DELIVERY = ROOT / "src/ldporto/local_curator_handoff.py"


def test_01_recovery_requires_an_existing_analysis_not_youtube_redownload():
    script=RECOVERY.read_text(encoding="utf-8")
    assert "[Parameter(Mandatory=$true)]" in script
    assert "[string]$AnalysisDir" in script
    assert "second_curation_export.json" in script
    assert "PILOTO_E2E_REAL.ps1" in script
    assert "-AnalysisDir $folder" in script
    assert "allow-download" not in script.lower()
    assert "analyze.py" not in script
    assert "git push" not in script and "git merge" not in script


def test_02_recovery_validates_source_sha_and_never_approves_final():
    script=RECOVERY.read_text(encoding="utf-8")
    assert "Get-FileHash -LiteralPath $media -Algorithm SHA256" in script
    assert "if ($mediaSha -ne [string]$summary.source.source_sha256)" in script
    assert "r6-media-audit --inbox $inbox --media $media" in script
    assert "r6-preview-smoke --inbox $inbox --media $media --seconds 6 --confirm-preview-test" in script
    assert 'human_approved=$false' in script
    assert 'publication_ready=$false' in script
    assert 'final_reels_rendered=$false' in script
    assert 'historical_full_suite_passed=$false' in script


def test_03_recovery_probes_rename_then_enters_curator_repo_for_cli():
    script=RECOVERY.read_text(encoding="utf-8")
    assert "DIAGNOSTICAR_RENAME_CURATOR.ps1" in script
    assert "Push-Location $curator" in script
    assert "finally {" in script and "Pop-Location" in script
    assert "PILOT_RECOVERED_PREVIEW_REPORT.json" in script


def test_04_probe_deletes_only_task_owned_folders_and_keeps_policies():
    script=DIAGNOSTIC.read_text(encoding="utf-8")
    assert '[guid]::NewGuid().ToString("N")' in script
    assert ".handoff-diagnostic-pending-" in script
    assert ".handoff-diagnostic-published-" in script
    assert "[IO.Directory]::Move($stage,$target)" in script
    assert "if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)" in script
    assert "Remove-Item -LiteralPath $path -Recurse -Force" in script
    assert "Set-Acl" not in script and "icacls" not in script
    assert "takeown" not in script and "git push" not in script


def test_05_handoff_atomic_rename_stays_bounded_with_no_copy_fallback():
    script=DELIVERY.read_text(encoding="utf-8")
    assert "def _publish_directory_with_bounded_retry" in script
    assert "winerror" in script
    assert "max_attempts=6" in script
    assert "if code not in (5, 32, 33)" in script
    assert "delivery_destination_race_without_overwrite" in script
    assert "os.rename(staging, folder)" in script
    assert "curator_atomic_directory_rename_denied" in script
    assert "_publish_directory_with_bounded_retry(staging, folder)" in script
    assert "os.replace(staging, folder)" not in script


def test_06_original_package_remains_immutable_in_recovery():
    script=RECOVERY.read_text(encoding="utf-8")
    assert "source_preserved=$true" in script
    assert "PILOT_E2E_REPORT.json" in script
    assert "PILOT_RECOVERED_PREVIEW_REPORT.json" in script
    assert "SHA256" in script
    assert "python -m" not in script or "git add" not in script
    assert "PILOTO_FULL_DEFAULTS.ps1" not in script


def test_07_explicit_media_is_normalized_before_curator_directory_switch():
    script=RECOVERY.read_text(encoding="utf-8")
    assert 'if ($MediaPath) {' in script
    assert '$explicitMedia = (Resolve-Path -LiteralPath $MediaPath).Path' in script
    assert script.index('$explicitMedia = (Resolve-Path -LiteralPath $MediaPath).Path') < script.index('Push-Location $curator')
    assert 'if ($explicitMedia) { $realParams.MediaPath = $explicitMedia }' in script
    assert '$media = $explicitMedia' in script


def test_08_zip_is_measured_before_and_after_handoff():
    script=RECOVERY.read_text(encoding="utf-8")
    assert '$originalZipSha = (Get-FileHash -LiteralPath $zip -Algorithm SHA256)' in script
    assert '$finalZipSha = (Get-FileHash -LiteralPath $zip -Algorithm SHA256)' in script
    assert 'if ([string]$handoff.zip_sha256 -ne $originalZipSha)' in script
    assert 'if ($finalZipSha -ne $originalZipSha -or $finalZipBytes -ne $originalZipBytes)' in script
    assert 'source_zip_preservation_verified=$true' in script
    assert script.index('$originalZipSha =') < script.index('& $real @realParams')
    assert script.index('$finalZipSha =') > script.index('Pop-Location')


def test_09_preview_receipt_is_crosschecked_with_a_real_mp4():
    script=RECOVERY.read_text(encoding="utf-8")
    assert 'Resolve-Path -LiteralPath ([string]$preview.file_path)' in script
    assert 'output\\r6_preview_smoke' in script
    assert '[IO.FileAttributes]::ReparsePoint' in script
    assert '$previewSha = (Get-FileHash -LiteralPath $previewFile -Algorithm SHA256)' in script
    assert '$previewBytes -ne [long]$preview.file_bytes' in script
    assert '$preview.has_audio -ne $true' in script
    assert 'technical_preview_file_verified=$true' in script
    assert script.index('$previewSha =') < script.index('Write-Host "[5/5]')


def test_10_report_keeps_short_technical_preview_distinct_from_final_reels():
    script=RECOVERY.read_text(encoding="utf-8")
    assert 'technical_preview_duration_seconds=[double]$preview.output_duration' in script
    assert 'technical_preview_sample_seconds=[double]$preview.sample_seconds' in script
    assert 'human_approved=$false' in script
    assert 'publication_ready=$false' in script
    assert 'final_reels_rendered=$false' in script


def test_11_legacy_media_without_download_manifest_has_bounded_sha_verified_fallback():
    script=RECOVERY.read_text(encoding="utf-8")
    assert '$legacyDir = Join-Path $analyzer' in script
    assert 'if (Test-Path -LiteralPath $download -PathType Leaf)' in script
    assert 'foreach ($extension in @(".mp4", ".mkv", ".webm", ".mov"))' in script
    assert '$candidate = Join-Path $legacyDir ($videoId + $extension)' in script
    assert '$candidateSha = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256)' in script
    assert 'if ($candidateSha -eq [string]$summary.source.source_sha256)' in script
    assert 'Fonte exata ausente na pasta legada' in script
    assert 'Get-ChildItem -Recurse' not in script
    assert 'AllowDownload' not in script
