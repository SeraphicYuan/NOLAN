"""OmniVoice proof-of-concept / smoke test for NOLAN.

Run inside the dedicated omnivoice env (see scripts/setup_omnivoice.ps1):
    conda run -p D:\\env\\omnivoice python scripts\\omnivoice_poc.py
    conda run -p D:\\env\\omnivoice python scripts\\omnivoice_poc.py --ref_audio ref.wav

It loads the model, generates a short sample (cloning the reference if given),
and reports the two numbers we care about for coexistence with ComfyUI:
peak VRAM and the real-time factor (RTF).
"""

import argparse
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="Hello from NOLAN. This is an OmniVoice "
                    "text to speech test running on the local GPU.")
    ap.add_argument("--ref_audio", default=None, help="3-10s reference clip to clone")
    ap.add_argument("--ref_text", default=None, help="transcript of ref (auto if omitted)")
    ap.add_argument("--out", default="omnivoice_poc.wav")
    ap.add_argument("--model", default="k2-fsa/OmniVoice")
    args = ap.parse_args()

    import torch
    import numpy as np
    from omnivoice import OmniVoice

    print("CUDA available:", torch.cuda.is_available(),
          torch.cuda.get_device_name(0) if torch.cuda.is_available() else "(cpu)")
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32

    t0 = time.time()
    model = OmniVoice.from_pretrained(args.model, device_map=device, dtype=dtype)
    print(f"model loaded in {time.time()-t0:.1f}s")

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()

    kw = {"text": args.text}
    if args.ref_audio:
        kw["ref_audio"] = args.ref_audio
    if args.ref_text:
        kw["ref_text"] = args.ref_text

    t1 = time.time()
    audio = model.generate(**kw)
    gen_s = time.time() - t1

    wav = audio[0] if isinstance(audio, (list, tuple)) else audio
    wav = np.asarray(wav, dtype=np.float32)
    audio_s = len(wav) / 24000.0

    try:
        import soundfile as sf
        sf.write(args.out, wav, 24000)
    except Exception:
        import torchaudio
        torchaudio.save(args.out, torch.from_numpy(wav).unsqueeze(0), 24000)

    print(f"generated {audio_s:.1f}s of audio in {gen_s:.1f}s  (RTF {gen_s/max(audio_s,1e-6):.3f})")
    if torch.cuda.is_available():
        print(f"peak VRAM: {torch.cuda.max_memory_allocated()/1e9:.2f} GB")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
