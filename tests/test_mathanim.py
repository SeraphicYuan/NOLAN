"""Honesty tests for the MATH source — one per claim the docs make about it.

Docs claim, tests enforce (docs/WIRING_CHECKLIST.md). Each test below exists because some
statement in `skills/organ/math-animation.md`, `catalog.json` or the module docstrings would
otherwise be free to rot:

  * the template vocabulary lives in ONE place and three consumers agree with it
  * a formula on screen traces to the ledger, in BOTH directions
  * the freeze-heal never boomerangs a derivation
  * narration owns duration, and reveals cannot be front-loaded
  * a theme cannot make `changing` and `fixed` indistinguishable
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
if str(BRIDGE) not in sys.path:
    sys.path.insert(0, str(BRIDGE))

from nolan.mathanim import gate, registry, style  # noqa: E402

CATALOG = json.loads((BRIDGE / "catalog.json").read_text(encoding="utf-8"))
SKILL = (REPO / "skills" / "organ" / "math-animation.md").read_text(encoding="utf-8")
PIPELINE_SKILL = (REPO / "skills" / "pipeline" / "hyperframes.md").read_text(encoding="utf-8")


def _scene(data, *, start=0.0, dur=9.0, sid="s1"):
    return {"id": sid, "type": "math", "start": start, "dur": dur, "data": data}


SEQUENCE = {
    "template": "equation_sequence",
    "objective": "Derive the vertex form",
    "formulas": [
        {"latex": "y=x^2-6x+5", "says": "standard form"},
        {"latex": "y=(x^2-6x+9)-9+5", "says": "add and subtract nine"},
        {"latex": "y=(x-3)^2-4", "says": "vertex form"},
    ],
    "params": {"steps": [0, 1, 2]},
}


# --- ONE vocabulary, three consumers ---------------------------------------------------------


def test_catalog_documents_every_registry_template():
    """The catalog carries a GENERATED copy of the registry. Drift means an agent is choosing
    from a hand-kept slice of the inventory — pitfall #5."""
    documented = set(CATALOG["scene_templates"]["math"]["templates"])
    assert documented == set(registry.TEMPLATE_IDS), (
        f"catalog/registry drift: only in registry {sorted(set(registry.TEMPLATE_IDS) - documented)}, "
        f"only in catalog {sorted(documented - set(registry.TEMPLATE_IDS))}. Regenerate the entry "
        f"from `registry.catalog_entry()`."
    )


def test_catalog_entry_matches_what_the_registry_generates():
    """Not just the NAMES — the whole generated payload, so a `when_to_use` cannot go stale."""
    generated = registry.catalog_entry()
    entry = CATALOG["scene_templates"]["math"]
    assert entry["templates"] == generated["templates"]
    assert entry["semantic_roles"] == generated["semantic_roles"]


def test_the_skill_teaches_every_template():
    for name in registry.TEMPLATE_IDS:
        assert f"`{name}`" in SKILL, (
            f"organ.math-animation does not mention {name!r} — an agent reading the skill would "
            f"never pick it, so it is capable-but-unauthored (pitfall #2)"
        )


def test_the_skill_names_every_semantic_role():
    for role in registry.SEMANTIC_ROLES:
        assert f"`{role}`" in SKILL, f"the skill omits the semantic role {role!r}"


def test_the_pipeline_skill_documents_the_step_and_its_gate():
    """`test_organ_skills.py` only scans `_run("label")` steps, and math resolution runs INLINE
    (like datasets/documents). Without this, the DAG could grow a hard gate nobody documented."""
    assert "*(math)*" in PIPELINE_SKILL, "the finish-DAG table does not list the math step"
    assert "math-provenance gate" in PIPELINE_SKILL, "the DAG table does not list the math gate"
    assert gate.ESCAPE_ENV in PIPELINE_SKILL, (
        f"the DAG table does not name the escape hatch {gate.ESCAPE_ENV}"
    )


def test_the_dag_actually_calls_the_step_it_documents():
    """The other direction: the skill's row must correspond to a real call in the driver."""
    finish = (REPO / "src" / "nolan" / "hyperframes" / "finish.py").read_text(encoding="utf-8")
    assert "resolve_math_scenes" in finish, "finish.py does not invoke the math step"
    bridge = (REPO / "src" / "nolan" / "hyperframes" / "math_source.py").read_text(encoding="utf-8")
    assert "resolve_math" in bridge


