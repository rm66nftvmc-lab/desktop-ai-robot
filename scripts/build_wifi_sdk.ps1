# Build only; never uploads. Inherit the Windows proxy for this process only.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$previousHttp = $env:HTTP_PROXY
$previousHttps = $env:HTTPS_PROXY
$previousUtf8 = $env:PYTHONUTF8
$previousBuildDir = $env:PLATFORMIO_BUILD_DIR
try {
    $env:PYTHONUTF8 = '1'
    # IDF 4's objdump/ldgen disagree on encoding for Chinese archive paths.
    $env:PLATFORMIO_BUILD_DIR = Join-Path $env:LOCALAPPDATA 'DesktopAiRobot\wifi-sdk-build'
    $settings = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    if ($settings.ProxyEnable -eq 1 -and $settings.ProxyServer) {
        $server = [string]$settings.ProxyServer
        if ($server -notmatch '=') {
            if ($server -notmatch '^https?://') { $server = 'http://' + $server }
            if (-not $env:HTTP_PROXY) { $env:HTTP_PROXY = $server }
            if (-not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = $server }
        } else {
            foreach ($entry in ($server -split ';')) {
                if ($entry -match '^(http|https)=(.+)$') {
                    $scheme = $Matches[1]
                    $address = $Matches[2]
                    if ($address -notmatch '^https?://') { $address = 'http://' + $address }
                    if ($scheme -eq 'http' -and -not $env:HTTP_PROXY) { $env:HTTP_PROXY = $address }
                    if ($scheme -eq 'https' -and -not $env:HTTPS_PROXY) { $env:HTTPS_PROXY = $address }
                }
            }
        }
    }
    & $python -m platformio run -d (Join-Path $repo 'voice-device\diagnostics\wifi-sdk')
    if ($LASTEXITCODE -ne 0) { throw 'SDK build failed; no firmware was uploaded.' }
    & $python (Join-Path $repo 'scripts\verify_wifi_sdk_build.py')
    if ($LASTEXITCODE -ne 0) { throw 'SDK build verification failed; no firmware was uploaded.' }
} finally {
    $env:HTTP_PROXY = $previousHttp
    $env:HTTPS_PROXY = $previousHttps
    $env:PYTHONUTF8 = $previousUtf8
    $env:PLATFORMIO_BUILD_DIR = $previousBuildDir
}
