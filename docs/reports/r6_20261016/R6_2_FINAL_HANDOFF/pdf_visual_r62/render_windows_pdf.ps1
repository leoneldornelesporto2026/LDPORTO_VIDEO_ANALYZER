param([string]$PdfPath = (Join-Path $PSScriptRoot 'synthetic_editorial.pdf'),
      [string]$OutputDirectory = $PSScriptRoot,
      [int]$MaxPages = 0,
      [int[]]$PageNumbers = @())

$ErrorActionPreference = 'Stop'
$reportRoot = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if ($resolvedOutput -ne $reportRoot -and -not $resolvedOutput.StartsWith($reportRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'reader_output_outside_visual_report'
}
$null = New-Item -ItemType Directory -Path $resolvedOutput -Force
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null

$taskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
$actionMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
} | Select-Object -First 1

function Await-Operation($operation, [Type]$resultType) {
    $task = $taskMethod.MakeGenericMethod($resultType).Invoke($null, @($operation))
    $task.Wait()
    return $task.Result
}
function Await-Action($operation) {
    $task = $actionMethod.Invoke($null, @($operation))
    $task.Wait()
}

$resolvedPdf = (Resolve-Path -LiteralPath $PdfPath).Path
$storageFile = Await-Operation ([Windows.Storage.StorageFile]::GetFileFromPathAsync($resolvedPdf)) ([Windows.Storage.StorageFile])
$document = Await-Operation ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($storageFile)) ([Windows.Data.Pdf.PdfDocument])
$results = @()
$renderCount = if ($MaxPages -gt 0) { [Math]::Min($MaxPages, $document.PageCount) } else { $document.PageCount }
$pageIndices = if ($PageNumbers.Count -gt 0) { @($PageNumbers | ForEach-Object { $_ - 1 }) } else { @(0..($renderCount - 1)) }
foreach ($pageIndex in $pageIndices) {
    if ($pageIndex -lt 0 -or $pageIndex -ge $document.PageCount) { throw 'reader_page_number_outside_pdf' }
    $page = $document.GetPage([uint32]$pageIndex)
    $stream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    try {
        Await-Action ($page.RenderToStreamAsync($stream))
        $reader = New-Object Windows.Storage.Streams.DataReader ($stream.GetInputStreamAt(0))
        try {
            $size = [uint32]$stream.Size
            $null = Await-Operation ($reader.LoadAsync($size)) ([uint32])
            $bytes = New-Object byte[] $size
            $reader.ReadBytes($bytes)
            $target = Join-Path $resolvedOutput ('page_{0:D2}.png' -f ($pageIndex + 1))
            [System.IO.File]::WriteAllBytes($target, $bytes)
            $results += [pscustomobject]@{page = $pageIndex + 1; width = $page.Size.Width;
                height = $page.Size.Height; file = [System.IO.Path]::GetFileName($target); bytes = $size}
        } finally { $reader.Dispose() }
    } finally { $stream.Dispose(); $page.Dispose() }
}
$report = [pscustomobject]@{reader = 'Windows.Data.Pdf.PdfDocument'; source = [System.IO.Path]::GetFileName($resolvedPdf);
    source_sha256 = (Get-FileHash -LiteralPath $resolvedPdf -Algorithm SHA256).Hash.ToLowerInvariant();
    total_pages = $document.PageCount; rendered_pages = $results.Count; pages = $results;
    scope = 'independent_windows_pdf_reader_no_source_media'}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $resolvedOutput 'windows_reader_result.json') -Encoding UTF8
$report | ConvertTo-Json -Depth 5
