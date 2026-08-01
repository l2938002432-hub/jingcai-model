$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $projectRoot 'artifacts\relay'
$python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
try {
    Push-Location $projectRoot
    & $python "$projectRoot\scripts\relay_official_snapshot.py" 2>&1 |
        Tee-Object -FilePath (Join-Path $logDir 'relay.log') -Append
    if ($LASTEXITCODE -ne 0) {
        throw "relay exited with code $LASTEXITCODE"
    }
    "[$stamp] relay dispatched successfully" | Add-Content -Encoding utf8 (Join-Path $logDir 'relay.log')
}
catch {
    "[$stamp] relay failed: $($_.Exception.Message)" | Add-Content -Encoding utf8 (Join-Path $logDir 'relay-error.log')
    exit 1
}
finally {
    Pop-Location -ErrorAction SilentlyContinue
}
