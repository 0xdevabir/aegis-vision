# One-command Docker bring-up for Aegis on Windows (PowerShell 5.1+, Docker Desktop).
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\docker-up.ps1
# Same steps as scripts/docker-up.sh.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Test-Native([scriptblock]$Command) {
    # Native commands report failure through the exit code, and their stderr must not stop the script.
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Command *> $null; return ($LASTEXITCODE -eq 0) } catch { return $false }
    finally { $ErrorActionPreference = $old }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host 'ERROR: Docker is not installed. Install Docker Desktop, then retry.'; exit 1
}
if (-not (Test-Native { docker compose version })) {
    Write-Host 'ERROR: docker compose plugin missing.'; exit 1
}
if (-not (Test-Native { docker info })) {
    Write-Host 'ERROR: Docker daemon is not running. Open Docker Desktop, wait until it is ready, then retry.'; exit 1
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host 'Created .env from .env.example - set real secrets before production use.'
}

# Compose interpolates these from .env - they must be present (placeholders OK for local demos).
function Get-EnvValue([string]$Key) {
    $line = Get-Content .env | Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
    if ($line) { return $line.Substring($Key.Length + 1).Trim() }
    return ''
}
foreach ($key in 'POSTGRES_PASSWORD', 'SECRET_KEY', 'ENCRYPTION_KEY', 'ENCRYPTION_SALT', 'INTERNAL_API_KEY') {
    if (-not (Get-EnvValue $key)) { Write-Host "ERROR: set $key in .env, then re-run."; exit 1 }
}

foreach ($dir in 'models', 'data\watchlist', 'data\demo\clips', 'logs') {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

# Host webcam bridge so Docker cameras with source: 0 / "0" can see the PC's camera.
$py = '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    $py = if ($cmd) { $cmd.Source } else { '' }
}
$listening = $false
try { $tcp = New-Object Net.Sockets.TcpClient('127.0.0.1', 8090); $tcp.Close(); $listening = $true } catch { }
if ($listening) {
    Write-Host 'webcam bridge already running'
} elseif (-not $py -or -not (Test-Native { & $py -c 'import cv2' })) {
    Write-Host 'Webcam bridge skipped: needs Python with OpenCV on the host (pip install opencv-python). RTSP/HTTP cameras are unaffected.'
} else {
    $bridge = Start-Process -FilePath $py -ArgumentList 'scripts\webcam_bridge.py' -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput 'logs\webcam_bridge.log' -RedirectStandardError 'logs\webcam_bridge.err.log'
    Set-Content -Path 'logs\webcam_bridge.pid' -Value $bridge.Id
    Write-Host "webcam bridge started (logs\webcam_bridge.log). Stop it with: Stop-Process -Id $($bridge.Id)"
}

Write-Host 'Building and starting Aegis stack (first build can take 10-20+ minutes)...'
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$port = Get-EnvValue 'HTTP_PORT'
if (-not $port) { $port = '8080' }
Write-Host ''
Write-Host '============================================'
Write-Host '  Aegis is starting'
Write-Host "  Dashboard  -> http://localhost:$port"
Write-Host "  API / docs -> http://localhost:$port/docs"
Write-Host '  Logs       -> docker compose logs -f'
Write-Host '  Admin pwd  -> docker compose logs backend | Select-String bootstrap'
Write-Host '  Stop       -> docker compose down'
Write-Host '============================================'
