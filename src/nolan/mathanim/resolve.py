"""The finish-DAG step: `math` scenes -> rendered Manim clips + a video ground.

Runs after `word-sync` and before `recompose`, the same slot the dataset and
document sources occupy, and for the same reason: by then the scene's window and
the narration's word timings are final, and the composed HTML has not been built
yet.

  data.template + data.params + data.formulas
     -> ProjectSpec                        (adapter)
     -> the math-provenance gate           (gate)
     -> Manim clip in assets/math/         (render, in the Manim env)
     -> data.ground = {kind:"video", src}  (mounted by collect_video_grounds)

The gate runs over EVERY math scene before ANY of them renders. Rendering three
clips and then refusing on the fourth would spend minutes of Manim to arrive at a
failure that was knowable in milliseconds.

Clips are content-addressed on the built project — which embeds the authored
data, the theme's style tokens, the exact scene duration and the sliced word
timings — so re-running `hf-finish` reuses every unchanged clip. That cache is
load-bearing, not an optimisation: Manim renders are the expensive step in this
path, and an edit loop that re-renders them all is an edit loop nobody uses.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from nolan.mathanim import gate as _gate
from nolan.mathanim.adapter import MathAuthoringError, beat_id, project_from_scene
from nolan.mathanim.render import MathRenderError, clip_duration, render_project, stage_clip

MATH_ASSET_DIR = "assets/math"
# The compiler pads a Manim scene to exactly `beat.duration_seconds`, so anything beyond a frame or
# two of drift means the render did not do what it promised. Calibrated on the four-template
# acceptance comp at 30fps: observed |clip - window| was 0.02, 0.02, 0.02 and 0.09s (container
# rounding on the encode). 0.12 clears that with margin while still catching a truncated render;
# the residual shows as the final frame held for <3 frames, which for a derivation is the RIGHT
# behaviour — it is why math clips opt out of the boomerang freeze-heal.
DURATION_TOLERANCE_S = 0.12

_FORMAT = re.compile(r"^\s*(\d{3,5})\s*[xX*]\s*(\d{3,5})\s*$")


class MathResolveError(RuntimeError):
    """The math source could not be resolved. Fails the finish DAG, loudly."""


# --- reading the composition -----------------------------------------------------------------


def _spec_files(pdir: Path) -> List[Path]:
    return sorted((pdir / "compositions" / "frames").glob("*.spec.json"))


def _voice_words(pdir: Path) -> List[List[Dict[str, Any]]]:
    """Per-frame word lists, in spec order.

    Sorted by `frame` and indexed positionally — the same mapping
    `assemble_media._frame_durations` uses. Two ways to pair a spec file with its
    voice track would drift the moment one of them learned about a gap.
    """

    meta = pdir / "audio_meta.json"
    if not meta.is_file():
        return []
    try:
        voices = json.loads(meta.read_text(encoding="utf-8")).get("voices", [])
    except (json.JSONDecodeError, OSError):
        return []
    return [
        list(v.get("words") or [])
        for v in sorted(voices, key=lambda v: v.get("frame", 0))
    ]


def _canvas(pdir: Path, spec: Dict[str, Any]) -> Dict[str, int]:
    """Pixel canvas for a spec, resolved the way `ensure_storyboard` resolves it."""

    raw = spec.get("format") or (spec.get("frames") or [{}])[0].get("format") or ""
    match = _FORMAT.match(str(raw))
    width, height = (int(match.group(1)), int(match.group(2))) if match else (1920, 1080)
    return {"width": width, "height": height, "fps": 30}


def _comp_theme(pdir: Path) -> Optional[str]:
    try:
        return (json.loads((pdir / "hyperframes.json").read_text(encoding="utf-8")) or {}).get(
            "theme"
        )
    except (json.JSONDecodeError, OSError):
        return None


def iter_math_scenes(
    pdir: Path, only: Optional[Path] = None
) -> Iterator[Tuple[Path, Dict, Dict, Dict, int]]:
    """Every `math` scene in the comp: (spec_file, spec, frame, scene, frame_index).

    `only` restricts the walk to ONE spec file while keeping its position in the comp — the frame
    index is what pairs a spec with its voice track, so it has to come from the full ordering even
    when a single frame is being resolved (the edit loop's case).
    """

    for index, spec_file in enumerate(_spec_files(pdir)):
        if only is not None and spec_file.resolve() != Path(only).resolve():
            continue
        try:
            spec = json.loads(spec_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise MathResolveError(f"{spec_file.name}: unreadable spec — {exc}") from exc
        for frame in spec.get("frames", []) or []:
            for scene in frame.get("scenes", []) or []:
                if scene.get("type") == "math":
                    yield spec_file, spec, frame, scene, index


def _write_spec(spec_file: Path, spec: Dict[str, Any]) -> None:
    """Write a spec back preserving its line endings (CRLF files exist in this tree)."""

    crlf = b"\r\n" in spec_file.read_bytes()
    payload = (json.dumps(spec, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if crlf:
        payload = payload.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    spec_file.write_bytes(payload)


# --- the step --------------------------------------------------------------------------------


def build_all(
    pdir: Path, only: Optional[Path] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], List[str]]:
    """Build every math scene's project. Returns (built, blocking findings, notes).

    Building is where authoring errors surface, so it happens for ALL scenes
    before any render — and an unbuildable scene becomes a gate finding rather
    than an exception, so the author sees every problem in one pass instead of
    fixing them one render at a time.
    """

    theme_default = _comp_theme(pdir)
    words_by_frame = _voice_words(pdir)
    built: List[Dict[str, Any]] = []
    findings: List[Dict[str, str]] = []
    notes: List[str] = []

    for spec_file, spec, frame, scene, index in iter_math_scenes(pdir, only):
        frame_id = str(frame.get("id") or spec_file.stem)
        where = f"{frame_id}/{scene.get('id')}"
        data = scene.get("data") or {}

        scene_findings = _gate.scene_findings(data, where)
        if scene_findings:
            findings.extend(scene_findings)
            continue

        words = words_by_frame[index] if index < len(words_by_frame) else []
        try:
            project, build_notes = project_from_scene(
                scene,
                frame_id=frame_id,
                theme=frame.get("theme") or theme_default,
                canvas=_canvas(pdir, spec),
                words=words,
            )
        except MathAuthoringError as exc:
            findings.append(
                {"reason": _gate.UNAUTHORABLE, "where": where, "message": str(exc)}
            )
            continue

        findings.extend(_gate.project_findings(project, where))
        notes.extend(build_notes)
        notes.extend(_gate.advisories(project, where))
        built.append(
            {
                "spec_file": spec_file,
                "spec": spec,
                "scene": scene,
                "where": where,
                "frame_id": frame_id,
                "project": project,
            }
        )
    return built, findings, notes


def resolve_math_spec(comp, spec_file) -> int:
    """Resolve just ONE frame's math scenes — the edit loop's entry point.

    Same builder, same gate, same content-addressed cache as the full-comp path; only the walk is
    narrowed. A separate implementation here is how the edit loop and the finish DAG would start
    disagreeing about what a scene means.
    """

    return resolve_math(comp, only=Path(spec_file))


def resolve_math(comp, *, render: bool = True, only: Optional[Path] = None) -> int:
    """Resolve every math scene in `comp`. Returns how many scenes were resolved.

    Raises `MathResolveError` on a gate failure or a render failure — this step
    is not soft. A math essay whose mathematics does not check out, or whose
    clips did not render, must not reach the composed HTML.
    """

    from nolan.hyperframes.edit import _project_dir

    pdir = Path(_project_dir(comp))
    built, findings, notes = build_all(pdir, only)
    if not built and not findings:
        return 0

    for note in notes:
        print(f"  ◆ {note}")

    if findings and not _gate.escaped():
        raise MathResolveError(_gate.format_block(findings))
    if findings:
        print(
            f"  ⚠ {len(findings)} math-provenance finding(s) — shipping anyway "
            f"({_gate.ESCAPE_ENV}=1):"
        )
        for item in findings:
            print(f"      {item['where']}: {item['message']}")
        built = [b for b in built if b["where"] not in {f["where"] for f in findings}]

    if not render:
        print(f"  math gate: {len(built)} scene(s) authorable, no render requested")
        return 0

    resolved = 0
    touched: Dict[Path, Dict[str, Any]] = {}
    for item in built:
        src = _resolve_one(pdir, item)
        if src is None:
            continue
        touched[item["spec_file"]] = item["spec"]
        resolved += 1
    for spec_file, spec in touched.items():
        _write_spec(spec_file, spec)
    return resolved


def _resolve_one(pdir: Path, item: Dict[str, Any]) -> Optional[str]:
    """Render (or reuse) one scene's clip and stamp its ground. Mutates the spec."""

    from math_animation.bundle import sha256_json

    project = item["project"]
    scene = item["scene"]
    where = item["where"]
    digest = sha256_json(project)[:12]
    bid = beat_id(item["frame_id"], str(scene.get("id")))
    relative = f"{MATH_ASSET_DIR}/{bid}.{digest}.mp4"
    destination = pdir / relative

    if destination.is_file() and destination.stat().st_size > 2048:
        print(f"  ↺ {where}: cached ({relative})")
        _stamp(scene, relative, digest, project, cached=True)
        return relative

    try:
        result = render_project(
            project, runs_dir=pdir / "capture" / "_math" / bid, review=True
        )
    except MathRenderError as exc:
        raise MathResolveError(f"{where}: {exc}") from exc

    window = float(scene.get("dur") or 0)
    actual = clip_duration(result.clip)
    if actual is not None and abs(actual - window) > DURATION_TOLERANCE_S:
        # NOT healed. `heal_video_freezes` boomerangs a short clip — forward then
        # reversed — which would play a derivation backwards. The compiler
        # promises an exact duration, so a mismatch is a broken promise worth
        # surfacing, not papering over.
        raise MathResolveError(
            f"{where}: the rendered clip is {actual:.2f}s but its narration window "
            f"is {window:.2f}s. The math compiler pads to the exact window, so this "
            f"means the render was cut short — check {result.run_dir / 'logs'}."
        )

    stage_clip(result.clip, destination)
    _prune_stale(destination.parent, bid, digest)
    for note in result.notes:
        print(f"  ◆ {where}: {note}")
    print(
        f"  ✓ {where}: rendered {relative} ({result.duration_seconds:.2f}s, "
        f"math={result.math_status}, pedagogy={result.pedagogy_score:.2f})"
    )
    _stamp(scene, relative, digest, project, cached=False)
    return relative


def _stamp(
    scene: Dict[str, Any], relative: str, digest: str, project: Any, *, cached: bool
) -> None:
    """Write the ground the composer and assemble step read, plus provenance.

    `_math` is underscore-prefixed so `block_registry.visible_strings` skips it:
    provenance is not narration, and letting it into the phrase matcher would
    corrupt scene placement.
    """

    data = scene.setdefault("data", {})
    data["ground"] = {"kind": "video", "src": relative}
    data["_math"] = {
        "engine": "math-animation",
        "template": data.get("template"),
        "project_sha256": digest,
        "beat_id": project.beats[0].id,
        "formulas": [f.latex_parts[0] for f in project.math_ledger.formulas],
        "claims": {
            claim.id: claim.verification for claim in project.math_ledger.claims
        },
        "cached": cached,
    }


def _prune_stale(directory: Path, bid: str, keep: str) -> None:
    """Drop this beat's older content-addressed clips once a new one supersedes them."""

    for path in directory.glob(f"{bid}.*.mp4"):
        if f".{keep}.mp4" not in path.name:
            path.unlink(missing_ok=True)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="nolan.mathanim.resolve")
    parser.add_argument("comp")
    parser.add_argument(
        "--gate-only",
        action="store_true",
        help="build + gate every math scene without spending a render",
    )
    args = parser.parse_args()
    count = resolve_math(args.comp, render=not args.gate_only)
    print(f"resolved {count} math scene(s) → Manim clips mounted as video grounds")


if __name__ == "__main__":
    main()
