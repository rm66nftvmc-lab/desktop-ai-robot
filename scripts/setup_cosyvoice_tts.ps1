$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$directory = Join-Path $env:LOCALAPPDATA "DesktopAiRobot\tts-cosyvoice"
$python = Join-Path $directory ".venv\Scripts\python.exe"
$repo = Join-Path $directory "repo"
$revision = "074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc"
$projectPython = Join-Path $project ".venv\Scripts\python.exe"
if (-not (Test-Path $projectPython)) { throw "Install the Bridge Python environment first" }
New-Item -ItemType Directory -Force $directory | Out-Null
if (-not (Test-Path $repo)) {
    git clone https://github.com/QwenAudio/CosyVoice.git $repo
    if ($LASTEXITCODE -ne 0) { throw "CosyVoice clone failed" }
    git -C $repo checkout $revision
    if ($LASTEXITCODE -ne 0) { throw "Pinned revision checkout failed" }
}
$actual = git -C $repo rev-parse HEAD
if ($actual -ne $revision) { throw "CosyVoice source revision differs; preserving existing checkout" }
git -C $repo submodule update --init --recursive
if ($LASTEXITCODE -ne 0) { throw "Matcha dependency checkout failed" }
if (-not (Test-Path $python)) {
    & $projectPython -m venv (Join-Path $directory ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Environment creation failed" }
}
$wheelDirectory = Join-Path $env:LOCALAPPDATA "DesktopAiRobot\tts-paimon\wheels"
New-Item -ItemType Directory -Force $wheelDirectory | Out-Null
$wheel = Join-Path $wheelDirectory "torch-2.7.1+cu128-cp312-cp312-win_amd64.whl"
if (-not (Test-Path $wheel) -or (Get-Item $wheel).Length -ne 3273024349) {
    curl.exe -L --fail --retry 4 -C - -o $wheel "https://download-r2.pytorch.org/whl/cu128/torch-2.7.1%2Bcu128-cp312-cp312-win_amd64.whl"
    if ($LASTEXITCODE -ne 0) { throw "PyTorch CUDA download failed" }
}
& $python -m pip install $wheel torchaudio==2.7.1 --extra-index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw "PyTorch installation failed" }
& $python -m pip install -r (Join-Path $PSScriptRoot "requirements-cosyvoice.txt")
if ($LASTEXITCODE -ne 0) { throw "CosyVoice inference dependencies failed" }
& $projectPython (Join-Path $PSScriptRoot "download_cosyvoice_models.py")
if ($LASTEXITCODE -ne 0) { throw "Model download/checksum failed" }
# The final smoke check synthesizes locally before enabling this voice in Bridge.
& $python (Join-Path $PSScriptRoot "smoke_cosyvoice.py")
if ($LASTEXITCODE -ne 0) { throw "Local synthesis smoke check failed" }
"Local synthesis verified $(Get-Date -Format o)" | Set-Content -Encoding utf8 (Join-Path $directory "INSTALL_COMPLETE.txt")
Write-Host "CosyVoice installed locally. Original voices remain available."
