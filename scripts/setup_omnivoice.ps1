# ============================================================
#  NOLAN — OmniVoice (local TTS + voice cloning) env setup
#  Creates an ISOLATED conda env so the heavy CUDA/torch stack
#  never touches the lean `nolan` env. Run this once.
#
#  Usage (from repo root, in a normal PowerShell):
#     powershell -ExecutionPolicy Bypass -File scripts\setup_omnivoice.ps1
#
#  Requires: conda on PATH, an NVIDIA GPU + recent driver.
# ============================================================

$ErrorActionPreference = "Stop"
$EnvPrefix = "D:\env\omnivoice"   # sibling of D:\env\nolan

Write-Host "==> Creating conda env at $EnvPrefix (python 3.11)..." -ForegroundColor Cyan
conda create -y --prefix $EnvPrefix python=3.11

Write-Host "==> Upgrading pip..." -ForegroundColor Cyan
conda run -p $EnvPrefix python -m pip install --upgrade pip

# PyTorch with CUDA 12.8 (per OmniVoice README). Adjust cuXXX if your driver is older.
Write-Host "==> Installing CUDA PyTorch (cu128)..." -ForegroundColor Cyan
conda run -p $EnvPrefix pip install torch==2.8.0+cu128 torchaudio==2.8.0+cu128 --extra-index-url https://download.pytorch.org/whl/cu128

Write-Host "==> Installing omnivoice + soundfile..." -ForegroundColor Cyan
conda run -p $EnvPrefix pip install omnivoice soundfile

Write-Host "==> Verifying CUDA is visible to torch..." -ForegroundColor Cyan
conda run -p $EnvPrefix python -c "import torch; print('cuda_available', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-')"

Write-Host ""
Write-Host "Done. Env python: $EnvPrefix\python.exe" -ForegroundColor Green
Write-Host "Next: run the POC (downloads the model on first run, ~once):" -ForegroundColor Green
Write-Host "  conda run -p $EnvPrefix python scripts\omnivoice_poc.py" -ForegroundColor Green
Write-Host ""
Write-Host "Then point NOLAN at it in nolan.yaml:" -ForegroundColor Green
Write-Host "  tts:" -ForegroundColor Green
Write-Host "    enabled: true" -ForegroundColor Green
Write-Host "    provider: omnivoice" -ForegroundColor Green
Write-Host "    omnivoice:" -ForegroundColor Green
Write-Host "      env_python: D:\env\omnivoice\python.exe" -ForegroundColor Green
