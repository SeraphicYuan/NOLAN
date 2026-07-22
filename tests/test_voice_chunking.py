"""A5 (sub-chunking) + A6 (per-section delivery) at the synth-helper level."""

import wave

import numpy as np

from nolan import voice_pipeline as vp


def _write(p, seconds, fr=24000):
    x = (np.sin(2*np.pi*220*np.arange(int(seconds*fr))/fr)*0.3*32767).astype("<i2")
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr); w.writeframes(x.tobytes())


def _dur(p):
    with wave.open(str(p), "rb") as w:
        return round(w.getnframes()/w.getframerate(), 3)


# ---- sentence split ----

def test_split_sentences_basic():
    s = vp._split_sentences("First one. Second one! Third?")
    assert s == ["First one.", "Second one!", "Third?"]


def test_split_sentences_keeps_abbreviations():
    s = vp._split_sentences("Dr. Smith met Mr. Jones today. It went well.")
    assert len(s) == 2 and s[0].startswith("Dr. Smith") and "Mr. Jones" in s[0]


def test_split_to_chunks_packs():
    text = "Aa bb cc. Dd ee ff. Gg hh ii. Jj kk ll."   # 4 sentences × 3 words (capitalized)
    chunks = vp._split_to_chunks(text, max_words=6)     # ≤6 words → 2 sentences per chunk
    assert len(chunks) == 2 and all(len(c.split()) <= 6 for c in chunks)
    assert sum(len(c.split()) for c in chunks) == 12    # total words preserved


def test_split_to_chunks_off():
    assert vp._split_to_chunks("a. b. c.", 0) == ["a. b. c."]


# ---- concat ----

def test_concat_section_wavs_sums_with_gap(tmp_path):
    a, b = tmp_path/"a.wav", tmp_path/"b.wav"
    _write(a, 0.5); _write(b, 0.5)
    dst = tmp_path/"sec.wav"
    vp._concat_section_wavs([a, b], dst, gap_ms=90)
    assert abs(_dur(dst) - (0.5 + 0.09 + 0.5)) < 0.02


# ---- synthesize_sections ----

class _Fake:
    def __init__(self): self.items = None
    def synthesize_batch(self, items, out_dir, num_step=None):
        from pathlib import Path
        self.items = items
        out = {}
        for it in items:
            p = Path(out_dir)/f"{it['id']}.wav"
            _write(p, 0.6)
            out[it["id"]] = p
        return out


def test_synthesize_sections_short_is_single_utterance(tmp_path):
    fake = _Fake()
    out = vp.synthesize_sections(fake, ["short body here"], tmp_path, sub_chunk_words=60)
    assert list(out) == ["sec_0000"] and len(fake.items) == 1
    assert fake.items[0]["id"] == "sec_0000"


def test_synthesize_sections_long_is_chunked_and_concatenated(tmp_path):
    fake = _Fake()
    body = " ".join(f"Sentence number {i} carries a few words." for i in range(12))  # 12 sentences ×7w
    out = vp.synthesize_sections(fake, [body], tmp_path, sub_chunk_words=15)
    # multiple sub-chunk items were synthesized...
    assert len(fake.items) > 1 and all(it["id"].startswith("sec_0000__") for it in fake.items)
    # ...but the result is ONE section wav (count invariant preserved) and it concatenates them
    assert list(out) == ["sec_0000"] and out["sec_0000"].name == "sec_0000.wav"
    assert _dur(out["sec_0000"]) > 0.6                     # longer than one chunk
    # sub-chunk wavs were tidied away
    assert not list(tmp_path.glob("sec_0000__*.wav"))


def test_delivery_instruct_only_when_allowed_and_not_cloning(tmp_path):
    fake = _Fake()   # instruct-capable build (allow_instruct) + no clone → instruct applied
    vp.synthesize_sections(fake, ["a body", "b body"], tmp_path,
                           deliveries=["somber", None], sub_chunk_words=0, allow_instruct=True)
    assert fake.items[0].get("instruct") == "somber"
    assert "instruct" not in fake.items[1]


def test_delivery_dropped_by_default_engine_unsupported(tmp_path):
    """Default: OmniVoice yields no audio for `instruct`, so it is NOT sent even without a clone."""
    fake = _Fake()
    vp.synthesize_sections(fake, ["a body"], tmp_path, deliveries=["somber"], sub_chunk_words=0)
    assert "instruct" not in fake.items[0]


def test_delivery_sent_with_clone_on_capable_engine(tmp_path):
    """On an instruct-capable engine (CosyVoice3), a delivery IS sent alongside the clone —
    clone + emotion in one call (OmniVoice couldn't, but it reports allow_instruct=False)."""
    fake = _Fake()
    vp.synthesize_sections(fake, ["a body"], tmp_path, ref_audio="voice.wav",
                           deliveries=["somber"], sub_chunk_words=0, allow_instruct=True)
    assert fake.items[0].get("instruct") == "somber" and fake.items[0].get("ref_audio") == "voice.wav"


def test_parse_delivery_marker():
    """A6: a `[delivery: ...]` line is captured as the beat's delivery and NOT spoken."""
    from nolan.script import parse_script_sections
    md = ("# S\n## Beat one\n[delivery: somber, measured]\n"
          "The actual spoken line here.\n\n## Beat two\nNo delivery on this beat.\n")
    secs = parse_script_sections(md)
    assert secs[0]["delivery"] == "somber, measured"
    assert secs[0]["body"] == "The actual spoken line here."
    assert "delivery" not in secs[0]["body"] and "somber" not in secs[0]["body"]
    assert secs[1].get("delivery") is None
