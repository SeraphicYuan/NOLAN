"""
Asset-binding tests: a scene's asset tray + comments that reference assets by id/label,
instead of pasting paths.

1. deterministic: a photo_brief with {ref:'<id>'} / bare-id images dereferences against
   the scene's `assets`, pulling src + caption(label).
2. real LLM: a comment ("grid of these, zoom the Knight when VO says 'crash'") -> the gate
   resolves asset references to the bound srcs.
"""
import os
import sys
import sqlite3
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
LIB = "_library/images"


def asset(id_, title_like, kind="image"):
    db = sqlite3.connect(os.path.join(LIB, "catalog.db"))
    p, t = db.execute("SELECT path, title FROM assets WHERE status='active' AND title LIKE ? LIMIT 1",
                      (f"%{title_like}%",)).fetchone()
    db.close()
    return {"id": id_, "kind": kind, "src": os.path.abspath(os.path.join(LIB, p)),
            "label": t.strip().rstrip(".").title()}


def test_deref():
    from nolan.brief import resolve_brief, SceneContext
    tray = [asset("a1", "KNIGHT"), asset("a2", "COUNTESS"), asset("a3", "PHYSICIAN")]
    ctx = SceneContext(duration=6.0, assets={a["id"]: a for a in tray})
    brief = {"kind": "photo-story", "layout": "grid", "grid": "1x3",
             "images": [{"ref": "a1"}, "a2", {"ref": "a3"}],   # ref-object, bare-id, ref-object
             "focus": {"image": 0, "at": "start"}}
    spec, msgs = resolve_brief(brief, ctx)
    cards = spec["content"]["cards"]
    print("deref messages:", msgs)
    assert cards[0]["src"] == tray[0]["src"], "ref did not resolve to bound src"
    assert cards[0]["caption"] == "The Knight", cards[0].get("caption")  # label seeded caption
    assert cards[1]["src"] == tray[1]["src"], "bare id did not resolve"
    assert not [m for m in msgs if "not bound" in m], msgs
    print("  OK deref: 3 refs -> bound srcs; captions from labels")


def test_unbound_ref_warns():
    from nolan.brief import resolve_brief, SceneContext
    ctx = SceneContext(duration=6.0, assets={"a1": asset("a1", "KNIGHT")})
    spec, msgs = resolve_brief({"kind": "photo-story", "layout": "grid",
                                "images": [{"ref": "a1"}, {"ref": "missing"}]}, ctx)
    assert any("not bound" in m for m in msgs), msgs
    print("  OK unbound ref warns:", [m for m in msgs if "not bound" in m][0])


async def test_real_llm_reference():
    from nolan.config import load_config
    from nolan.llm import create_text_llm
    from nolan.iterate import revise_scene

    tray = [asset("a1", "KNIGHT"), asset("a2", "COUNTESS"), asset("a3", "PHYSICIAN")]
    scene = {
        "id": "s1", "start_seconds": 0.0, "end_seconds": 6.0,
        "narration_excerpt": "after the great crash everything changed",
        "subtitle_cues": [{"text": "after", "start": 0.2, "end": 0.5},
                          {"text": "the", "start": 0.6, "end": 0.8},
                          {"text": "great", "start": 0.9, "end": 1.3},
                          {"text": "crash", "start": 1.4, "end": 1.9},
                          {"text": "everything", "start": 2.0, "end": 2.6}],
        "assets": tray,
    }
    note = ("Make a 1x3 grid of these three pictures, fly in one by one, and zoom the Knight "
            "to the center when the voiceover says 'crash'.")
    client = create_text_llm(load_config())
    patch = await revise_scene(scene, note, client, "segment")
    spec = patch.get("motion_spec")
    assert spec, f"no motion_spec; patch={patch}"
    srcs = [c["src"] for c in spec["content"]["cards"]]
    bound = {a["src"] for a in tray}
    print("effect:", spec["effect"], "| focusAt:", spec.get("style", {}).get("focusAt"))
    print("cards resolved to bound assets:", all(s in bound for s in srcs))
    assert all(s in bound for s in srcs), f"cards not from the tray: {srcs}"
    print("  OK real-LLM: comment referenced bound assets ->", len(srcs), "cards, all from tray")


def main():
    test_deref()
    test_unbound_ref_warns()
    if "--llm" in sys.argv:
        asyncio.run(test_real_llm_reference())
    print("\nASSET-BINDING TESTS PASS")


if __name__ == "__main__":
    main()