# --- the ledger, in both directions ----------------------------------------------------------


def test_a_clean_scene_passes_the_gate():
    assert gate.scene_findings(SEQUENCE, "f/s") == []


def test_a_bespoke_program_may_not_paint_an_off_ledger_formula():
    program = {
        "objects": [{"id": "o1", "type": "math_tex", "latex_parts": [r"x=\frac{-b}{2a}"]}],
        "cues": [{"id": "c1", "actions": [{"type": "create", "target": "o1"}]}],
    }
    data = {"template": "scene_program", "formulas": [{"latex": "y=x^2"}],
            "params": {"program": program}}
    findings = gate.scene_findings(data, "f/s")
    assert [f["reason"] for f in findings] == [gate.OFF_LEDGER]

    # ...and the SAME program passes once the formula is in the ledger. Without this half, a gate
    # that simply refused every scene_program would look identical.
    data["formulas"] = [{"latex": r"x = \frac{-b}{2a}", "says": "the quadratic formula"}]
    assert gate.scene_findings(data, "f/s") == [], "whitespace-only differences must still match"


def test_the_ledger_walk_finds_latex_wherever_it_lives():
    """`latex_parts` sits on objects AND on `transform_math` actions. A fixed key list that missed
    either would leave exactly the hole the gate exists to close."""
    program = {
        "objects": [{"id": "o1", "type": "math_tex", "latex_parts": ["a=1"]}],
        "cues": [{"id": "c1", "actions": [
            {"type": "transform_math", "target": "o1", "latex_parts": ["a=2"]}]}],
    }
    assert set(gate.program_latex(program)) == {"a=1", "a=2"}


def test_invalid_latex_fails_the_engine_check():
    from nolan.mathanim.adapter import project_from_scene

    data = dict(SEQUENCE, formulas=[{"latex": r"y=\frac{1}{2"}, {"latex": "a=1"}, {"latex": "b=2"}])
    project, _ = project_from_scene(
        _scene(data), frame_id="f", theme=None, canvas={"width": 960, "height": 540, "fps": 24}
    )
    findings = gate.project_findings(project, "f/s")
    assert [f["reason"] for f in findings] == [gate.INVALID_MATH]


def test_uncited_formulas_are_advisory_not_blocking():
    """A gate that demanded a citation for `y = x^2 - 6x + 5` would train authors to paste a fake
    one, and a gate people defeat is worse than none (pitfall #11)."""
    from nolan.mathanim.adapter import project_from_scene

    project, _ = project_from_scene(
        _scene(SEQUENCE), frame_id="f", theme=None, canvas={"width": 960, "height": 540, "fps": 24}
    )
    assert gate.project_findings(project, "f/s") == []
    assert gate.advisories(project, "f/s"), "an uncited formula must at least be REPORTED"

    cited = dict(SEQUENCE, formulas=[dict(f, verified="Euler 1748") for f in SEQUENCE["formulas"]])
    project, _ = project_from_scene(
        _scene(cited), frame_id="f", theme=None, canvas={"width": 960, "height": 540, "fps": 24}
    )
    assert gate.advisories(project, "f/s") == []


# --- the authoring gate ----------------------------------------------------------------------


def test_custom_python_is_refused_by_name():
    for data in (
        dict(SEQUENCE, custom_scene="class X(Scene): pass"),
        {"template": "equation_reveal", "formulas": [{"latex": "a=1"}],
         "params": {"formula": 0, "source": "import os"}},
    ):
        errors = registry.validate_scene_data(data, "f/s")
        assert any("custom Manim source is refused" in e for e in errors), errors


def test_an_unknown_template_is_refused():
    errors = registry.validate_scene_data({"template": "manim_go_wild"}, "f/s")
    assert errors and "not a math template" in errors[0]


def test_a_formula_index_outside_the_ledger_is_refused():
    data = {"template": "equation_transform",
            "formulas": [{"latex": "a=1"}, {"latex": "a=2"}],
            "params": {"from": 0, "to": 7}}
    errors = registry.validate_scene_data(data, "f/s")
    assert any("outside data.formulas" in e for e in errors), errors


