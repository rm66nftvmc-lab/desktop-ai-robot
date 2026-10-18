# Install the vendored DeepSeek Harness session-delete plugin without a network.
#
# The Bridge uses DSH's `web` profile for its headless Harness host. Permanent
# Harness conversation deletion is a Host route provided by this plugin, so a
# clean checkout must be able to install it from `plugins/` instead of GitHub.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\install_dsh_plugin.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\install_dsh_plugin.ps1 -Force
#
# The script is idempotent. It copies the built package into the profile's
# node_modules, points the profile dependency at the local copy, and appends the
# plugin to `dsh.profile.bundles`. It never touches the desktop profile unless
# -ProfileName is given explicitly.

[CmdletBinding()]
param(
    [string]$DshHome = (Join-Path $HOME '.dsh'),
    [string]$ProfileName = 'web',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repo 'plugins\dsh-plugin-session-delete'
$sourceManifest = Join-Path $source 'package.json'

if (-not (Test-Path -LiteralPath $sourceManifest)) {
    throw "Vendored plugin not found at $source. Run this script from a full checkout."
}

$manifest = Get-Content -LiteralPath $sourceManifest -Raw -Encoding UTF8 | ConvertFrom-Json
$pluginName = [string]$manifest.name
$pluginVersion = [string]$manifest.version
if ($pluginName -ne 'dsh-plugin-session-delete') {
    throw "Unexpected plugin name '$pluginName' in $sourceManifest"
}

$dshHomePath = [IO.Path]::GetFullPath($DshHome)
$profileDir = Join-Path $dshHomePath (Join-Path 'profiles' $ProfileName)
$profileManifest = Join-Path $profileDir 'package.json'
$nodeModules = Join-Path $profileDir 'node_modules'
$target = Join-Path $nodeModules $pluginName

if (-not (Test-Path -LiteralPath $profileManifest)) {
    throw "DSH profile '$ProfileName' was not found at $profileDir. Start the Bridge once so DSH creates the profile, then rerun this script."
}

# Guard every destructive step with an explicit containment check.
$nodeModulesFull = [IO.Path]::GetFullPath($nodeModules)
$targetFull = [IO.Path]::GetFullPath($target)
if (-not $targetFull.StartsWith($nodeModulesFull + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to write outside the profile's node_modules: $targetFull"
}

$installedVersion = ''
$installedManifest = Join-Path $target 'package.json'
if (Test-Path -LiteralPath $installedManifest) {
    try {
        $installedVersion = [string](Get-Content -LiteralPath $installedManifest -Raw -Encoding UTF8 |
            ConvertFrom-Json).version
    } catch {
        $installedVersion = ''
    }
}

if ((Test-Path -LiteralPath $target) -and -not $Force) {
    if ($installedVersion -eq $pluginVersion) {
        Write-Host "Plugin $pluginVersion is already present in profile '$ProfileName'."
    } else {
        throw "Profile '$ProfileName' already has $pluginName $installedVersion. Rerun with -Force to replace it with $pluginVersion."
    }
} else {
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $nodeModules | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
    Write-Host "Copied $pluginName $pluginVersion to $target"
}

# Point the profile at the vendored copy. The absolute `file:` spec is resolved
# on this machine only; it is what keeps plugin installs working offline.
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Copy-Item -LiteralPath $profileManifest -Destination "$profileManifest.bak-$stamp" -Force
$profile = Get-Content -LiteralPath $profileManifest -Raw -Encoding UTF8 | ConvertFrom-Json

if ($null -eq $profile.PSObject.Properties['dependencies']) {
    $profile | Add-Member -MemberType NoteProperty -Name dependencies -Value ([pscustomobject]@{})
}
$fileSpec = 'file:' + ($source -replace '\\', '/')
$profile.dependencies | Add-Member -MemberType NoteProperty -Name $pluginName -Value $fileSpec -Force

if ($null -eq $profile.PSObject.Properties['dsh']) {
    $profile | Add-Member -MemberType NoteProperty -Name dsh -Value ([pscustomobject]@{})
}
if ($null -eq $profile.dsh.PSObject.Properties['profile']) {
    $profile.dsh | Add-Member -MemberType NoteProperty -Name profile -Value ([pscustomobject]@{})
}
$bundles = @()
if ($null -ne $profile.dsh.profile.PSObject.Properties['bundles']) {
    $bundles = @($profile.dsh.profile.bundles)
}
if ($bundles -notcontains $pluginName) {
    $bundles += $pluginName
}
$profile.dsh.profile | Add-Member -MemberType NoteProperty -Name bundles -Value $bundles -Force

$json = $profile | ConvertTo-Json -Depth 20
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($profileManifest, $json + "`n", $utf8)

$check = Get-Content -LiteralPath $profileManifest -Raw -Encoding UTF8 | ConvertFrom-Json
if (@($check.dsh.profile.bundles) -notcontains $pluginName) {
    throw "Failed to add $pluginName to dsh.profile.bundles in $profileManifest"
}

Write-Host ''
Write-Host "Profile:  $profileManifest"
Write-Host "Plugin:   $pluginVersion (vendored at $source)"
Write-Host "Bundles:  $($bundles -join ', ')"
Write-Host ''
Write-Host 'Restart the Bridge so the Host reloads the plugin:'
Write-Host '  powershell -ExecutionPolicy Bypass -File .\scripts\start_bridge.ps1 -Restart'
