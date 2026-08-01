"""Author the `_det-stretch` comp: HTML blocks + Manim math, including two BESPOKE ScenePrograms.

Scene windows are placeholders — `hf-finish`'s sync-durations + word-sync overwrite every
start/dur from the real VO. What matters here is the ORDER and the `anchor` phrases.
"""
import json
from pathlib import Path

COMP = Path(r"D:/ClaudeProjects/NOLAN/render-service/_lab_hyperframes/videos/_det-stretch")
FRAMES = COMP / "compositions" / "frames"
FRAMES.mkdir(parents=True, exist_ok=True)
THEME = "highlighter-editorial"

MATRIX = [[2.0, 1.0], [1.0, 2.0]]        # det = 4 - 1 = 3, the number the script says
SQUARE = [[-1.0, -1.0, 0.0], [1.0, -1.0, 0.0], [1.0, 1.0, 0.0], [-1.0, 1.0, 0.0]]


def square_program(matrix, det, *, collapse=False):
    """A unit square deformed by a matrix — the bespoke tier, typed end to end.

    `apply_matrix` carries `expected_determinant`, so the engine REFUSES to compile if the
    matrix it is told to draw does not have the determinant the script claims. The narration
    and the animation cannot drift apart silently.
    """
    label = "det = 0" if collapse else "det = 3"
    return {
        "scene_kind": "2d",
        "objects": [
            {"id": "sq", "type": "polygon", "vertices": SQUARE, "role": "primary",
             "fill_role": "primary", "fill_opacity": 0.16, "stroke_width": 5.0},
            # y=-2.2, not -3.1. The composition grid's caption keep-out starts at 83% of frame
            # height, which is y=-2.64 in Manim's 8.0-unit frame — and the layout linter CANNOT
            # see inside a video, so a label parked there collides with the caption pill and no
            # gate says a word. Inside a math clip, keep-out is the author's job.
            {"id": "cap", "type": "text", "text": label, "position": [0.0, -2.2, 0.0],
             "font_size": 34, "role": "muted"},
        ],
        "cues": [
            {"id": "draw", "mode": "parallel", "actions": [
                {"type": "create", "target": "sq", "run_time": 0.9},
                {"type": "create", "target": "cap", "run_time": 0.9},
            ]},
            {"id": "deform", "actions": [
                {"type": "apply_matrix", "target": "sq", "matrix": matrix,
                 "expected_determinant": det, "run_time": 1.6},
            ]},
            {"id": "settle", "actions": [
                {"type": "set_style", "target": "sq",
                 "role": "negative" if collapse else "changing", "run_time": 0.8},
            ]},
        ],
    }