def test_an_unconsumed_param_is_refused():
    """An authored field with no consumer is inert — the phantom-field class (pitfall #1)."""
    data = {"template": "equation_reveal", "formulas": [{"latex": "a=1"}],
            "params": {"formula": 0, "wobble": 3}}
    errors = registry.validate_scene_data(data, "f/s")
    assert any("not a parameter of" in e for e in errors), errors


def test_the_bridge_gate_delegates_to_the_registry():
    """`author.py` must not grow its own copy of the math vocabulary."""
    import author

    spec = {"frames": [{"id": "f1", "dur": 9.0, "scenes": [
        dict(_scene({"template": "nope"}), id="s1")]}]}
    errors = author.validate_spec(spec)
    assert any("not a math template" in e for e in errors), errors

    ok = {"frames": [{"id": "f1", "dur": 9.0, "scenes": [_scene(SEQUENCE)]}]}
    assert not [e for e in author.validate_spec(ok) if "math" in e]


# --- narration owns duration; reveals cannot be front-loaded ---------------------------------


def test_the_beat_is_exactly_the_scene_window():
    from nolan.mathanim.adapter import project_from_scene

    project, _ = project_from_scene(
        _scene(SEQUENCE, start=12.4, dur=9.0), frame_id="f", theme=None,
        canvas={"width": 960, "height": 540, "fps": 24},
    )
    assert project.beats[0].duration_seconds == 9.0


def test_an_at_phrase_resolves_to_clip_local_time():
    """The scene starts at 12.4s of its section; a phrase spoken at 15.55s must land at 3.15s in
    the clip, not at 15.55s. Getting this wrong shifts every anchored step by the scene offset."""
    from nolan.mathanim.adapter import phrase_seconds

    words = [{"word": w, "start": 12.4 + i * 0.45, "end": 12.4 + i * 0.45 + 0.4}
             for i, w in enumerate("we start in standard form then we complete the square".split())]
    at = phrase_seconds("complete the square", words, 12.4, 9.0)
    assert at is not None
    assert abs(at - (words[7]["start"] - 12.4)) < 1e-6


def test_an_unspoken_at_phrase_is_reported_not_swallowed():
    from nolan.mathanim.adapter import project_from_scene

    words = [{"word": w, "start": i * 0.4, "end": i * 0.4 + 0.35}
             for i, w in enumerate("nothing here matches the authored phrase at all".split())]
    data = dict(SEQUENCE, params={"steps": [0, 1, 2], "at": ["never spoken", "also absent"]})
    _, notes = project_from_scene(
        _scene(data), frame_id="f", theme=None,
        canvas={"width": 960, "height": 540, "fps": 24}, words=words,
    )
    assert sum("not spoken inside this scene" in n for n in notes) == 2


def test_reveals_spread_across_the_beat_instead_of_front_loading():
    """A derivation that writes three steps in 2.4s then holds a frozen frame for 6.6s reads as a
    static slide — the pitfall #9 shape, one layer down."""
    from nolan.mathanim.adapter import project_from_scene

    project, _ = project_from_scene(
        _scene(SEQUENCE, dur=12.0), frame_id="f", theme=None,
        canvas={"width": 960, "height": 540, "fps": 24},
    )
    starts = [c.start_at.seconds for c in project.beats[0].scene_program.cues]
    assert starts == sorted(starts)
    assert starts[-1] > 12.0 * 0.5, (
        f"the last reveal lands at {starts[-1]}s of a 12s beat — the reveals are front-loaded"
    )


def test_an_animation_longer_than_its_window_is_refused_not_squeezed():
    from nolan.mathanim.adapter import MathAuthoringError, project_from_scene

    data = dict(SEQUENCE, formulas=[{"latex": f"a={i}"} for i in range(6)],
                params={"steps": [0, 1, 2, 3, 4, 5]})
    with pytest.raises(MathAuthoringError, match="Narration owns duration"):
        project_from_scene(_scene(data, dur=1.2), frame_id="f", theme=None,
                           canvas={"width": 960, "height": 540, "fps": 24})


def test_the_compiler_pads_the_scene_to_its_exact_window():
    """The promise the freeze-heal opt-out depends on: verified against the engine, not assumed."""
    from math_animation.compiler import ManimCompiler
    from math_animation.style import normalize_style
    from nolan.mathanim.adapter import project_from_scene

    project, _ = project_from_scene(
        _scene(SEQUENCE, dur=9.0), frame_id="f", theme=None,
        canvas={"width": 960, "height": 540, "fps": 24},
    )
    import tempfile

    result = ManimCompiler().compile(
        project, normalize_style(project.style), Path(tempfile.mkdtemp())
    )
    assert result.timeline.clips[0].duration_seconds == 9.0


