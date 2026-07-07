"""Render one short preview clip per authorable catalog entry (the /showcase gallery).

Rewritten 2026-07 for the registry-backed showcase: renders through the SAME
paths the pipeline uses (nolan.motion.executor for motion effects,
nolan.layout_blocks for block templates) — NOT the removed render-service preset
endpoint. Each 1080p mp4 is transcoded to a small looping webm committed under
render-service/public/previews/<id>.webm, so the gallery thumbnails load offline.

Version-stamping: previews/_manifest.json records a hash of (component source +
fixture). A clip is re-rendered only when its hash changes (or --force), and a
stale preview (component changed after its clip) can be detected from the manifest.

Run with the Windows env python:
    D:\\env\\nolan\\python.exe -X utf8 scripts/gen_showcase_previews.py [--force] [ids...]

A catalog entry with no FIXTURE is reported LOUDLY and skipped (never silently),
so coverage gaps are visible. tests/test_preview_fixtures.py enforces motion
coverage.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / "render-service" / "remotion-lib" / "public"
OUT = ROOT / "render-service" / "public" / "previews"
LIB_SRC = ROOT / "render-service" / "remotion-lib" / "src"
THEME = "dark-editorial"          # motion comps: resolveTheme alias (_active-theme.json)
BLOCK_THEME = "midnight-press"    # blocks render via Chapter/stage.mjs which reads themes/<dir>/tokens.css

# sample media already staged in public/
I1 = str(PUB / "02_throne_hall.png")
I2 = str(PUB / "01_rider_gate.png")
I3 = str(PUB / "03_warrior_valley.png")

# id -> {content, style?}; media as absolute paths (the executor stages them).
FIXTURES: dict[str, dict] = {
    # ---- motion effects ----
    "kinetic-text": {"content": {"text": "The center cannot hold", "highlights": ["center"]}},
    "bar-compare": {"content": {"title": "Revenue", "bars": [{"label": "2019", "value": 12}, {"label": "2024", "value": 48}], "suffix": "B"}},
    "k-shape": {"content": {"title": "The Great Divergence", "topLabel": "Capital", "bottomLabel": "Labor"}},
    "annotate-stat": {"content": {"value": "$28,000", "label": "per capita"}},
    "route-map": {"content": {"title": "The Voyage", "pins": [{"x": 0.22, "y": 0.34, "label": "Troy"}, {"x": 0.72, "y": 0.6, "label": "Ithaca"}], "mapSrc": I1}},
    "premium-card": {"content": {"title": "The Return", "subtitle": "Book One", "kicker": "THE ODYSSEY"}},
    "timeline": {"content": {"start": -800, "end": -700, "markers": [{"year": -750, "label": "Homer"}, {"year": -720, "label": "Iliad"}]}},
    "counter": {"content": {"value": 300, "label": "Spartans", "suffix": ""}},
    "title": {"content": {"title": "WE ARE HERE", "subtitle": "and nowhere else"}},
    "lower-third": {"content": {"name": "Odysseus", "title": "King of Ithaca"}},
    "comparison": {"content": {"left_text": "Sparta", "right_text": "Athens", "center_label": "VS"}},
    "line-chart": {"content": {"points": [["2019", 10], ["2020", 22], ["2021", 61]], "title": "Going vertical"}},
    "loop-diagram": {"content": {"nodes": ["Fear", "Anger", "Hate", "Suffering"], "title": "The Cycle"}},
    "photo-montage-pro": {"content": {"cards": [{"src": I1, "x": 0.32, "y": 0.4}, {"src": I2, "x": 0.66, "y": 0.55}, {"src": I3, "x": 0.5, "y": 0.35}]}},
    "photo-grid": {"content": {"cards": [{"src": p} for p in [I1, I2, I3, I1, I2, I3, I1, I2, I3]], "cols": 3, "rows": 3}},
    "still-motion": {"content": {"image": I1, "treatment": "ken-burns-in"}},
    "split-screen": {"content": {"left": I1, "right": I2, "left_label": "Then", "right_label": "Now"}},
    "stat-over": {"content": {"image": I1, "value": 50000, "caption": "in the stadium"}},
    "clip-montage": {"content": {"clips": [{"path": I1, "kind": "image", "duration": 1.2}, {"path": I2, "kind": "image", "duration": 1.2}, {"path": I3, "kind": "image", "duration": 1.2}]}},
    # ---- the 7 gap effects ----
    "screen-frame": {"content": {"background": I1, "url": "nolan.studio/essays", "label": "The dashboard"}, "style": {"device": "browser"}},
    "camera-shake": {"content": {"background": I1, "label": "IMPACT"}, "style": {"intensity": 0.7}},
    "bar-race": {"content": {"title": "Model scores over time", "bars": [{"label": "GPT", "value": 82}, {"label": "Claude", "value": 95}, {"label": "Gemini", "value": 78}, {"label": "Llama", "value": 61}]}},
    "typewriter": {"content": {"text": "rm -rf / --no-preserve-root"}, "style": {"mode": "type"}},
    "before-after": {"content": {"background": I1, "foreground": I2, "before_label": "1990", "after_label": "2026"}},
    "whip-transition": {"content": {"background": I1, "foreground": I2}, "style": {"direction": "left"}},
    "picture-in-picture": {"content": {"background": I1, "foreground": I2, "inset_label": "LIVE"}, "style": {"corner": "br"}},

    # ---- block templates (layout_blocks) — params per each adapter's schema ----
    # (counter/title/comparison/timeline collide with motion ids and share those
    #  previews via the harness dedupe, so they need no separate block fixture.)
    "quote": {"content": {"quote": "Man is condemned to be free.", "attribution": "Jean-Paul Sartre"}},
    "pull_quote": {"content": {"quote": "The unexamined life is not worth living.", "attribution": "Socrates", "highlight_words": ["unexamined"]}},
    "definition": {"content": {"term": "Hubris", "definition": "Excessive pride or self-confidence that invites downfall."}},
    "statistic": {"content": {"value": 4.4, "label": "average score", "suffix": "%"}},
    "ranking": {"content": {"title": "Top exporters", "items": [["China", "$3.6T"], ["USA", "$2.1T"], ["Germany", "$1.7T"]]}},
    "stat_comparison": {"content": {"title": "Before / after", "left_value": "4.4%", "left_label": "2019", "right_value": "12%", "right_label": "2024"}},
    "question": {"content": {"question": "What does it cost to become yourself?", "context": "The central question of the essay"}},
    "chapter_card": {"content": {"title": "The Descent", "subtitle": "Book Eleven", "chapter_number": 11}},
    "section_divider": {"content": {"title": "Meanwhile, in Ithaca", "subtitle": ""}},
    "list": {"content": {"title": "The three temptations", "items": ["The Lotus", "The Sirens", "The Cattle of the Sun"]}},
    "lower_third": {"content": {"name": "Telemachus", "title": "Son of Odysseus"}},
    "source_citation": {"content": {"source_name": "The Odyssey", "author": "Homer", "publication": "Book IX", "date": "c. 700 BC"}},
    "verdict": {"content": {"verdict": "The prophecy was self-fulfilling.", "supporting_text": "Every attempt to avoid it caused it.", "verdict_type": "confirmed"}},
    "location_stamp": {"content": {"location": "Ithaca", "sublocation": "The Ionian Sea", "date": "Dawn"}},
    "progress_bar": {"content": {"progress": 0.68, "label": "Voyage home", "milestone_labels": ["Troy", "Circe", "Ithaca"]}},
    "percentage_bar": {"content": {"percentage": 43, "label": "of the fleet lost", "context": "by the tenth year"}},
    "tweet_card": {"content": {"content": "the sea does not reward those who are too anxious.", "username": "Odysseus", "handle": "@ithaca_king", "likes": 3200, "verified": True}},
    "news_headline": {"content": {"headline": "TROY FALLS AFTER TEN-YEAR SIEGE", "source": "Aegean Herald", "news_type": "breaking"}},
    "document_highlight": {"content": {"text": "Sing to me of the man, Muse, the man of twists and turns.", "highlight_text": "twists and turns", "document_title": "The Odyssey"}},
    "bar_chart": {"content": {"title": "Ships lost by cause", "bars": [{"label": "Storm", "value": 6}, {"label": "Cyclops", "value": 1}, {"label": "Scylla", "value": 1}], "unit": ""}},
    "line_chart": {"content": {"title": "Crew remaining", "points": [[1, 600], [5, 400], [9, 45], [10, 1]]}},
    "pie_percentage": {"content": {"percentage": 43, "title": "Fleet lost", "text": "Nearly half the ships never left the Aegean.", "slice_label": "lost"}},
    "data_table": {"content": {"columns": ["Trial", "Result"], "rows": [["Lotus Eaters", "escaped"], ["Cyclops", "blinded"], ["Sirens", "survived"]], "highlight_row": 1, "caption": "The trials"}},
    "image_compare": {"content": {"left": {"src": I1, "label": "The palace"}, "right": {"src": I2, "label": "The road home"}, "kicker": "Then / Now", "verdict": "Everything had changed."}},
    "kinetic_headline": {"content": {"text": "Nobody is my name", "accent_words": ["Nobody"]}},
    "detail_loupe": {"content": {"src": I1, "region": [0.34, 0.3, 0.24, 0.24], "label": "The throne"}},
    "loop_diagram": {"content": {"title": "The cycle of wrath", "nodes": ["Insult", "Rage", "Vengeance", "Grief"], "center_label": "Wrath"}},
}


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _hash(entry_id: str, target: str, fx: dict) -> str:
    src = LIB_SRC / f"{target}.tsx"
    h = hashlib.sha1()
    h.update(json.dumps(fx, sort_keys=True).encode())
    if src.exists():
        h.update(src.read_bytes())
    return h.hexdigest()[:16]


def _to_webm(mp4: Path, webm: Path) -> None:
    subprocess.run([_ffmpeg(), "-y", "-i", str(mp4), "-an",
                    "-vf", "scale=640:-2", "-c:v", "libvpx-vp9", "-b:v", "0",
                    "-crf", "36", "-pix_fmt", "yuv420p", str(webm)],
                   capture_output=True, check=True)


def render_entry(entry: dict, fx: dict, force: bool, manifest: dict) -> tuple[str, str]:
    from nolan.motion.spec import validate
    from nolan.motion import executor
    from nolan import layout_blocks

    eid, kind, target = entry["id"], entry["kind"], entry["target"]
    webm = OUT / f"{eid}.webm"
    hsh = _hash(eid, target, fx)
    if not force and webm.exists() and manifest.get(eid) == hsh:
        return eid, "cached"

    dur = 4.0
    tmp = OUT / f"_tmp_{eid}.mp4"
    try:
        if kind == "block":
            out = layout_blocks.render_layout_block(eid, dict(fx.get("content", {})), dur, tmp, theme=BLOCK_THEME, scene_id=eid)
            if out is None:
                return eid, "no-adapter"
        else:
            spec = {"effect": eid, "content": dict(fx.get("content", {})),
                    "style": dict(fx.get("style", {})), "theme": THEME, "duration": dur}
            norm, probs = validate(spec)
            if probs:
                return eid, f"invalid: {probs[0][:60]}"
            executor.render(norm, tmp)
        _to_webm(tmp, webm)
        tmp.unlink(missing_ok=True)
        manifest[eid] = hsh
        return eid, "ok"
    except Exception as ex:
        tmp.unlink(missing_ok=True)
        return eid, f"FAIL: {str(ex)[-90:]}"


def main() -> None:
    from nolan.webui.showcase_catalog import build_showcase_catalog
    OUT.mkdir(parents=True, exist_ok=True)
    force = "--force" in sys.argv
    want = {a for a in sys.argv[1:] if not a.startswith("-")}

    cat = build_showcase_catalog(ROOT)
    entries = [e for e in cat["effects"] if e["kind"] in ("motion", "block")]
    if want:
        entries = [e for e in entries if e["id"] in want]

    mpath = OUT / "_manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {}

    tally: dict[str, int] = {}
    skipped = []
    done: set[str] = set()
    # motion entries come first in the catalog; a few ids (counter/title/timeline/…)
    # also exist as block templates — the motion render is canonical, so a later
    # block entry with the same id shares that preview instead of overwriting it.
    for i, e in enumerate(entries, 1):
        if e["id"] in done:
            print(f"[{i:>2}/{len(entries)}] {e['id']:<26} shared (motion preview)", flush=True)
            continue
        fx = FIXTURES.get(e["id"])
        if fx is None:
            skipped.append(e["id"])
            print(f"[{i:>2}/{len(entries)}] {e['id']:<26} SKIP (no fixture)", flush=True)
            continue
        eid, status = render_entry(e, fx, force, manifest)
        if status in ("ok", "cached"):
            done.add(eid)
        tally[status.split(':')[0]] = tally.get(status.split(':')[0], 0) + 1
        print(f"[{i:>2}/{len(entries)}] {eid:<26} {status}", flush=True)
        mpath.write_text(json.dumps(manifest, indent=1))

    print(f"[previews] {json.dumps(tally)}  missing-fixture: {len(skipped)} {skipped}", flush=True)


if __name__ == "__main__":
    main()
