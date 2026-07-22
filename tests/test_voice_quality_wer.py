"""P5.1: WER scorer — pure logic (Whisper-free)."""

import wave

import numpy as np
import pytest

from nolan.voice_quality import normalize_words, word_error_rate, score_section, score_voiceover


@pytest.mark.parametrize("ref,hyp,expected", [
    (["a", "b", "c"], ["a", "b", "c"], 0.0),          # perfect
    (["a", "b", "c"], ["a", "x", "c"], 0.333),         # 1 substitution / 3
    (["a", "b"], ["a", "b", "c"], 0.5),                # 1 insertion / 2
    (["a", "b", "c"], ["a", "c"], 0.333),              # 1 deletion / 3
    ([], [], 0.0),                                     # both empty
    ([], ["a"], 1.0),                                  # empty ref, some hyp
    (["a", "b"], [], 1.0),                             # all deleted
])
def test_word_error_rate(ref, hyp, expected):
    assert word_error_rate(ref, hyp) == expected


def test_normalize_words_speaks_numbers():
    assert normalize_words("In 1888, prices rose 90%!") == \
        ["in", "eighteen", "eighty", "eight", "prices", "rose", "ninety", "percent"]


def test_score_section_perfect_and_garbled():
    # a transcriber that returns the spoken form → WER 0
    perfect = score_section("x", "The price rose 90 percent.",
                            transcribe=lambda w: "the price rose ninety percent")
    assert perfect["wer"] == 0.0 and perfect["ref_words"] == 5
    # a transcriber that garbles two words → WER > 0
    bad = score_section("x", "The price rose ninety percent.",
                        transcribe=lambda w: "the price fell nineteen percent")
    assert bad["wer"] > 0.0


def _write(p, seconds=0.6, fr=24000):
    x = (np.sin(2*np.pi*220*np.arange(int(seconds*fr))/fr)*0.3*32767).astype("<i2")
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr); w.writeframes(x.tobytes())


def test_score_voiceover_flags_high_wer(tmp_path):
    work = tmp_path / "_work"; work.mkdir()
    _write(work / "sec_0000.wav"); _write(work / "sec_0001.wav")   # sec 2 missing on disk
    sections = [{"body": "clean beat one"}, {"body": "clean beat two"}, {"body": "no wav here"}]
    # sec 0 transcribes perfectly, sec 1 garbled
    def fake(wav):
        return "clean beat one" if wav.name == "sec_0000.wav" else "totally different words spoken"
    rep = score_voiceover(tmp_path, sections, transcribe=fake, wer_warn=0.3)
    assert rep["sections"][0]["wer"] == 0.0 and rep["sections"][0]["flag"] is False
    assert rep["sections"][1]["flag"] is True
    assert rep["sections"][2]["present"] is False
    assert rep["flagged"] == [1] and rep["mean_wer"] is not None
