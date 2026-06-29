"""Lab probe: synthesize the presentation's narration with NOLAN's OmniVoice
(local voice cloning) — proving the skill's TTS seam can be NOLAN's engine.

Reads the skill's audio-segments.json, batch-synthesizes every segment with the
OmniVoice provider (cloning the given ref voice), and writes wavs named
<chapter>_<step>.wav into an output dir. A separate bash step converts those to
the skill's public/audio/<chapter>/<step>.mp3 layout. NOLAN is used read-only.

Run with the NOLAN env python (Windows), e.g.:
  D:\\env\\nolan\\python.exe web-video-lab/synth_omnivoice.py \
    --segments web-video-lab/human-3.0/presentation/audio-segments.json \
    --out web-video-lab/human-3.0/presentation/.tts_wav \
    --ref voices/shakespeare-narrator/sample.wav
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ref", default=None, help="reference voice wav for cloning (optional)")
    args = ap.parse_args()

    from nolan.config import load_config
    from nolan.tts import create_tts_provider

    cfg = load_config()
    provider = create_tts_provider(cfg.tts)  # OmniVoiceTTS (dedicated CUDA env)

    segs = json.loads(Path(args.segments).read_text(encoding="utf-8"))
    ref = str(Path(args.ref).resolve()) if args.ref else None

    items = []
    for s in segs:
        items.append({
            "id": f"{s['chapter']}_{s['step']}",
            "text": s["text"],
            **({"ref_audio": ref} if ref else {}),
        })

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"synthesizing {len(items)} segments via OmniVoice (ref={'yes' if ref else 'auto'}) …")
    num_step = getattr(cfg.tts.omnivoice, "num_step", 32)
    produced = provider.synthesize_batch(items, out_dir, num_step=num_step)

    ok = 0
    for it in items:
        wav = produced.get(it["id"])
        status = "ok" if wav and Path(wav).exists() else "MISSING"
        if status == "ok":
            ok += 1
        print(f"  {it['id']}: {status}")
    print(f"done: {ok}/{len(items)} wavs in {out_dir}")


if __name__ == "__main__":
    main()
