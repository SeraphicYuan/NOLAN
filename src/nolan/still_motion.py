"""Render a single still into a moving shot via the `StillMotion` Remotion effect.

Turns a photo into video-essay b-roll with a MOTIVATED motion:
  ken-burns-in / -out / -pan  — camera zooms/pans with its origin on the salient subject
  parallax                    — sharp subject cutout (rembg) over a blurred, slower background

The salient target (and the parallax foreground) are derived from a rembg cutout, so a
push-in actually pushes *into the subject*. Pairs with `motion_select` (which picks the id)
and the pairing engine (which picks the asset).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

_TREATMENTS = {"ken-burns-in", "ken-burns-out", "ken-burns-pan", "parallax",
               "rack-focus", "blur-in", "atmospheric", "hold"}
_NEED_CUTOUT = {"parallax", "rack-focus"}


def camera_tour_props(scene: dict, ordinal: int = 0,
                      center: Optional[tuple] = None) -> dict:
    """THE energy→camera vocabulary for a still (single home — plumbing
    consolidation; premium's ArtworkStage steps and any future consumer read
    it from here so the dialects can't drift; `motion_for_tempo` in
    nolan.tempo_plan maps the same levers to standalone treatment ids).

    ArtworkStage keyframes its camera ONLY from focus regions — this is where
    the treatment vocabulary lands: energy sets zoom tightness, motion_speed
    sets glide/hold pacing. Placement precedence: an explicit ``center``
    (a human's nine-dot tray placement — the camera pushes exactly there) →
    a stamped still-motion direction → center/left/right lane alternation by
    ordinal so consecutive stills don't all push the same way.
    """
    energy = 0.5
    try:
        energy = float(scene.get("energy") or 0.5)
    except (TypeError, ValueError):
        pass
    speed = str(scene.get("motion_speed") or "medium").lower()

    side = max(0.45, min(0.8, 0.78 - 0.35 * energy))
    ms = scene.get("motion_spec") or {}
    direction = ((ms.get("content") or {}).get("direction")
                 or ms.get("direction") or "")
    if center is not None:
        x = max(0.0, min(1.0 - side, float(center[0]) - side / 2))
        y = max(0.0, min(1.0 - side, float(center[1]) - side / 2))
    elif direction == "left":
        x, y = 0.06, (1 - side) / 2
    elif direction == "right":
        x, y = 1 - side - 0.06, (1 - side) / 2
    else:
        lane = ordinal % 3
        x = {0: (1 - side) / 2, 1: 0.08, 2: 1 - side - 0.08}[lane]
        y = (1 - side) / 2

    glide = {"slow": 34, "medium": 26, "fast": 18}.get(speed, 26)
    intro = {"slow": 48, "medium": 40, "fast": 26}.get(speed, 40)
    # Synthesized (wordless) focuses render as ONE continuous eased move
    # across the whole step (mode from assign_still_treatments, default a
    # plain push) — the hold-then-lunge two-phase pattern is banned. Word-
    # anchored tours don't come through this function.
    mode = scene.get("_still_treatment") or "kenburns-in"
    return {"focuses": [{"word": "", "x": round(x, 3), "y": round(y, 3),
                         "w": side, "h": side}],
            "glide": glide, "introHold": intro, "mode": mode}


_PAN_CUES = (" from ", " through ", " across ", " rose ", "journey",
             " born ", "procession", "march", "flight", "fleeing", "voyage",
             "travel", "sequence")
_OUT_CUES = (" but ", "turns out", "the strange", "entire", " whole ", " all of ",
             "everything", " empire", " world", "reveal", "it ends", "stands over",
             "surrender", "larger than")
_IN_CUES = (" this ", " these ", " his ", " her ", "the man", "the poem",
            "manuscript", "face", "hands", " lines ", "detail", "one last",
            "named", "nicknamed")


def select_still_treatment(scene: dict, prev: Optional[str] = None) -> str:
    """Narrative-semantic camera direction for a still (aeneid feedback:
    every image got the same push). Deterministic cues:

    - PAN: the narration MOVES (journeys, sequences, from→to)
    - OUT: the narration WIDENS (reveals, context, 'the whole/everything')
    - IN:  the narration NAMES/examines (this, the man, a detail)

    plus a hard no-repeat against ``prev`` (the previous still's treatment) —
    two identical consecutive moves read as a template, not a camera.
    """
    text = " " + ((scene.get("narration_excerpt") or "") + " "
                  + (scene.get("visual_description") or "")).lower() + " "
    pick = None
    if any(c in text for c in _PAN_CUES):
        pick = "kenburns-pan"
    elif any(c in text for c in _OUT_CUES):
        pick = "kenburns-out"
    elif any(c in text for c in _IN_CUES):
        pick = "kenburns-in"
    if pick is None:
        pick = "kenburns-in"
    if pick == prev:
        cycle = ("kenburns-in", "kenburns-pan", "kenburns-out")
        pick = next(c for c in cycle if c != prev)
    return pick


# The premium still-camera vocabulary (ArtworkStage `mode`). Also the value
# set for the AUTHORED `still_treatment` field — a human lock from the
# timeline/Inspector that the pre-pass below honors verbatim.
STILL_TREATMENTS = ("kenburns-in", "kenburns-out", "kenburns-pan",
                    "drift", "tour")

# The ONE bridge from the authored camera lock into the still-motion effect's
# treatment enum (motion registry `still-motion`), so the ORCHESTRATOR render
# lane honors the same lock the premium lane does. Kept here — the camera
# vocabulary has exactly one owner (pitfall #4); tests assert every value
# lands inside the registry enum.
_TO_STILL_MOTION = {
    "kenburns-in": "ken-burns-in",
    "kenburns-out": "ken-burns-out",
    "kenburns-pan": "ken-burns-pan",
    "drift": "atmospheric",          # drift = ambient tone hold
    "tour": "ken-burns-pan",         # nearest single-move analog
}


def to_still_motion_treatment(treatment: str) -> Optional[str]:
    """Map an authored ``still_treatment`` lock to the still-motion effect's
    treatment value, or None if the lock isn't in the vocabulary."""
    return _TO_STILL_MOTION.get(treatment)


def assign_still_treatments(plan: dict) -> int:
    """IN-MEMORY pre-pass (premium calls it at plan load, motif-style):
    stamp ``scene['_still_treatment']`` on every still-rendered scene —
    narrative semantics via :func:`select_still_treatment`, no-two-
    consecutive enforced across the whole piece, and the LAST low-energy
    scene of a section gets ``drift`` (the protected quiet close). The plan
    on disk never carries the underscore key.

    A scene carrying an AUTHORED ``still_treatment`` (human lock, validated
    against :data:`STILL_TREATMENTS`) gets exactly that — it wins over the
    cues, the drift close and the no-repeat rule, and counts as ``prev`` so
    neighbors still diversify around it."""
    prev = None
    n = 0
    for scenes in (plan.get("sections") or {}).values():
        if not isinstance(scenes, list):
            continue
        for i, s in enumerate(scenes):
            if not isinstance(s, dict):
                continue
            if not (s.get("matched_asset") or s.get("generated_asset")):
                continue
            if s.get("motion_spec") or s.get("layout_spec") or s.get("pinned_asset"):
                continue                      # other treatments own these
            locked = s.get("still_treatment")
            if locked in STILL_TREATMENTS:
                pick = locked
            else:
                pick = select_still_treatment(s, prev)
                if (i == len(scenes) - 1
                        and float(s.get("energy") or 0.5) < 0.3):
                    pick = "drift"
            s["_still_treatment"] = pick
            prev = pick
            n += 1
    return n


def subject_center(image_path, cache: bool = True) -> Optional[tuple]:
    """Salient subject center (x, y in 0..1) for camera targeting, or None.

    Same rembg signal ``render_still`` pushes into — so premium's synthesized
    camera moves aim at the SUBJECT instead of rotating through lanes. The
    result is cached in a ``<image>.subject.json`` sidecar (re-renders never
    re-run the model). Fail-soft: any failure returns None and the caller
    falls back to lane alternation — the camera never breaks over saliency.
    """
    import json as _json
    p = Path(image_path)
    side = p.parent / (p.name + ".subject.json")
    if cache and side.exists():
        try:
            d = _json.loads(side.read_text(encoding="utf-8"))
            return (d["x"], d["y"]) if d.get("ok") else None
        except Exception:
            pass
    try:
        target, _ = _salient(p, want_cutout=False, out_dir=p.parent)
        d = {"ok": True, "x": target["x"], "y": target["y"]}
    except Exception:
        d = {"ok": False}
    if cache:
        try:
            side.write_text(_json.dumps(d), encoding="utf-8")
        except Exception:
            pass
    return (d["x"], d["y"]) if d.get("ok") else None


def _salient(image_path, want_cutout: bool, out_dir: Path):
    """Return ({x,y} salient target in 0..1, cutout_png_path|None) from a rembg mask."""
    import numpy as np
    from nolan.cutout import remove_background
    rgba = remove_background(image_path)                 # PIL RGBA (subject kept, bg transparent)
    alpha = np.asarray(rgba.split()[-1])
    ys, xs = np.where(alpha > 40)
    target = {"x": 0.5, "y": 0.5}
    if xs.size >= 50:
        cx, cy = float(xs.mean()) / rgba.width, float(ys.mean()) / rgba.height
        target = {"x": min(max(cx, 0.15), 0.85), "y": min(max(cy, 0.15), 0.85)}
    fg = None
    if want_cutout and xs.size >= 50:
        fg = out_dir / (Path(image_path).stem + ".fg.png")
        rgba.save(fg)
    return target, fg


def render_still(image_path, motion_id: str = "ken-burns-in", out_path=None,
                 duration: float = 4.0, direction: str = "right") -> Path:
    """Render `image_path` to an mp4 with the chosen motion. Returns the mp4 path."""
    from nolan import remotion_source
    image_path = Path(image_path)
    out_path = Path(out_path) if out_path else image_path.with_suffix(".motion.mp4")
    treatment = motion_id if motion_id in _TREATMENTS else "ken-burns-in"

    target, fg = {"x": 0.5, "y": 0.5}, None
    if treatment != "hold":
        try:
            target, fg = _salient(image_path, want_cutout=(treatment in _NEED_CUTOUT), out_dir=out_path.parent)
        except Exception:
            pass
    if treatment in _NEED_CUTOUT and not fg:
        treatment = "ken-burns-in"                       # no subject found → graceful fallback

    frames = max(30, int(round(duration * 30)))
    produced = remotion_source.render(
        "StillMotion", {"treatment": treatment, "target": target, "direction": direction},
        out_path.name, duration_frames=frames,
        background=str(image_path.resolve()), foreground=(str(Path(fg).resolve()) if fg else None),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if Path(produced).resolve() != out_path.resolve():
        import shutil
        shutil.copy(produced, out_path)
    return out_path


def render_split(left_img, right_img, out_path, duration: float = 4.0,
                 left_label: str = "", right_label: str = "", fps: int = 30) -> Path:
    """Render two stills as a SplitScreen 'collision' clip (the relational operator's payoff)."""
    from nolan import remotion_source
    out_path = Path(out_path)
    frames = max(30, int(round(duration * fps)))
    produced = remotion_source.render(
        "SplitScreen", {"leftLabel": left_label or "", "rightLabel": right_label or ""},
        out_path.name, duration_frames=frames,
        background=str(Path(left_img).resolve()), foreground=str(Path(right_img).resolve()))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if Path(produced).resolve() != out_path.resolve():
        import shutil
        shutil.copy(produced, out_path)
    return out_path


def render_stat_over(media_path, value, out_path, *, prefix: str = "", suffix: str = "",
                     caption: str = "", decimals: int = 0, theme=None, accent: str = "",
                     kind: str = "image", duration: float = 5.0, fps: int = 30) -> Path:
    """Render the SCALE count-up (StatOver) over a tangible-referent still or clip.

    Number + caption styling comes entirely from `theme` (resolveTheme in the composition),
    so the stat matches the rest of the video. kind='video' uses live footage as the backdrop.
    """
    from nolan import remotion_source
    out_path = Path(out_path)
    frames = max(30, int(round(duration * fps)))
    props = {"value": value, "prefix": prefix or "", "suffix": suffix or "",
             "caption": caption or "", "decimals": int(decimals or 0)}
    if theme:
        props["theme"] = theme
    if accent:
        props["accent"] = accent
    media = str(Path(media_path).resolve())
    kw = {"video": media} if kind == "video" else {"background": media}
    produced = remotion_source.render("StatOver", props, out_path.name, duration_frames=frames, **kw)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if Path(produced).resolve() != out_path.resolve():
        import shutil
        shutil.copy(produced, out_path)
    return out_path


def render_clip_montage(clips, out_path, transition: str = "fade", trans_frames: int = 16, fps: int = 30) -> Path:
    """Assemble b-roll clips/stills into one video with shot-to-shot transitions (ClipMontage).

    clips: list of {"path", "kind": "video"|"image", "duration": seconds}. transition applies
    between every pair (fade|slide|wipe|clockWipe|cut). Uses @remotion/transitions (no ffmpeg xfade).
    """
    from nolan import remotion_source
    out_path = Path(out_path)
    cards = [{"src": str(Path(c["path"]).resolve()), "kind": c.get("kind", "video"),
              "durationInFrames": max(1, int(round(c.get("duration", 3.0) * fps)))} for c in clips]
    n_trans = max(0, len(cards) - 1)
    transitions = [{"type": transition, "durationInFrames": trans_frames}] * n_trans
    overlap = 0 if transition == "cut" else trans_frames * n_trans
    total = max(30, sum(c["durationInFrames"] for c in cards) - overlap)
    produced = remotion_source.render("ClipMontage", {"transitions": transitions},
                                      out_path.name, duration_frames=total, cards=cards)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if Path(produced).resolve() != out_path.resolve():
        import shutil
        shutil.copy(produced, out_path)
    return out_path
