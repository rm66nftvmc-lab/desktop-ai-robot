# Run in an Administrator PowerShell. Grants only the device port on this LAN.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ipaddress]$HostAddress,
    [ValidateRange(1024,65535)][int]$Port = 8788
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$program = & $python -c 'import sys; print(sys._base_executable)'
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $program)) {
    throw 'Cannot locate the actual Bridge Python runtime.'
}
$adapter = Get-NetIPAddress -IPAddress $HostAddress.IPAddressToString -AddressFamily IPv4
$parameters = @{
    Name = 'DesktopAiRobot-Device-WiFi'
    DisplayName = 'Desktop AI Robot Wi-Fi device'
    Direction = 'Inbound'
    Action = 'Allow'
    Protocol = 'TCP'
    LocalPort = $Port
    LocalAddress = $HostAddress.IPAddressToString
    RemoteAddress = 'LocalSubnet'
    InterfaceAlias = $adapter.InterfaceAlias
    Profile = 'Any'
    Program = $program
    Enabled = 'True'
}
if (Get-NetFirewallRule -Name $parameters.Name -ErrorAction SilentlyContinue) {
    $parameters.Remove('DisplayName')
    Set-NetFirewallRule @parameters | Out-Null
} else {
    New-NetFirewallRule @parameters | Out-Null
}
Write-Host "Allowed device TCP $Port only on $HostAddress / $($adapter.InterfaceAlias), from LocalSubnet."