frames = [
    # ── 01 · the machine ────────────────────────────────────────────────────────────────────
    ("01-machine", [
        {"id": "s1", "type": "math", "anchor": "two by two matrix", "data": {
            "template": "equation_reveal",
            "objective": "Introduce the matrix as an object, before any interpretation",
            "kicker": "FOUR LITTLE NUMBERS",
            "formulas": [{"latex": r"A=\begin{bmatrix} 2 & 1 \\ 1 & 2 \end{bmatrix}",
                          "says": "a two by two matrix"}],
            "params": {"formula": 0, "part_roles": ["primary"]},
        }},
        {"id": "s2", "type": "statement", "anchor": "not a table", "data": {
            "register": "paper",
            "kicker": "THE REFRAME",
            "lines": ["A matrix is not a table.", "It is a machine that grabs space",
                      "and stretches it."],
            "operative": "stretches it",
        }},
    ]),
    # ── 02 · the square (BESPOKE + annotations over live animation) ─────────────────────────
    ("02-square", [
        {"id": "s1", "type": "math", "anchor": "unit square", "data": {
            "template": "scene_program",
            "objective": "Show the determinant as the factor the area is multiplied by",
            "kicker": "WATCH THE AREA",
            "caption": "the new area is three",
            "annotations": [
                {"text": "area 1", "at": "area one", "x": 0.40, "y": 0.30, "tone": "ink"},
                {"text": "now 3x bigger", "at": "area is three", "x": 0.66, "y": 0.22, "tone": "accent"},
            ],
            "formulas": [],
            "params": {"program": square_program(MATRIX, 3.0)},
        }},
        {"id": "s2", "type": "stat", "anchor": "that three is", "data": {
            "kicker": "THE DETERMINANT",
            "items": [{"value": 3, "label": "times bigger", "at": "that three is"}],
        }},
    ]),
    # ── 03 · the formula ───────────────────────────────────────────────────────────────────
    ("03-formula", [
        {"id": "s1", "type": "math", "anchor": "a d minus b c", "data": {
            "template": "equation_sequence",
            "objective": "Connect the memorised formula to the measured stretch",
            "kicker": "THE FORMULA, DEMYSTIFIED",
            "formulas": [
                {"latex": r"\det A = ad - bc", "says": "a d minus b c"},
                {"latex": r"\det A = (2)(2) - (1)(1)", "says": "two times two minus one times one"},
                {"latex": r"\det A = 3", "says": "leaves three"},
            ],
            "params": {"steps": [0, 1, 2],
                       "at": ["two times two", "leaves three"]},
        }},
        {"id": "s2", "type": "pull_quote", "anchor": "it is just", "data": {
            "quote": "It is just the stretch factor.",
            "cite": "the whole idea",
        }},
    ]),
    # ── 04 · the collapse (BESPOKE, singular) ──────────────────────────────────────────────
    ("04-collapse", [
        {"id": "s1", "type": "math", "anchor": "determinant hits zero", "data": {
            "template": "scene_program",
            "objective": "Show what a zero determinant destroys",
            "kicker": "DETERMINANT ZERO",
            "annotations": [
                {"text": "area gone", "at": "crushed onto a line", "x": 0.5, "y": 0.32,
                 "tone": "accent"},
            ],
            "formulas": [],
            # [[1,2],[0.5,1]] -> det = 1 - 1 = 0: every point lands on one line
            "params": {"program": square_program([[1.0, 2.0], [0.5, 1.0]], 0.0, collapse=True)},
        }},
        {"id": "s2", "type": "statement", "anchor": "nothing you do", "data": {
            "register": "paper",
            "lines": ["Nothing you do", "will ever get it back."],
            "operative": "ever",
        }},
    ]),
]

# Windows come FROM the narration, not from a guess. The frame's duration IS its VO wav, and every
# scene after the first opens where its anchor phrase is actually spoken. Authoring placeholders and
# hoping word-sync fixes them is what put a 6.9s derivation into a 6.0s hole: `place_scenes` scales
# within the frame duration the SPEC declares, so a placeholder frame dur silently caps every scene.
audio = json.loads((COMP / "audio_meta.json").read_text(encoding="utf-8"))
by_frame = {v["frame"]: v for v in audio["voices"]}


def spoken_at(words, phrase):
    """When `phrase` is first spoken, using the repo's own matcher (not a private one)."""
    from nolan.aligner import WordTimestamp
    from nolan.hyperframes.sync import _phrase_time
    stream = [WordTimestamp(word=w["word"], start=w["start"], end=w["end"]) for w in words]
    return _phrase_time(phrase, stream)


for index, (fid, scenes) in enumerate(frames, start=1):
    voice = by_frame[index]
    frame_dur = float(voice["duration_s"])
    words = voice["words"]
    starts = [0.0]
    for sc in scenes[1:]:
        at = spoken_at(words, sc["anchor"])
        if at is None:
            raise SystemExit(f"{fid}/{sc['id']}: anchor {sc['anchor']!r} is never spoken in this frame")
        starts.append(round(float(at), 2))
    for i, sc in enumerate(scenes):
        sc["start"] = starts[i]
        sc["dur"] = round((starts[i + 1] if i + 1 < len(starts) else frame_dur) - starts[i], 2)
    spec = {"format": "1920x1080",
            "frames": [{"id": fid, "dur": round(frame_dur, 2), "theme": THEME, "scenes": scenes}]}
    (FRAMES / f"{fid}.spec.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    kinds = ", ".join(f"{s['id']}:{s['type']}@{s['start']:.1f}+{s['dur']:.1f}" for s in scenes)
    print(f"  {fid:12} {frame_dur:5.2f}s  {kinds}")

(COMP / "hyperframes.json").write_text(json.dumps({
    "theme": THEME,
    "paths": {"blocks": "compositions"},
    # A 48s math explainer is DELIBERATELY narrow: four beats, mostly one animated source. The
    # defaults are tuned for a 7-minute essay with a dozen block types, so scoring this against
    # them would fail a piece that is exactly what it should be.
    "style_dials": {"asset_density": "balanced", "video_share": "heavy", "block_variety": "minimal"},
}, indent=2) + "\n", encoding="utf-8")
print(f"\ntheme {THEME}; {sum(len(s) for _, s in frames)} scenes over {len(frames)} frames")