# --- classification: a math clip counts as media, and is never healed -------------------------


def test_a_grounded_math_scene_counts_as_video():
    """Scoring a full-frame animation `none` is exactly the contradiction `block_registry` exists
    to end — the metric would demand grounding for a scene that is already all media."""
    from nolan.style_contract.metrics import scene_asset_srcs, scene_media

    grounded = {"template": "equation_sequence",
                "ground": {"kind": "video", "src": "assets/math/f1.s1.abc.mp4"}}
    assert scene_media("math", grounded) == "video"
    assert scene_asset_srcs("math", grounded) == ["assets/math/f1.s1.abc.mp4"]
    assert scene_media("math", {"template": "equation_sequence"}) == "none"


def test_auto_ground_may_not_place_a_photo_behind_a_derivation():
    from nolan.block_registry import consumes_ground

    assert not consumes_ground("math"), (
        "listing `math` as a ground block would let auto-ground overwrite the ground the resolver "
        "stamped, throwing away a Manim render"
    )


def test_the_freeze_heal_skips_math_clips():
    """Its heal is a boomerang — forward then REVERSED. On a derivation that plays the argument
    backwards, which is worse than the freeze it fixes."""
    import assemble_media

    assert not assemble_media._healable("assets/math/f1.s1.abc.mp4")
    assert not assemble_media._healable("assets\\math\\f1.s1.abc.mp4")
    assert assemble_media._healable("assets/a5_02_fit8s.mp4"), (
        "the skip must be scoped to math clips — b-roll still needs healing"
    )


# --- the composer ----------------------------------------------------------------------------


def test_the_composer_paints_no_scrim_over_a_math_clip():
    """`media_ground` darkens footage so overlaid text stays legible. A math clip has no text to
    protect, and a scrim would grey out the equations."""
    import compose

    frag, _ = compose.BLOCKS["math"]("s1", _scene(dict(SEQUENCE, kicker="STEP TWO")))
    assert not any("scrim" in f for f in frag)
    assert not any("gnd" in f for f in frag)


def test_the_composer_pins_its_caption_to_the_spoken_word():
    import compose

    data = dict(SEQUENCE, caption="the vertex sits at x equals three")
    _, tl_plain = compose.BLOCKS["math"]("s1", _scene(data, start=4.0, dur=11.0))
    cued = dict(data, _field_cues={"caption": 9.4})
    _, tl_cued = compose.BLOCKS["math"]("s1", _scene(cued, start=4.0, dur=11.0))
    assert tl_plain != tl_cued, "the caption ignores the cue sync writes for it"
    assert any("9.40" in line for line in tl_cued)
    assert any("4.60" in line for line in tl_plain), "un-cued, it falls back to start + lead"


def test_a_math_scene_with_no_chrome_still_mounts_a_clip_element():
    import compose

    frag, _ = compose.BLOCKS["math"]("s1", _scene(SEQUENCE))
    assert frag and 'class="clip"' in frag[0]


# --- style: a theme may not collapse the semantic roles ---------------------------------------


@pytest.mark.parametrize(
    "theme",
    sorted(p.parent.name for p in (REPO / "themes").glob("*/theme.json")),
)
def test_every_shipped_theme_yields_distinguishable_roles(theme):
    problems = style.check_roles(style.style_payload(theme))
    assert not problems, f"{theme}: " + "; ".join(problems)


def test_a_collapsed_palette_is_still_refused():
    """The other direction. A check that passes everything measures nothing (pitfall #11)."""
    collapsed = {
        "colors": {"background": "#101010", "foreground": "#eeeeee"},
        "semantic_colors": {"changing": "#4d7a4d", "fixed": "#477957", "primary": "#4d7a4d",
                            "positive": "#70a37f", "negative": "#c96a6a", "secondary": "#8899aa"},
    }
    problems = style.check_roles(collapsed)
    assert any("changing" in p and "fixed" in p for p in problems)


