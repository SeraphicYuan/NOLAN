"""The ship stage: subtitles, chapters, the package, and the judge loop.

`nolan/packaging.py` has built chapters/subtitles/titles/thumbnails since SOTA #6 — and reads
`scene_plan.json`, which HF comps do not have, so the DOMINANT pipeline could not reach its own
packaging organ. This is the HF side of that, built as a sibling rather than an adapter because
`build_package` is bound to the Director path in four places at once and renders its thumbnail card
through Remotion (the LEGACY renderer here).

The properties worth pinning are the ones that were WRONG in a first draft and were only caught by
running it:

  * YouTube chapter stamps are `0:00`, not the zero-padded subtitle format — a naive trim of the
    subtitle timestamp produced `:00:00`, and YouTube ignores the entire list when one stamp fails
    to parse. Silently.
  * the judge loop must CONVERGE. Round after round the model re-proposed a title the deterministic
    check had already rejected, so `must_fix` never emptied; and it never returns "ship" on its own,
    so treating its taste notes as blocking meant the loop could only end by exhausting its budget.
  * packaging must REFUSE a stale deliverable — generating titles and thumbnails from a render the
    specs have moved past is how you promote a video you are not shipping.
"""
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"

from nolan.hyperframes import manifest as M               # noqa: E402
from nolan.hyperframes import package as PKG              # noqa: E402
from nolan.hyperframes import ship as SHIP                # noqa: E402
from nolan.hyperframes import subtitles as SUBS           # noqa: E402
from nolan.hyperframes import thumbnail as THUMB          # noqa: E402

_WORDS = ("try to sell your engagement ring back to the jeweler and they will refuse it "
          "because there is no resale market at all").split()


