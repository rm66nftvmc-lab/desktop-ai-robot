# Start only an already configured, loopback-only Hermes Gateway. Never change keys.
[CmdletBinding()]
param([string]$DataDir)
$ErrorActionPreference = 'Stop'
function Test-GatewayPort {
    $socket = [Net.Sockets.TcpClient]::new()
    try {
        $task = $socket.ConnectAsync('127.0.0.1', 8642)
        return ($task.Wait(300) -and $socket.Connected)
    } catch { return $false } finally { $socket.Dispose() }
}
if (Test-GatewayPort) { Write-Host 'Hermes Gateway listener already running.'; return }
if (-not $DataDir) {
    $anchor = Join-Path $env:ProgramData 'DesktopAiRobot\data-dir.txt'
    if ($env:ROBOT_DATA_DIR) { $DataDir = $env:ROBOT_DATA_DIR }
    elseif (Test-Path -LiteralPath $anchor) { $DataDir = (Get-Content -LiteralPath $anchor -Raw).Trim() }
    else { $DataDir = Join-Path $env:LOCALAPPDATA 'DesktopAiRobot' }
}
$exe = Join-Path $env:LOCALAPPDATA 'hermes\bin\hermes.exe'
$config = Join-Path $env:LOCALAPPDATA 'hermes\.env'
$keyFile = Join-Path $DataDir 'hermes-api-key.txt'
if (-not ((Test-Path -LiteralPath $exe) -and (Test-Path -LiteralPath $config) -and (Test-Path -LiteralPath $keyFile))) {
    Write-Warning 'Hermes Gateway is not configured; Bridge can still use other agents.'
    return
}
$settings = @{}
foreach ($line in (Get-Content -LiteralPath $config)) {
    if ($line -match '^\s*(API_SERVER_(?:KEY|HOST|PORT))\s*=\s*(.*?)\s*$') {
        $settings[$Matches[1]] = $Matches[2].Trim('"', "'")
    }
}
$key = (Get-Content -LiteralPath $keyFile -Raw).Trim()
if ($key.Length -lt 16 -or $settings['API_SERVER_KEY'] -cne $key -or
    $settings['API_SERVER_HOST'] -ne '127.0.0.1' -or $settings['API_SERVER_PORT'] -ne '8642') {
    Write-Warning 'Hermes API configuration does not match the local Bridge. Existing settings were preserved.'
    return
}
try {
    $process = Start-Process -FilePath $exe -ArgumentList @('gateway', 'run') -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $DataDir 'hermes-gateway.stdout.log') `
        -RedirectStandardError (Join-Path $DataDir 'hermes-gateway.stderr.log')
} catch {
    Write-Warning 'Hermes Gateway could not start. Bridge can still use other agents.'
    return
}
$deadline = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $deadline -and -not $process.HasExited) {
    if (Test-GatewayPort) { Write-Host 'Hermes Gateway listener started; Bridge will verify API authentication.'; return }
    Start-Sleep -Milliseconds 500
}
Write-Warning 'Hermes Gateway has not become ready. Check the private hermes-gateway logs.'
