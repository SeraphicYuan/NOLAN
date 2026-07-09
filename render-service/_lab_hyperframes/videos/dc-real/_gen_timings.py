"""Reuse the OmniVoice wavs, get word timings with CPU whisper, build audio_meta.json,
sync STORYBOARD durations. Run with D:\\env\\nolan\\python.exe -X utf8."""
import sys, json, wave, re
from pathlib import Path
sys.path.insert(0, r"D:\ClaudeProjects\NOLAN\src")
from nolan.whisper import WhisperTranscriber, WhisperConfig

PROJ = Path(r"D:\ClaudeProjects\NOLAN\render-service\_lab_hyperframes\videos\dc-real")
VOICE_DIR = PROJ / "assets" / "voice"

def wav_dur(p: Path) -> float:
    with wave.open(str(p), "rb") as w:
        return round(w.getnframes() / float(w.getframerate()), 3)

wt = WhisperTranscriber(WhisperConfig(model_size="base", device="cpu", compute_type="int8"))
voices = []
for idx, vid in enumerate(["01", "02", "03"], start=1):
    wav = VOICE_DIR / f"{vid}.wav"
    dur = wav_dur(wav)
    words = wt.transcribe_words(wav)
    wjson = [{"id": f"{vid}-{j}", "text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
             for j, w in enumerate(words) if w.word.strip()]
    voices.append({"frame": idx, "path": f"assets/voice/{vid}.wav", "duration_s": dur, "words": wjson})
    print(f"frame {idx}: {wav.name}  {dur}s  {len(wjson)} words  | first: {wjson[0]['text']!r}@{wjson[0]['start']}s  last: {wjson[-1]['text']!r}@{wjson[-1]['end']}s", flush=True)

meta = {"bgm": None, "voices": voices, "sfx": []}
(PROJ / "audio_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
print("total voice duration:", round(sum(v["duration_s"] for v in voices), 3), "s", flush=True)

# narration owns duration → write real durations into STORYBOARD.md
sb = PROJ / "STORYBOARD.md"
lines = sb.read_text(encoding="utf-8").splitlines()
dur_by_frame = {v["frame"]: v["duration_s"] for v in voices}
cur = None
for i, ln in enumerate(lines):
    m = re.match(r"##\s*Frame\s*(\d+)", ln)
    if m:
        cur = int(m.group(1)); continue
    if cur in dur_by_frame and re.match(r"\s*-\s*duration:", ln):
        lines[i] = f"- duration: {dur_by_frame[cur]}s"
sb.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("STORYBOARD durations synced:", dur_by_frame, flush=True)
