# OmniVoice (local TTS + voice cloning) — setup

NOLAN's local text-to-speech and zero-shot voice cloning is powered by
[OmniVoice](https://github.com/k2-fsa/OmniVoice) (Apache-2.0). It runs in its own
isolated conda env so the heavy CUDA/PyTorch stack never pollutes the lean
`nolan` env — the same way ComfyUI is kept separate.

## Why a separate env
The `nolan` env ships **CPU-only PyTorch** on purpose. OmniVoice is a PyTorch
diffusion model that needs CUDA. Installing CUDA torch into `nolan` would bloat it
and risk conflicts, so OmniVoice lives in `D:\env\omnivoice` and NOLAN shells out
to it for voiceover jobs.

## Prerequisites
- NVIDIA GPU + recent driver (you have an RTX 4090).
- `conda` on PATH.
- Note on VRAM: ComfyUI keeps its model resident (~18 GB on a busy session).
  OmniVoice and ComfyUI are **serialized through a shared GPU lock** in NOLAN so
  they never run at the same time, and a voiceover job can optionally ask ComfyUI
  to free VRAM first. The POC below reports OmniVoice's actual footprint.

## Install (run once)
From the repo root in a normal PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_omnivoice.ps1
```

This creates `D:\env\omnivoice`, installs CUDA torch (cu128) + `omnivoice`, and
verifies CUDA is visible. (If your driver is older than CUDA 12.8, edit the `cu128`
tags in the script to match.)

## Validate (downloads the model on first run)
```powershell
conda run -p D:\env\omnivoice python scripts\omnivoice_poc.py
# clone a voice from a reference clip (3-10s):
conda run -p D:\env\omnivoice python scripts\omnivoice_poc.py --ref_audio ref.wav
```
It prints **peak VRAM** and **RTF** (real-time factor) and writes `omnivoice_poc.wav`.
If HuggingFace is slow, set `HF_ENDPOINT=https://hf-mirror.com` before running.

## Point NOLAN at it
Add to `nolan.yaml`:

```yaml
tts:
  enabled: true
  provider: omnivoice
  omnivoice:
    env_python: D:\env\omnivoice\python.exe
    model: k2-fsa/OmniVoice
    num_step: 32          # 16 = faster, 32 = higher quality
    free_comfyui_vram: true   # ask ComfyUI to unload before a voiceover job
```

Once set, the Hub's **Voices** page can clone voices (from an upload or a saved
Clip's audio) and generate a project's `assets/voiceover/voiceover.mp3` from its
`script.json`, after which `nolan align` derives audio-accurate scene timings.

## Voice cloning notes
- Reference clip: **3–10 s**, clean speech, same language as the target for the
  most natural result.
- Reference text is optional — OmniVoice auto-transcribes it with Whisper.
