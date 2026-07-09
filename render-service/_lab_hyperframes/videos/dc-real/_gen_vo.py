"""Generate the dc-real VO with OmniVoice + word timings with NOLAN whisper, then write
audio_meta.json in the faceless schema {bgm, voices:[{frame,path,duration_s,words:[{text,start,end}]}], sfx}
and sync frame durations into STORYBOARD.md. Run with D:\\env\\nolan\\python.exe -X utf8."""
import sys, json, wave, re
from pathlib import Path

sys.path.insert(0, r"D:\ClaudeProjects\NOLAN\src")
from nolan.config import load_config
from nolan.tts import create_tts_provider
from nolan.whisper import WhisperTranscriber

PROJ = Path(r"D:\ClaudeProjects\NOLAN\render-service\_lab_hyperframes\videos\dc-real")
VOICE_DIR = PROJ / "assets" / "voice"
VOICE_DIR.mkdir(parents=True, exist_ok=True)

LINES = {
    "01": "By twenty thirty, AI data centers could draw twelve percent of all US electricity, up from about four percent today. The epicenter is Virginia, home to the world's densest cluster of data centers.",
    "02": "But the quieter cost is water. A single large data center can drink over a million gallons a day to stay cool, often in towns that are already short on it.",
    "03": "Three forces now collide: power, water, and land. The real question is who pays the bill.",
}

def wav_dur(p: Path) -> float:
    with wave.open(str(p), "rb") as w:
        return round(w.getnframes() / float(w.getframerate()), 3)

def main():
    cfg = load_config()
    provider = create_tts_provider(cfg.tts)
    items = [{"id": i, "text": t} for i, t in LINES.items()]
    print("synthesizing", len(items), "lines with OmniVoice ...", flush=True)
    produced = provider.synthesize_batch(items, VOICE_DIR)
    print("produced:", {k: str(v.name) for k, v in produced.items()}, flush=True)

    wt = WhisperTranscriber()
    voices = []
    for idx, vid in enumerate(["01", "02", "03"], start=1):
        wav = produced.get(vid) or (VOICE_DIR / f"{vid}.wav")
        wav = Path(wav)
        dur = wav_dur(wav)
        words = wt.transcribe_words(wav)
        wjson = [{"id": f"{vid}-{j}", "text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
                 for j, w in enumerate(words) if w.word.strip()]
        voices.append({"frame": idx, "path": f"assets/voice/{vid}.wav", "duration_s": dur, "words": wjson})
        print(f"  frame {idx}: {wav.name}  {dur}s  {len(wjson)} words", flush=True)

    meta = {"bgm": None, "voices": voices, "sfx": []}
    (PROJ / "audio_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    total = round(sum(v["duration_s"] for v in voices), 3)
    print("total voice duration:", total, "s", flush=True)

    # sync frame durations into STORYBOARD.md (narration owns duration)
    sb = PROJ / "STORYBOARD.md"
    text = sb.read_text(encoding="utf-8")
    dur_by_frame = {v["frame"]: v["duration_s"] for v in voices}
    lines = text.splitlines()
    cur = None
    for i, ln in enumerate(lines):
        m = re.match(r"##\s*Frame\s*(\d+)", ln)
        if m:
            cur = int(m.group(1)); continue
        if cur in dur_by_frame and re.match(r"\s*-\s*duration:", ln):
            lines[i] = f"- duration: {dur_by_frame[cur]}s"
            dur_by_frame.pop(cur)
    sb.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("STORYBOARD durations synced.", flush=True)

if __name__ == "__main__":
    main()
