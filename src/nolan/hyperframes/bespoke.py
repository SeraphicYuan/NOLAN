"""Bespoke mode for the HyperFrames edit page — hand SELECTED scene(s) to a fleet agent to author a
fully-custom `raw` scene (bespoke HTML + GSAP), reviewed as a PROPOSAL, woven per frame. The escape
hatch for when no compose.py block fits (or a block can't do what the scene needs — e.g. exact word
positioning the deterministic `spotlight` layout won't expose).

It REUSES the whole propose->gate->accept->render pipeline built for batch edits: the agent calls
`edit.propose_scene_edit(...)` with a raw-conversion op, the proposal lands in `.hf_proposals.json`,
the human reviews it in the existing panel, accept applies it through the author.py gate + rebuilds
the frame HTML, and `incremental.render_one` re-renders just that frame. A bespoke scene IS a `raw`
scene, and the composer gate now lints its seek-safety (author.py `_raw_seek_errors`), so a
non-deterministic tween reverts. The NEW part here is (a) the rich CONTEXT the agent is handed — the
scene's purpose, narration + word timings, theme tokens, the frame's other scenes (continuity), the
assets, and the hard authoring contract — and (b) the per-scene fan-out (one agent per scene).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import batch as _batch
from .edit import (asset_pool_meta, catalog, comp_dir, frame_transcripts, list_assets,
                   load_frame_spec, log_activity)
from nolan import composition as _composition

REPO = Path(__file__).resolve().parents[3]


def _theme_composition_allowed(theme_slug: str):
    """The theme's declared composition.allowed set (constrains archetype choice), or None if the theme
    doesn't declare one yet — in which case selection is purely content-first (scene type / beat)."""
    if not theme_slug:
        return None
    f = REPO / "themes" / theme_slug / "theme.json"
    try:
        c = json.loads(f.read_text(encoding="utf-8")).get("composition") or {}
        return c.get("allowed") or None
    except Exception:
        return None
FLEET_SESSIONS = ["nolan1", "nolan2", "nolan3", "nolan4", "nolan5", "nolan6"]


def _find(fr: Dict[str, Any], sid: str) -> Optional[Dict[str, Any]]:
    return next((s for s in fr.get("scenes", []) if s.get("id") == sid), None)


