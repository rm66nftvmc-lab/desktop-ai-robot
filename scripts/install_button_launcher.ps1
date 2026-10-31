[CmdletBinding()]
param([switch]$Uninstall)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\pythonw.exe'
$entry = Join-Path $PSScriptRoot 'button_launcher.py'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$name = 'DesktopAiRobotButtonLauncher'
if ($Uninstall) {
    Remove-ItemProperty -LiteralPath $runKey -Name $name -ErrorAction SilentlyContinue
    # Stop only this checkout's listener, never Bridge or unrelated Python processes.
    foreach ($process in (Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'")) {
        if ($process.CommandLine -and $process.CommandLine.Contains($entry)) {
            Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
        }
    }
    Write-Host 'Button listener removed from login startup.'
    exit 0
}
if (-not (Test-Path -LiteralPath $python)) { throw 'Project pythonw.exe is missing.' }
New-Item -Path $runKey -Force | Out-Null
Set-ItemProperty -LiteralPath $runKey -Name $name -Value ('"{0}" "{1}"' -f $python, $entry)
Start-Process -FilePath $python -ArgumentList ('"{0}"' -f $entry) -WorkingDirectory $repo -WindowStyle Hidden
Write-Host 'USB button listener installed and started; it will run at Windows login.'
