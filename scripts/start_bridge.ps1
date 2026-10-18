# Start (or restart) the Desktop AI Robot Bridge with the anchored data store.
#
# The Bridge must see one store: the one recorded in
# %PROGRAMDATA%\DesktopAiRobot\data-dir.txt. Resolving a different LOCALAPPDATA
# (for example under a packaged editor or another user context) used to create a
# second empty database and a second access key. This launcher pins the store
# explicitly so that cannot happen by accident.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_bridge.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\start_bridge.ps1 -Restart
#
# -Restart stops only this project's Bridge, its Paimon TTS child and the
# headless Harness Host that the Bridge itself started; unrelated listeners are
# rejected, never killed.

[CmdletBinding()]
param(
    [switch]$Restart,
    [switch]$OpenBrowser,
    [ValidateRange(1, 65535)][int]$Port = 8787
)

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python virtual environment not found at $python. Create it with: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}

function Get-PortOwner([int]$port) {
    # Get-NetTCPConnection can stall in the Windows networking CIM provider,
    # especially while a listener is being removed. netstat avoids that query.
    foreach ($line in (& netstat.exe -ano -p tcp)) {
        if ($line -match '^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$' -and [int]$Matches[1] -eq $port) {
            return [int]$Matches[2]
        }
    }
    return 0
}

function Get-CommandLine([int]$processId) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    if ($process) { return [string]$process.CommandLine }
    return ''
}

