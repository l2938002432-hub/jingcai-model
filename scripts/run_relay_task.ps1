$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $projectRoot 'artifacts\relay'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdoutLog = Join-Path $logDir "relay-$stamp.stdout.log"
$stderrLog = Join-Path $logDir "relay-$stamp.stderr.log"
$summaryLog = Join-Path $logDir 'relay.log'
$errorLog = Join-Path $logDir 'relay-error.log'
$successRecord = Join-Path $logDir 'last-success.json'

function Resolve-RelayPython {
    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($env:JINGCAI_RELAY_PYTHON)) {
        $candidates += $env:JINGCAI_RELAY_PYTHON
    }
    $candidates += (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe')
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) {
        $candidates += $command.Source
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "Python interpreter not found. Checked JINGCAI_RELAY_PYTHON, Python313 under LOCALAPPDATA, and python.exe on PATH."
}

try {
    Push-Location $projectRoot
    $python = Resolve-RelayPython
    $version = & $python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python interpreter check failed: $version"
    }
    "[$(Get-Date -Format 's')] relay start; python=$python; version=$version; stdout=$stdoutLog; stderr=$stderrLog" |
        Add-Content -Encoding utf8 $summaryLog
    & $python "$projectRoot\scripts\relay_official_snapshot.py" --diagnostic-json 1> $stdoutLog 2> $stderrLog
    if ($LASTEXITCODE -ne 0) {
        throw "relay exited with code $LASTEXITCODE; stdout=$stdoutLog; stderr=$stderrLog"
    }
    $metadataLine = Get-Content -LiteralPath $stdoutLog -Tail 1 -ErrorAction Stop
    $metadata = $metadataLine | ConvertFrom-Json -ErrorAction Stop
    $record = [ordered]@{
        completed_at = (Get-Date).ToUniversalTime().ToString('o')
        python = $python
        python_version = "$version"
        snapshot_sha256 = $metadata.snapshot_sha256
        snapshot_bytes = $metadata.snapshot_bytes
        fixture_count = $metadata.fixture_count
        repository = $metadata.repository
        ref = $metadata.ref
        dispatch_message = $metadata.message
    }
    $record | ConvertTo-Json | Set-Content -Encoding utf8 $successRecord
    "[$(Get-Date -Format 's')] relay dispatched; hash=$($metadata.snapshot_sha256); fixtures=$($metadata.fixture_count); last_success=$successRecord" |
        Add-Content -Encoding utf8 $summaryLog
}
catch {
    "[$(Get-Date -Format 's')] relay failed: $($_.Exception.Message); stdout=$stdoutLog; stderr=$stderrLog" |
        Add-Content -Encoding utf8 $errorLog
    exit 1
}
finally {
    Pop-Location -ErrorAction SilentlyContinue
}
