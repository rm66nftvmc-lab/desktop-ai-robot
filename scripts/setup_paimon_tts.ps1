$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$userRoot = Join-Path $env:LOCALAPPDATA "DesktopAiRobot\tts-paimon"
$ttsPython = Join-Path $userRoot ".venv\Scripts\python.exe"
$projectPython = Join-Path $project ".venv\Scripts\python.exe"
$requirements = Join-Path $PSScriptRoot "requirements-paimon.txt"
$constraint = Join-Path $userRoot "torch-constraints.txt"
$wheelDir = Join-Path $userRoot "wheels"
$torchWheel = Join-Path $wheelDir "torch-2.7.1+cu128-cp312-cp312-win_amd64.whl"

if (-not (Test-Path $ttsPython)) { throw "Missing isolated GPT-SoVITS Python: $ttsPython" }
if (-not (Test-Path $requirements)) { throw "Missing GPT-SoVITS requirements: $requirements" }
if (-not (Test-Path $projectPython)) { throw "Missing project Python: $projectPython" }

@"
torch==2.7.1+cu128
torchaudio==2.7.1+cu128
transformers==4.50.3
peft==0.15.2
fast_langdetect==0.3.1
numpy<2
"@ | Set-Content -Encoding ascii $constraint

New-Item -ItemType Directory -Force -Path $wheelDir | Out-Null
if (-not (Test-Path $torchWheel) -or (Get-Item $torchWheel).Length -ne 3273024349) {
    curl.exe -L --fail --retry 5 --retry-all-errors --retry-delay 2 -C - -o $torchWheel `
        "https://download-r2.pytorch.org/whl/cu128/torch-2.7.1%2Bcu128-cp312-cp312-win_amd64.whl"
    if ($LASTEXITCODE -ne 0) { throw "PyTorch CUDA 12.8 download failed" }
}
if ((Get-Item $torchWheel).Length -ne 3273024349) { throw "PyTorch wheel size mismatch; partial download preserved" }
& $ttsPython -m pip install $torchWheel
if ($LASTEXITCODE -ne 0) { throw "PyTorch CUDA 12.8 installation failed" }
& $ttsPython -m pip install torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw "TorchAudio installation failed" }
& $ttsPython -m pip install -r $requirements --constraint $constraint --extra-index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw "GPT-SoVITS dependency installation failed" }
& $projectPython (Join-Path $PSScriptRoot "prepare_paimon_runtime.py")
if ($LASTEXITCODE -ne 0) { throw "GPT-SoVITS compatibility preparation failed" }
Push-Location (Join-Path $userRoot "repo")
try {
    & $ttsPython api.py --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "GPT-SoVITS import smoke check failed" }
} finally { Pop-Location }
& $projectPython (Join-Path $project "scripts\download_paimon_models.py")
if ($LASTEXITCODE -ne 0) { throw "Paimon model download failed" }
"GPT-SoVITS runtime and Paimon model assets installed on $(Get-Date -Format o)" |
    Set-Content -Encoding utf8 (Join-Path $userRoot "INSTALL_COMPLETE.txt")

Write-Host "Paimon local TTS installation complete. Restart Bridge and select Paimon to audition."