def _scene_words(comp: str, frame_id: str, scene_id: str, sc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The scene's narration words WITH frame-local timings (for word-anchored reveals). [] if unaligned."""
    meta_f = comp_dir(comp) / "audio_meta.json"
    if not meta_f.exists():
        return []
    try:
        meta = json.loads(meta_f.read_text(encoding="utf-8"))
    except Exception:
        return []
    m = re.match(r"(\d+)", frame_id)
    n = str(int(m.group(1))) if m else None
    voice = next((v for v in meta.get("voices", []) if str(v.get("frame")) == n), None) if n else None
    if not voice:
        return []
    a = float(sc.get("start", 0) or 0)
    b = a + float(sc.get("dur", 0) or 0)
    out = []
    for w in voice.get("words", []):
        ws, we = float(w.get("start", 0) or 0), float(w.get("end") or w.get("start") or 0)
        if ws < b and we > a:
            out.append({"w": w.get("word") or w.get("text") or "", "start": round(ws - a, 2), "end": round(we - a, 2)})
    return out


def _theme_tokens(theme: str, limit: int = 22) -> Dict[str, str]:
    """The design tokens (--name: value) from themes/<theme>/tokens.css — the ACTUAL palette/type the
    bespoke scene must match (the same vars compose._theme_vars injects as #root custom props)."""
    if not theme:
        return {}
    css = REPO / "themes" / theme / "tokens.css"
    if not css.exists():
        return {}
    toks: Dict[str, str] = {}
    for name, val in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", css.read_text(encoding="utf-8")):
        toks.setdefault(name.strip(), val.strip())
        if len(toks) >= limit:
            break
    return toks


def _raw_schema() -> Dict[str, Any]:
    return (catalog().get("scene_templates") or {}).get("raw", {})


def bespoke_task_brief(comp: str, frame_id: str, scene_id: str, direction: str = "",
                       session: str = "") -> str:
    """The context-rich task brief for a bespoke-scene agent. Assembles everything the agent needs to
    author ONE scene from scratch (its meaning, narration+timings, theme, continuity, assets, the raw
    contract) and submit it as a reviewable proposal. Returned to the caller to write + dispatch."""
    spec, info = load_frame_spec(comp, frame_id)
    fr = spec["frames"][info["i"]]
    sc = _find(fr, scene_id) or {}
    theme = _batch._theme(comp)
    tokens = _theme_tokens(theme)
    transcript = (frame_transcripts(comp, frame_id) or {}).get(scene_id, "")
    words = _scene_words(comp, frame_id, scene_id, sc)
    dur = float(sc.get("dur", 0) or 0)
    start = float(sc.get("start", 0) or 0)
    is_last = fr.get("scenes", [])[-1].get("id") == scene_id if fr.get("scenes") else True

    # continuity: the frame's OTHER scenes (type + one-line + window)
    others = []
    for s in fr.get("scenes", []):
        if s.get("id") == scene_id:
            continue
        lines = (s.get("data") or {}).get("lines") or (s.get("data") or {}).get("headline") or []
        gist = (lines[0] if isinstance(lines, list) and lines else (s.get("data") or {}).get("kicker") or "")
        others.append(f"  - {s.get('id')} [{s.get('type')}] {s.get('start')}–{round(float(s.get('start',0))+float(s.get('dur',0)),1)}s: {str(gist)[:60]}")

    assets = [a["path"] for a in list_assets(comp)][:24]
    pool = asset_pool_meta(comp)
    words_md = ", ".join(f'"{w["w"]}"@{w["start"]}s' for w in words[:40]) or "(no aligned words — pace to the duration)"
    tokens_md = "\n".join(f"  {k}: {v}" for k, v in tokens.items()) or "  (theme has no tokens.css — use the composer default palette)"
    # Composition archetype — the layout LEVER (A/B/C/D proved an explicit named archetype moves the agent
    # off its left-column default). Content-first: the scene's beat/type suggests it, the theme's allowed
    # set constrains it, an explicit human direction overrides it.
    archetype = _composition.resolve(scene_type=sc.get("type"), beat=transcript, direction=direction,
                                     allowed=_theme_composition_allowed(theme))
    composition_md = _composition.brief_section(archetype)
    schema = _raw_schema()
    op = ('[{"op":"patch","scene_id":"%s","patch":{"type":"raw","data":{"html":["<...>"],"tl":["tl.fromTo(...)"]}}}]'
          % scene_id)

    return f"""# Bespoke HyperFrames scene — author `{scene_id}` from scratch (GSAP `raw`)

You are fleet agent '{session or "(unassigned)"}'. Author a **fully-custom** design for ONE scene of a
HyperFrames video essay, because no compose.py block fits it well. Output is a `raw` scene — bespoke
HTML fragments + GSAP timeline lines merged into the frame's ONE paused, seek-safe timeline. You submit
it as a PROPOSAL (the human reviews + accepts; you do NOT touch canonical specs or render).

## What this scene is SAYING (design to the meaning, not decoration)
- Scene `{scene_id}` in frame `{frame_id}`, currently a `{sc.get('type')}` block.
- **Narration (this scene): "{transcript[:400]}"**
- Word timings (frame-local seconds — ANCHOR your reveals to these): {words_md}
- Duration **{dur:.2f}s** (fixed — VO owns it), starts at {start:.2f}s in the frame.
- Human direction: {direction or "(none — infer the strongest visual from the narration)"}

## The look — match the theme `{theme or "(default)"}`
Use these design tokens (they resolve as CSS `var(--name)` on `#root`; prefer them over hardcoded colors):
{tokens_md}

{composition_md}

## Continuity — the frame's OTHER scenes (do not clash; be consistent)
{chr(10).join(others) or "  (this is the only scene in the frame)"}
This scene {"IS the LAST scene (an exit transition is allowed)" if is_last else "is NOT last — author NO exit/outro animation (the transition injector owns hand-offs)"}.

## Materials you may use
Assets already in the comp (reference by path in your html, e.g. <img src="assets/…">):
{chr(10).join('  - ' + a for a in assets) or "  (none — this can be a pure typographic/graphic scene)"}
{("Generated-asset prompts (context): " + "; ".join(f"{k}={v.get('gen_prompt')[:50]}" for k,v in list(pool.items())[:6] if v.get('gen_prompt'))) if pool else ""}

## The hard authoring contract (the composer gate ENFORCES the seek-safety ones — a violation reverts)
- `raw` data: {json.dumps(schema.get("data_schema", {}))}
- Every timed element: `class="clip"` + `data-start` / `data-duration` / `data-track-index`. IDs **prefixed with `{scene_id}-`**.
- Tracks: ground=0, scrim/vignette=1, content=2, props=4+. Higher = in front.
- Times in `tl` are **frame-absolute** (this scene runs {start:.2f}–{start+dur:.2f}s).
- **Seek-safe: transforms + opacity ONLY.** NO `Math.random` / `Date.now` / `new Date` / `performance.now`, NO `yoyo`, NO infinite `repeat:-1`, no CSS transitions. (These are gated — they revert.)
- Hero visible by t≤0.5s into the scene; reveal ACROSS the full duration (no front-load-then-freeze).
- **KINETIC-REPLACE — clear what you replace.** If a phrase/word is superseded by the next one in the SAME
  region, fade the outgoing element FULLY to `opacity:0` (NOT a lingering ~0.1 ghost) as the next appears —
  otherwise the text STACKS and COLLIDES. "Reveal across the full duration" means the NEW content keeps the
  scene full, never leftover ghosts piled behind the live text. A faint background echo is allowed ONLY in a
  distinct, non-overlapping zone (its own column/band) — never overlapping the current headline or chips.
- Keep all content in the top **83%** (caption keep-out at the bottom). Do NOT set `captionBar`.
- A full-bleed background rides on its OWN `class="clip"` layer (track 0), never `#root`.

## Submit your proposal (do NOT edit canonical specs)
Run this once you've authored the scene:
```
python -X utf8 -c "from nolan.hyperframes import propose_scene_edit; \\
  propose_scene_edit('{comp}', '{frame_id}', '{scene_id}', \\
    ops={op}, \\
    rationale='bespoke: <one line — what you designed and why>', agent='{session or "agent"}')"
```
The human sees it in the review panel, accepts it (gated + provenance-stamped), and re-renders this frame.
"""


def dispatch_bespoke(comp: str, scene_ids: List[str], direction: str = "",
                     sessions: Optional[List[str]] = None) -> Dict[str, Any]:
    """Fan out ONE agent per selected scene (round-robin across `sessions`), each with its own rich
    context brief written to compositions/_bespoke/<scene>_task.md. Returns per-scene dispatch info."""
    from nolan.webui import operations
    sessions = [s for s in (sessions or FLEET_SESSIONS) if s] or FLEET_SESSIONS
    task_dir = comp_dir(comp) / "compositions" / "_bespoke"
    task_dir.mkdir(parents=True, exist_ok=True)
    # group scene_id -> its frame (a scene id is unique within, but we resolve the frame that holds it)
    results = []
    for i, sid in enumerate(scene_ids):
        session = sessions[i % len(sessions)]
        frame_id = _frame_of_scene(comp, sid)
        if not frame_id:
            results.append({"scene_id": sid, "dispatched": False, "error": "scene not found in any frame"})
            continue
        brief = bespoke_task_brief(comp, frame_id, sid, direction=direction, session=session)
        task_file = task_dir / f"{sid}_task.md"
        task_file.write_text(brief, encoding="utf-8")
        dispatched = False
        try:
            operations._dispatch_to_tmux(session, f"New BESPOKE HyperFrames scene task — read "
                                         f"{task_file.as_posix()} and follow it (author scene {sid}, submit a proposal).")
            dispatched = True
        except Exception as e:
            results.append({"scene_id": sid, "frame_id": frame_id, "session": session,
                            "dispatched": False, "task": task_file.as_posix(), "error": str(e)})
            continue
        results.append({"scene_id": sid, "frame_id": frame_id, "session": session,
                        "dispatched": dispatched, "task": task_file.as_posix()})
    log_activity(comp, "bespoke", f"dispatched {sum(1 for r in results if r.get('dispatched'))}/{len(scene_ids)} bespoke scene(s)",
                 outcome="dispatched")
    return {"comp": comp, "results": results}


def _frame_of_scene(comp: str, scene_id: str) -> Optional[str]:
    """The frame_id whose spec holds `scene_id` (bespoke selects by scene; we resolve its frame)."""
    for spec_file in sorted((comp_dir(comp) / "compositions" / "frames").glob("*.spec.json")):
        try:
            spec = json.loads(spec_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        for fr in spec.get("frames", []):
            if any(s.get("id") == scene_id for s in fr.get("scenes", [])):
                return fr.get("id")
    return None