@pytest.fixture()
def comp():
    name = "_hf_ship_pytest"
    dst = VIDEOS / name
    if dst.exists():
        shutil.rmtree(dst)
    fdir = dst / "compositions" / "frames"
    fdir.mkdir(parents=True)
    for i, fid in enumerate(("01-try-to-sell-it-back", "02-the-rock-was-never-rare",
                             "03-lock-the-exit"), 1):
        (fdir / f"{fid}.spec.json").write_text(json.dumps({"frames": [{"id": fid, "dur": 30.0, "scenes": [
            {"id": f"s{i}", "type": "statement", "start": 0, "dur": 30,
             "data": {"lines": [f"beat {i}"]}}]}]}), encoding="utf-8")
    (dst / "hyperframes.json").write_text('{"theme":"kraft-paper"}', encoding="utf-8")
    (dst / "SOURCE.md").write_text(
        "# Video Script\n\n## Try to sell it back\n\n"
        "Try something with me. Take the ring back to the jeweler and ask them to buy it. "
        "They will not. There is no resale market and no price to look up.\n", encoding="utf-8")
    (dst / "audio_meta.json").write_text(json.dumps({"voices": [
        {"frame": 1, "path": "assets/voice/01.wav", "duration_s": 30.0,
         "words": [{"word": w, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, w in enumerate(_WORDS)]},
        {"frame": 2, "path": "assets/voice/02.wav", "duration_s": 30.0, "words": []},
        {"frame": 3, "path": "assets/voice/03.wav", "duration_s": 30.0, "words": []},
    ]}), encoding="utf-8")
    (dst / "renders").mkdir()
    (dst / "renders" / M.DELIVERABLE).write_bytes(b"x")
    try:
        yield name
    finally:
        shutil.rmtree(dst, ignore_errors=True)


# --- subtitles -------------------------------------------------------------------------------------

def test_cues_come_from_the_shipped_caption_groups(comp):
    cd = VIDEOS / comp
    (cd / "caption_groups.json").write_text(json.dumps({"groups": [
        {"start": 0.0, "end": 2.0, "text": "Try something with me."},
        {"start": 2.0, "end": 4.0, "text": "Take the ring back."}]}), encoding="utf-8")
    cs = SUBS.cues(comp)
    assert [c[2] for c in cs] == ["Try something with me.", "Take the ring back."]


def test_it_falls_back_to_the_aligned_words(comp):
    """A comp with no caption groups still gets a subtitle track from the word timings."""
    cs = SUBS.cues(comp)
    assert cs and "sell" in " ".join(c[2] for c in cs)


def test_overlapping_and_zero_length_cues_are_normalised(comp):
    cd = VIDEOS / comp
    (cd / "caption_groups.json").write_text(json.dumps({"groups": [
        {"start": 0.0, "end": 5.0, "text": "one"},        # overlaps the next
        {"start": 2.0, "end": 2.0, "text": "two"},        # zero length
        {"start": 6.0, "end": 7.0, "text": "three"}]}), encoding="utf-8")
    cs = SUBS.cues(comp)
    assert all(e > s for s, e, _ in cs), "YouTube drops zero-length cues"
    assert all(cs[i][1] <= cs[i + 1][0] for i in range(len(cs) - 1)), "…and overlapping ones"


def test_srt_and_vtt_are_written(comp):
    res = SUBS.write(comp)
    assert res["ok"] and res["cues"] > 0
    assert Path(res["srt"]).exists() and Path(res["vtt"]).exists()
    assert Path(res["vtt"]).read_text(encoding="utf-8").startswith("WEBVTT")
    assert "-->" in Path(res["srt"]).read_text(encoding="utf-8")


# --- chapters --------------------------------------------------------------------------------------

def test_chapter_stamps_use_youtubes_format_not_the_subtitle_format():
    """A trimmed subtitle timestamp produced `:00:00`; YouTube then ignores the WHOLE list."""
    assert SUBS.chapter_stamp(0) == "0:00"
    assert SUBS.chapter_stamp(85) == "1:25"
    assert SUBS.chapter_stamp(740.1) == "12:20"
    assert SUBS.chapter_stamp(3723) == "1:02:03"


def test_chapters_are_the_vo_sections(comp):
    chs = SUBS.chapters(comp)
    assert [c["t"] for c in chs] == [0.0, 30.0, 60.0]
    assert chs[0]["title"] == "Try to sell it back", "the frame slug IS the beat's name"


def test_youtube_chapter_constraints_are_asserted(comp):
    chs = SUBS.chapters(comp)
    assert SUBS.youtube_chapter_issues(chs, 90.0) == []
    assert SUBS.youtube_chapter_issues(chs[:2], 90.0), "fewer than 3 chapters is rejected"
    assert SUBS.youtube_chapter_issues([{"t": 4.0, "title": "x"}] + chs[1:], 90.0), \
        "a first chapter that isn't 0:00 is rejected"
    assert SUBS.youtube_chapter_issues(
        [{"t": 0, "title": "a"}, {"t": 3, "title": "b"}, {"t": 40, "title": "c"}], 90.0), \
        "a chapter under 10s is rejected"


# --- the computable half of the title rubric ---------------------------------------------------------

def test_a_title_the_opening_never_pays_off_is_faulted(comp):
    opening = SHIP.opening_text(comp)
    assert SHIP.check_title("Try to sell your engagement ring", opening) == []
    faults = SHIP.check_title("De Beers wrote the rule you still follow", opening)
    assert any("pay it off" in f for f in faults), \
        "judged against the opening, not in isolation — that is what optimises for retention"


def test_length_and_saturated_phrasing_are_computed_not_asked():
    o = "anything"
    assert any("chars" in f for f in SHIP.check_title("x" * 80, o))
    assert any("saturated" in f for f in SHIP.check_title("The Truth About Diamonds", o))


# --- the judge loop --------------------------------------------------------------------------------

def test_the_loop_converges_when_the_computable_rubric_is_clean(comp):
    """The model returns taste notes on every round and never says 'ship'. Treating those as blocking
    means the loop can only end by exhausting its budget — a timeout wearing convergence's clothes."""
    draft = {"titles": ["Try to sell your engagement ring"], "description": "d",
             "thumbnail_briefs": []}
    SHIP.write_draft(comp, draft, 1)

    class _LLM:
        async def generate(self, prompt, system_prompt=None):
            return json.dumps({"verdict": "revise", "must_fix": ["make it punchier"],
                               "title_notes": [], "description_note": "n"})
    rev = SHIP.judge(comp, draft, llm=_LLM())
    assert rev["verdict"] == "ship", "taste notes are advisory; the computable faults block"
    assert rev["notes"] == ["make it punchier"], "…and are surfaced, not discarded"


def test_a_revision_cannot_re_propose_a_rejected_title(comp):
    """Observed live: the model kept re-submitting a title the check had rejected, so `must_fix`
    never emptied. Asking nicely in the prompt is not a mechanism."""
    class _LLM:
        async def generate(self, prompt, system_prompt=None):
            return json.dumps({"titles": ["De Beers wrote the rule you still follow",
                                          "Try to sell your engagement ring"],
                               "description": "d", "thumbnail_briefs": []})
    out = SHIP._apply_review(comp, {"titles": []}, {"must_fix": ["x"]}, llm=_LLM())
    assert "De Beers wrote the rule you still follow" not in out["titles"]
    assert out["titles"] == ["Try to sell your engagement ring"]


def test_versioning_follows_the_script_programs_convention(comp):
    SHIP.write_draft(comp, {"titles": ["a"]}, 1)
    SHIP.write_draft(comp, {"titles": ["b"]}, 2)
    assert SHIP.latest_n(comp) == 2
    assert (SHIP.drafts_dir(comp) / "draft-02.json").exists()
    assert SHIP.load_draft(comp)["titles"] == ["b"]
    assert SHIP.load_draft(comp, 1)["titles"] == ["a"]


def test_no_llm_still_produces_a_draft(comp):
    d = SHIP._fallback_draft(comp, (VIDEOS / comp / "SOURCE.md").read_text(encoding="utf-8"))
    assert d["titles"] and d["generated_by"] == "fallback", "packaging must never block on an LLM"


# --- export mode -----------------------------------------------------------------------------------

def test_export_is_one_self_contained_file(comp):
    out = SHIP.export(comp)
    text = out.read_text(encoding="utf-8")
    assert out.name == "EXPORT.md"
    assert "Chapters" in text and "0:00 Try to sell it back" in text
    assert "Opening 75 seconds" in text and "sell your engagement ring" in text
    assert "kraft-paper" in text
    assert "5 title options" in text, "it must state what it wants, not just dump the script"


def test_export_abridges_rather_than_dumping(comp):
    """A 13-minute script burns the model's context on wording before it can reason about structure."""
    long_script = "\n\n## Beat\n\n" + ("word " * 4000)
    assert len(SHIP._abridge(long_script, keep=2000)) < len(long_script)
    assert "[…]" in SHIP._abridge(long_script, keep=2000)


# --- the package + the stale guard --------------------------------------------------------------------

def test_packaging_refuses_a_stale_deliverable(comp):
    M.write(comp, VIDEOS / comp, mode="whole")
    spec_f = VIDEOS / comp / "compositions" / "frames" / "03-lock-the-exit.spec.json"
    spec = json.loads(spec_f.read_text(encoding="utf-8"))
    spec["frames"][0]["scenes"][0]["data"]["lines"] = ["edited after the render"]
    spec_f.write_text(json.dumps(spec), encoding="utf-8")

    assert PKG.check_fresh(comp)["state"] == "stale"
    with pytest.raises(RuntimeError, match="refusing"):
        PKG.build(comp, llm=False)
    inv = PKG.build(comp, force=True, llm=False)
    assert inv["freshness"] == "stale", "…but force records that it shipped anyway"


def test_the_package_carries_every_artifact(comp):
    inv = PKG.build(comp, llm=False)
    pkg = VIDEOS / comp / "package"
    for f in ("chapters.txt", "subtitles.srt", "PROVENANCE.md", "description.txt",
              "title_options.txt", "package.json"):
        assert (pkg / f).exists(), f"missing {f}"
    assert inv["items"]["subtitle_cues"] > 0
    assert "provenance_summary" in inv["items"]
    assert inv["current_draft"] == 1


def test_the_description_leads_with_the_hook_then_chapters(comp):
    PKG.build(comp, llm=False)
    d = (VIDEOS / comp / "package" / "description.txt").read_text(encoding="utf-8")
    assert d.index("CHAPTERS") > 0 and "0:00 Try to sell it back" in d


# --- thumbnails ---------------------------------------------------------------------------------------

def test_the_layout_registry_matches_what_can_be_rendered():
    """Catalog honesty, the shape `test_block_registry` uses: a layout offered to the LLM that the
    composer cannot draw is a brief that silently falls back."""
    tok = THUMB._tokens("kraft-paper")
    for layout in THUMB.LAYOUTS:
        html = THUMB._compose(layout, "Two Words Here", tok, None, "")
        assert "TWO WORDS" in html.upper(), f"{layout} did not render its headline"
        assert html.startswith("<template>")


def test_an_unknown_layout_falls_back_rather_than_raising():
    tok = THUMB._tokens("kraft-paper")
    assert "<template>" in THUMB._compose("no-such-layout", "Hi There", tok, None)


def test_the_thumbnail_uses_the_essays_own_palette():
    tok = THUMB._tokens("kraft-paper")
    assert tok["surface"].startswith("#eedfc7") and tok["accent"].startswith("#a35b2a")
    assert "Fraunces" in tok["display"], "a thumbnail should look like the video it sells"


def test_the_judge_looks_at_the_feed_size_not_the_render(tmp_path):
    """Scoring a 1920px render passes designs that vanish where the decision is made."""
    from PIL import Image
    big = tmp_path / "t.png"
    Image.new("RGB", (1280, 720), (238, 223, 199)).save(big)
    small = THUMB.feed_preview(big)
    assert small and Image.open(small).size == (THUMB.FEED_W, THUMB.FEED_H)
    import inspect
    assert "feed_preview" in inspect.getsource(THUMB.score)
