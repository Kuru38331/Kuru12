$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$runtime = Join-Path $PSScriptRoot 'runtime'
$exe = Join-Path $runtime 'python.exe'
if (!(Test-Path -LiteralPath $exe)) {
    $candidate = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($candidate) {
        & $candidate.Source -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
        if ($LASTEXITCODE -eq 0) { & $candidate.Source -3 (Join-Path $PSScriptRoot 'web_launcher.py'); exit $LASTEXITCODE }
    }
    $candidate = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($candidate) {
        & $candidate.Source -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
        if ($LASTEXITCODE -eq 0) { & $candidate.Source (Join-Path $PSScriptRoot 'web_launcher.py'); exit $LASTEXITCODE }
    }
    Write-Host 'Preparing Python runtime from python.org. First launch only...'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $work = Join-Path ([IO.Path]::GetTempPath()) ('hsho-runtime-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $work | Out-Null
    try {
        $zip = Join-Path $work 'python.zip'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.13.7/python-3.13.7-embed-amd64.zip' -OutFile $zip
        $expanded = Join-Path $work 'expanded'
        Expand-Archive -LiteralPath $zip -DestinationPath $expanded
        $signature = Get-AuthenticodeSignature -LiteralPath (Join-Path $expanded 'python.exe')
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Python signature verification failed; runtime not installed.' }
        # Permit standard-library sibling imports without using global Python paths.
        Set-Content -LiteralPath (Join-Path $expanded 'python313._pth') -Encoding ASCII -Value "python313.zip`r`n.`r`n..`r`n../server`r`n"
        Move-Item -LiteralPath $expanded -Destination $runtime
    } finally { Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue }
}
& $exe (Join-Path $PSScriptRoot 'web_launcher.py')
exit $LASTEXITCODE