def test_roles_an_author_uses_together_are_checked_even_if_not_intrinsic():
    """`positive` vs `changing` is not an intrinsic pair, but an author who colours two parts of one
    equation with them has made it one."""
    payload = style.style_payload("blueprint")
    payload["semantic_colors"]["muted"] = payload["semantic_colors"]["fixed"]
    assert style.check_roles(payload) == []
    assert style.check_roles(payload, used_roles=["fixed", "muted"])


def test_the_theme_drives_the_manim_background():
    """A math clip in the engine's stock dark palette inside a cream editorial essay reads as a
    different film spliced in."""
    from nolan.mathanim.adapter import project_from_scene

    project, _ = project_from_scene(
        _scene(SEQUENCE), frame_id="f", theme="highlighter-editorial",
        canvas={"width": 1920, "height": 1080, "fps": 30},
    )
    palette = style.theme_palette("highlighter-editorial")
    assert project.style.raw["colors"]["background"] == palette["shell"]
    assert project.style.provider == "nolan"


def test_axes_are_painted_in_the_theme_not_manim_white():
    """Manim's `Axes` defaults to WHITE. On the engine's own dark background that reads; mounted in
    a light NOLAN theme the axes vanished entirely — visible in the first real render, invisible to
    every check, because axes are not a semantic role. Caught by looking at the frames."""
    from math_animation.blocks import compile_block
    from math_animation.contracts import FunctionPlotBlock, NumberLineBlock, StyleTemplateRef
    from math_animation.style import normalize_style

    tokens = normalize_style(StyleTemplateRef(raw=style.style_payload("highlighter-editorial")))
    assert tokens.muted != "#ffffff"

    plot = compile_block(FunctionPlotBlock(id="p", expression="x**2"), tokens)
    assert any(f"'color': {tokens.muted!r}" in line for line in plot.lines), (
        "function_plot axes carry no theme colour — they render Manim-white"
    )
    line = compile_block(NumberLineBlock(id="n", values=[1.0]), tokens)
    assert any(tokens.muted in ln for ln in line.lines), "number_line carries no theme colour"


def test_a_theme_face_manim_cannot_see_is_substituted_by_personality():
    """Manim asks Pango for SYSTEM fonts and cannot use the essay's webfonts. Left alone, Pango
    picks generic Sans with mangled kerning and says so only in a stderr log a successful render
    never surfaces — so the substitution is made deliberately, and reported."""
    installed = ["Century Gothic", "Georgia", "Consolas", "Arial", "Segoe UI"]
    font, note = style.resolve_font("highlighter-editorial", installed)   # wants Libre Franklin
    assert font == "Century Gothic", "a geometric-sans theme should not land on a serif"
    assert note and "Libre Franklin" in note

    serif, _ = style.resolve_font("vintage-editorial", installed)
    assert serif == "Georgia", "an editorial-serif theme should not land on a geometric sans"
    mono, _ = style.resolve_font("blueprint", installed)
    assert mono == "Consolas", "a mono-technical theme should stay monospaced"


def test_an_installed_theme_face_is_used_as_authored():
    font, note = style.resolve_font("highlighter-editorial", ["Libre Franklin", "Arial"])
    assert font == "Libre Franklin" and note is None


def test_an_unknown_font_list_is_not_evidence_of_a_missing_font():
    """[] means 'could not ask', not 'nothing installed'. Substituting on no information would
    silently retype every clip on a machine without Manim."""
    font, note = style.resolve_font("highlighter-editorial", [])
    assert font == "Libre Franklin" and note is None


def test_the_font_note_reaches_the_caller():
    """The note lives at the payload's top level; the adapter reads it from there. An earlier
    version wrote it there and read it from `typography` — an authored field with no consumer,
    the exact class this repo's checklist is built around."""
    payload = style.style_payload("highlighter-editorial", available_fonts=["Arial"])
    assert payload.get("_font_note")

    from nolan.mathanim.adapter import project_from_scene

    project, notes = project_from_scene(
        _scene(SEQUENCE), frame_id="f", theme="highlighter-editorial",
        canvas={"width": 960, "height": 540, "fps": 24},
    )
    if project.style.raw.get("_font_note"):
        assert any("not installed for Manim" in n for n in notes), (
            "the substitution was made but never reported to the author"
        )