function Stop-OwnedProcess([int]$processId, [string]$expectedPattern, [string]$label) {
    if (-not $processId) { return }
    $commandLine = Get-CommandLine $processId
    if (-not $commandLine) { return }  # Already exited between the port probe and here.
    if ($commandLine -notmatch $expectedPattern) {
        throw "Refusing to stop $label (PID $processId); its command line does not match $expectedPattern`n$commandLine"
    }
    Write-Host "Stopping $label (PID $processId)..."
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

$bridgeOwner = Get-PortOwner $Port
$bridgePattern = 'bridge\.app\.main:app|\-m\s+bridge\.run(?:\s|$)'
if ($Restart -and $bridgeOwner) {
    Stop-OwnedProcess $bridgeOwner $bridgePattern 'Bridge'
    $releaseDeadline = (Get-Date).AddSeconds(10)
    while ((Get-PortOwner $Port) -and (Get-Date) -lt $releaseDeadline) {
        Start-Sleep -Milliseconds 300
    }
    $bridgeOwner = Get-PortOwner $Port
}
if ($bridgeOwner) {
    if ((Get-CommandLine $bridgeOwner) -notmatch $bridgePattern) {
        throw "Port $Port is owned by another application; refusing to treat it as Bridge."
    }
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
    if ($health.ok -ne $true) { throw 'The listening Bridge failed its health check.' }
    Write-Host "Bridge already listening on http://127.0.0.1:$Port (PID $bridgeOwner)."
    Write-Host 'Use -Restart to reload code, models or the Harness plugin.'
    if ($OpenBrowser) { Start-Process "http://127.0.0.1:$Port/" }
    exit 0
}

if ($Restart) {
    # Bridge termination can orphan its children. Only processes whose command
    # line proves they belong to this project are removed.
    $paimonOwner = Get-PortOwner 9880
    if ($paimonOwner) { Stop-OwnedProcess $paimonOwner 'tts-paimon' 'Paimon TTS' }
    $cosyvoiceOwner = Get-PortOwner 9881
    if ($cosyvoiceOwner) { Stop-OwnedProcess $cosyvoiceOwner 'cosyvoice_local_server\.py' 'CosyVoice TTS' }
    $harnessOwner = Get-PortOwner 3081
    if ($harnessOwner) { Stop-OwnedProcess $harnessOwner 'harness-bridge\.patch' 'Bridge Harness Host' }
}

# Resolve the one anchored store. ROBOT_DATA_DIR wins only when explicitly set.
$anchorFile = Join-Path $env:ProgramData 'DesktopAiRobot\data-dir.txt'
$dataDir = $null
$dataSource = ''
if ($env:ROBOT_DATA_DIR) {
    $dataDir = $env:ROBOT_DATA_DIR
    $dataSource = 'ROBOT_DATA_DIR'
} elseif (Test-Path -LiteralPath $anchorFile) {
    $dataDir = (Get-Content -LiteralPath $anchorFile -Raw).Trim()
    $dataSource = 'anchor'
} else {
    $dataDir = Join-Path $env:LOCALAPPDATA 'DesktopAiRobot'
    $dataSource = 'LOCALAPPDATA'
}
if (-not [IO.Path]::IsPathRooted($dataDir)) {
    throw "Resolved data directory is not absolute: $dataDir"
}
$dataDir = [IO.Path]::GetFullPath($dataDir)
if (-not (Test-Path -LiteralPath $dataDir)) {
    throw "Data directory does not exist: $dataDir (source=$dataSource)"
}
if (-not (Test-Path -LiteralPath (Join-Path $dataDir 'access-token.txt'))) {
    Write-Warning "No access-token.txt in $dataDir; Bridge will create a new access key."
}

# Readiness summary. Missing optional models degrade gracefully, but the user
# should know before wondering why the robot is silent.
$ttsZh = Test-Path -LiteralPath (Join-Path $dataDir 'models\tts\kokoro-v1.1-zh.int8.onnx')
$ttsEn = Test-Path -LiteralPath (Join-Path $dataDir 'models\tts\kokoro-v1.0.int8.onnx')
$whisper = Test-Path -LiteralPath (Join-Path $dataDir 'models\models--Systran--faster-whisper-small')
$paimon = Test-Path -LiteralPath (Join-Path $dataDir 'tts-paimon\INSTALL_COMPLETE.txt')
$plugin = Test-Path -LiteralPath (Join-Path $HOME '.dsh\profiles\web\node_modules\dsh-plugin-session-delete\package.json')

Write-Host "Store:      $dataDir (source=$dataSource)"
Write-Host ("Models:     Kokoro zh={0} en={1}, Whisper small={2}, Paimon={3}" -f $ttsZh, $ttsEn, $whisper, $paimon)
Write-Host ("Harness:    session-delete plugin={0}" -f $plugin)
if (-not $plugin) {
    Write-Warning 'Permanent Harness conversation deletion will fail with 404. Install the vendored plugin: scripts\install_dsh_plugin.ps1'
}

$env:ROBOT_DATA_DIR = $dataDir
& $python -c "from bridge.run import rotate_startup_logs; from bridge.app.security import resolve_data_dir; rotate_startup_logs(resolve_data_dir()[0])"
if ($LASTEXITCODE -ne 0) { throw 'Bridge startup log rotation failed' }
$stdout = Join-Path $dataDir 'bridge.stdout.log'
$stderr = Join-Path $dataDir 'bridge.stderr.log'
$arguments = @('-m', 'bridge.run', '--port', "$Port")

Write-Host "Starting Bridge on http://127.0.0.1:$Port ..."
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $repo `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru

$deadline = (Get-Date).AddSeconds(60)
$ready = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch {
        if ($process.HasExited) { break }
    }
}

if (-not $ready) {
    Write-Host 'Bridge did not become ready. Last error output:' -ForegroundColor Red
    if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Tail 40 }
    $runtimeLog = Join-Path $dataDir 'bridge.runtime.log'
    if (Test-Path -LiteralPath $runtimeLog) { Get-Content -LiteralPath $runtimeLog -Tail 30 }
    throw 'Bridge startup failed.'
}

Write-Host ''
Write-Host "Bridge ready: http://127.0.0.1:$Port  (PID $($process.Id))" -ForegroundColor Green
Write-Host "Access key:   $(Join-Path $dataDir 'access-token.txt')"
Write-Host "Logs:         $stderr"
Write-Host "Runtime log:  $(Join-Path $dataDir 'bridge.runtime.log') (2 MB x 4 files maximum)"
Write-Host "Device / TTS state: open the page, log in, then GET /api/status"
if ($OpenBrowser) { Start-Process "http://127.0.0.1:$Port/" }
