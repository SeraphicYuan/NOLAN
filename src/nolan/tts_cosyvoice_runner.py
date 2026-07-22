"""Standalone CosyVoice3 batch runner — invoked by CosyVoiceTTS in the dedicated
`cosyvoice` conda env (NOT the nolan env). Reads a JSONL of items and writes one 16-bit
PCM wav per id, so the nolan pipeline stays engine-agnostic.

Handles the three CosyVoice3 input rules learned from the probe: 16 kHz reference,
`<|endofprompt|>` prompt structure, and float32→PCM16 output. An `instruct` (delivery)
routes to inference_instruct2 (clone + emotion in one call); otherwise inference_zero_shot.

Deliberately imports ONLY stdlib + the CosyVoice repo (no `nolan`), because it runs under
a different Python. Usage:
    <cosyvoice-python> tts_cosyvoice_runner.py --test_list x.jsonl --res_dir out \
        --model_dir pretrained_models/Fun-CosyVoice3-0.5B --repo D:\\env\\CosyVoice-src \
        [--neutral_instruct "calm, measured"]
"""
import argparse
import json
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test_list", required=True)
    ap.add_argument("--res_dir", required=True)
    ap.add_argument("--model_dir", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--neutral_instruct", default="")
    args = ap.parse_args()

    # This file lives in src/nolan, which Python auto-adds to sys.path[0] — and nolan modules
    # (e.g. packaging.py) would shadow the real libraries CosyVoice/modelscope import. Drop it.
    _self = os.path.dirname(os.path.abspath(__file__))
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _self]

    os.chdir(args.repo)                                   # relative model_dir + assets resolve here
    sys.path.insert(0, os.path.join(args.repo, "third_party", "Matcha-TTS"))
    sys.path.insert(0, args.repo)
    import torch
    import torchaudio
    from cosyvoice.cli.cosyvoice import AutoModel

    cv = AutoModel(model_dir=args.model_dir)
    sr = cv.sample_rate
    os.makedirs(args.res_dir, exist_ok=True)

    ref_cache = {}

    def ref16(path):
        """CosyVoice wants a 16 kHz mono reference; cache the resample per source path."""
        if path not in ref_cache:
            w, s = torchaudio.load(path)
            if w.shape[0] > 1:
                w = w.mean(0, keepdim=True)
            if s != 16000:
                w = torchaudio.transforms.Resample(s, 16000)(w)
            p = os.path.join(args.res_dir, f"_ref16_{len(ref_cache)}.wav")
            torchaudio.save(p, w, 16000)
            ref_cache[path] = p
        return ref_cache[path]

    with open(args.test_list, encoding="utf-8") as f:
        items = [json.loads(line) for line in f if line.strip()]

    for it in items:
        sid, text = it["id"], it["text"]
        ref, rt = it.get("ref_audio"), (it.get("ref_text") or "")
        instruct = it.get("instruct") or args.neutral_instruct or None
        try:
            if not ref:
                print(f"SKIP {sid}: no ref_audio (CosyVoice needs a reference)", flush=True)
                continue
            r16 = ref16(ref)
            if instruct:
                prompt = f"You are a helpful assistant. Please speak in a {instruct} tone.<|endofprompt|>"
                gen = cv.inference_instruct2(text, prompt, r16, stream=False)
            else:
                gen = cv.inference_zero_shot(text, "You are a helpful assistant.<|endofprompt|>" + rt,
                                             r16, stream=False)
            chunks = [j["tts_speech"] for j in gen]
            if not chunks:
                print(f"EMPTY {sid}", flush=True)
                continue
            audio = torch.cat(chunks, dim=1) if len(chunks) > 1 else chunks[0]
            torchaudio.save(os.path.join(args.res_dir, sid + ".wav"), audio, sr,
                            encoding="PCM_S", bits_per_sample=16)
            print(f"OK {sid} {audio.shape[1] / sr:.2f}s", flush=True)
        except Exception as e:  # noqa: BLE001 - report per item, keep going
            print(f"FAIL {sid} {type(e).__name__}: {str(e)[:200]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