def test_pango_font_misses_are_read_back_from_the_render_log(tmp_path):
    """The backstop. Pango reports a miss on stderr and the render still exits 0, so nothing
    downstream would ever know without reading the log."""
    from nolan.mathanim.render import font_misses

    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "beat.stderr.log").write_text(
        'couldn\'t load font "Libre Franklin Not-Rotated 6.667", falling back to '
        '"Sans Not-Rotated 6.667", expect ugly output.',
        encoding="utf-8",
    )
    assert font_misses(tmp_path) == ["Libre Franklin"]
    assert font_misses(tmp_path / "nonexistent") == []


def test_type_sizes_scale_with_the_canvas():
    """Manim sizes glyphs against a fixed 8.0-unit frame, so a size that reads at 1080p is
    unreadable in a 540p proxy."""
    big = style.style_payload("blueprint", canvas_height=1080)["typography"]["math_size"]
    small = style.style_payload("blueprint", canvas_height=540)["typography"]["math_size"]
    assert small < big


# --- the render boundary ---------------------------------------------------------------------


def test_the_render_boundary_reports_a_missing_toolchain_usefully():
    """LaTeX missing is the usual first failure, and it otherwise dies deep inside a subprocess."""
    from nolan.mathanim import render

    report = render.toolchain_report()
    assert set(report) >= {"python"}
    if report.get("python") != "missing":
        assert set(report) == {"python", "manim", "ffmpeg", "latex", "dvisvgm"}


def test_the_engine_takes_an_explicit_render_interpreter():
    """The whole two-env split rests on this parameter existing."""
    from math_animation.pipeline import AuthoringPipeline

    pipeline = AuthoringPipeline(runs_dir="runs", python_executable=r"X:\somewhere\python.exe")
    assert pipeline.renderer.python_executable == r"X:\somewhere\python.exe"


def test_the_vendored_engine_imports_without_its_optional_extras():
    """NOLAN's pipeline env carries pydantic and nothing else from this stack, so the engine's
    package __init__ must not drag LangGraph or OpenAI in on a plain `import`."""
    import subprocess

    probe = (
        "import sys, types;"
        "sys.modules['langgraph'] = None; sys.modules['openai'] = None;"
        "import math_animation;"
        "from math_animation.contracts import ProjectSpec;"
        "from math_animation.compiler import ManimCompiler;"
        "from math_animation.pedagogy import evaluate_pedagogy;"
        "from math_animation.pipeline import AuthoringPipeline;"
        "print('ok')"
    )
    done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert done.returncode == 0, (
        f"the engine needs an optional extra to import:\n{done.stderr[-1500:]}"
    )


def test_clip_names_are_content_addressed():
    """Re-running the DAG must reuse an unchanged clip; changing the authored data must not."""
    from math_animation.bundle import sha256_json
    from nolan.mathanim.adapter import project_from_scene

    kwargs = dict(frame_id="f", theme="blueprint",
                  canvas={"width": 1920, "height": 1080, "fps": 30})
    first, _ = project_from_scene(_scene(SEQUENCE), **kwargs)
    same, _ = project_from_scene(_scene(SEQUENCE), **kwargs)
    assert sha256_json(first) == sha256_json(same), "identical input must reuse the clip"

    themed, _ = project_from_scene(_scene(SEQUENCE), **{**kwargs, "theme": "vellum"})
    assert sha256_json(first) != sha256_json(themed), "a theme change must invalidate the clip"
    longer, _ = project_from_scene(_scene(SEQUENCE, dur=10.0), **kwargs)
    assert sha256_json(first) != sha256_json(longer), "a duration change must invalidate the clip"
    restepped, _ = project_from_scene(
        _scene(dict(SEQUENCE, params={"steps": [0, 2, 1]})), **kwargs)
    assert sha256_json(first) != sha256_json(restepped), "reordered steps must invalidate the clip"

    # ...and the other direction: HTML chrome is painted by the composer, not by Manim, so editing
    # it must NOT cost a re-render. A cache that invalidated on a caption typo would make the edit
    # loop as expensive as a cold build.
    chrome, _ = project_from_scene(
        _scene(dict(SEQUENCE, caption="a reworded caption", kicker="STEP THREE")), **kwargs)
    assert sha256_json(first) == sha256_json(chrome), (
        "a chrome-only edit invalidated the Manim clip — chrome is HTML, it costs nothing"
    )
