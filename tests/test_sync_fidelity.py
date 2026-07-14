"""VO↔script fidelity (④) + anchor↔transcript suggestion (⑤) — the two cold-start gaps the homer run hit:
a cloned VO silently dropped a whole sentence, and authors anchored to script phrases Whisper garbled."""
from nolan.hyperframes.sync import _dropped_sentences, _suggest_anchor_span


def test_dropped_sentence_flagged_when_absent():
    spoken = "greece could not yet write the poems were sung by travelling bards".split()
    src = "Greece could not yet write. Heroes are wounded, and then whole again."
    drops = _dropped_sentences(src, spoken)
    assert any("Heroes are wounded" in d["sentence"] for d in drops)          # the dropped line
    assert not any("Greece could not" in d["sentence"] for d in drops)        # this one WAS spoken


def test_no_drop_when_all_spoken():
    spoken = "the poems braid together dialects centuries and hundreds of miles apart".split()
    assert _dropped_sentences("The poems braid together dialects centuries apart.", spoken) == []


def test_suggest_span_for_garbled_anchor():
    stream = "in the nineteen thirties milman perry saw the seams".split()   # Whisper heard 'perry'
    assert _suggest_anchor_span("Milman Parry", stream) == "milman perry"


def test_no_suggestion_when_anchor_is_exact():
    stream = "the wine dark sea rolled on".split()
    assert _suggest_anchor_span("wine dark sea", stream) is None
