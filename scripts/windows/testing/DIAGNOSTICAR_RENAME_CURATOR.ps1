# Read-only diagnosis of the existing Curator delivery directory, except
# temporary probe folders CREATED by this script. Never changes ACL/security
# settings, source ZIPs, pre-existing deliveries, or repository code.
[CmdletBinding()]
param(
    [string]$CuratorRoot = "",
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$')]
    [string]$VideoId = "Eo2bUJcxASI"
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$analyzer = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
$curator = if ($CuratorRoot) {
    (Resolve-Path -LiteralPath $CuratorRoot).Path
} else {
    Join-Path (Split-Path -Path $analyzer -Parent) "LDPORTO_VIDEO_CURATOR"
}
if (-not (Test-Path -LiteralPath (Join-Path $curator "ldporto_studio\core.py") -PathType Leaf)) {
    throw "Curator ausente: $curator"
}
$root = Join-Path $curator ("input\analyzer\" + $VideoId)
$repoPath = Join-Path $curator "input\analyzer"
foreach ($path in @($curator,$repoPath,$root)) {
    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path -Force
        Write-Host ("PATH: "+$item.FullName)
        Write-Host ("ATTRIBUTES: "+$item.Attributes)
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Reparse point detected in delivery ancestry: $path"
        }
    }
}
# The real handoff may already have created the video-specific parent.
if (-not (Test-Path -LiteralPath $root -PathType Container)) {
    throw "Parent directory absent. Run the real handoff first; no new delivery parent created."
}
$token = [guid]::NewGuid().ToString("N")
$stage = Join-Path $root (".handoff-diagnostic-pending-" + $token)
$target = Join-Path $root (".handoff-diagnostic-published-" + $token)
Write-Host "TEST: atomic rename of a temporary folder under: $root" -ForegroundColor Cyan
try {
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    [IO.File]::WriteAllText((Join-Path $stage "only_this_test.txt"),"Directory-rename probe only.")
    if (Test-Path -LiteralPath $target) {
        throw "Unexpected diagnostic destination collision: $target"
    }
    [IO.Directory]::Move($stage,$target)
    if (-not (Test-Path -LiteralPath (Join-Path $target "only_this_test.txt") -PathType Leaf)) {
        throw "Probe file was lost during folder rename."
    }
    Write-Host "PROBE_RENAME_OK - Directory rename is allowed at this moment." -ForegroundColor Green
}
catch {
    Write-Host "PROBE_RENAME_FAILED - Local Windows permissions, sharing lock, or security policy may prevent the move." -ForegroundColor Yellow
    Write-Host ("ERROR: " + $_.Exception.GetType().FullName + " " + $_.Exception.Message)
    throw
}
finally {
    # Clean up ONLY the two unique paths created here.
    foreach ($path in @($target,$stage)) {
        if (Test-Path -LiteralPath $path) {
            try { Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop }
            catch { Write-Warning ("Cleanup of our test folder failed: "+$path+"; "+$_.Exception.Message) }
        }
    }
}
