"""Tier-1 of the Clips→HyperFrames effect adaptation.

The Clips page can already dispatch an agent to analyze a reference clip and CLONE its effect — but it produced
REMOTION (`.tsx`). HyperFrames is GSAP, so this retargets the loop: the agent authors a scene-scoped GSAP effect
(a `raw` block = `data.html` clip fragments + `data.tl` GSAP timeline lines), deduped against the HyperFrames
catalog (blocks / reveals / transitions), and `apply_effect` lands it on ONE scene through the author.py gate —
a malformed effect reverts, nothing ships broken. This is the standalone-effect tier; promotion into a reusable
block (compose_extension.py) is Tier-2 and layered on top.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Union

from .edit import _comp_dir, _edit, _find_scene, catalog, load_frame_spec, frame_transcripts

REPO = Path(__file__).resolve().parents[3]


def apply_effect(comp: str, frame_id: str, scene_id: str, html: Union[str, List[str]], tl: List[str]) -> Dict[str, Any]:
    """Apply an agent-authored GSAP effect to ONE scene by turning it into a `raw` block (data.html + data.tl).
    Runs through the author.py gate (a bad effect reverts). Timing (start/dur) + the scene id are preserved."""
    frags = html if isinstance(html, list) else [html]
    if not frags or not any(str(f).strip() for f in frags):
        return {"applied": False, "errors": "empty effect html"}

    def mutate(fr):
        sc = _find_scene(fr, scene_id)
        sc["type"] = "raw"
        d = sc.setdefault("data", {})
        d["html"] = [str(f) for f in frags]
        d["tl"] = [str(t) for t in (tl or [])]
        sc.setdefault("meta", {})["effect_source"] = "agent-clip-clone"      # provenance

    return _edit(comp, frame_id, mutate, kind="effect", scene_id=scene_id, summary=f"GSAP effect on {scene_id}")


def apply_block(comp: str, frame_id: str, scene_id: str, block_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Tier-2 landing: retarget ONE scene onto a REUSABLE catalog block (e.g. `spotlight`) instead of a
    bespoke `raw` effect. Validates the block_type against the composer catalog, then sets sc.type +
    sc.data through the author.py gate (a bad type / bad data reverts). Timing + scene id are preserved.
    This is the payoff of promoting a cloned effect into a parametric block — the agent picks params,
    the deterministic layout lives in the block."""
    known = set((catalog().get("scene_templates") or {}).keys())
    if block_type not in known:
        return {"applied": False, "errors": f"unknown block type {block_type!r} — not in the composer catalog"}
    if not isinstance(data, dict) or not data:
        return {"applied": False, "errors": "empty block data"}

    def mutate(fr):
        sc = _find_scene(fr, scene_id)
        sc["type"] = block_type
        sc["data"] = dict(data)
        sc.setdefault("meta", {})["effect_source"] = "agent-clip-clone"      # provenance
        sc["meta"]["effect_block"] = block_type

    return _edit(comp, frame_id, mutate, kind="effect", scene_id=scene_id,
                 summary=f"{block_type} block on {scene_id}")


def hf_catalog_md() -> str:
    """The HyperFrames motion catalog (blocks / text reveals / scene transitions) the agent must DEDUP against
    before proposing a new effect — the GSAP analogue of the Remotion pipeline's `_motion_catalog_md`."""
    c = catalog()
    out = ["## HyperFrames catalog — dedup against these FIRST (reuse an existing one when it fits)", "",
           "### Blocks (whole-scene templates — `data.type`)"]
    for name, spec in (c.get("scene_templates") or {}).items():
        out.append(f"- **{name}** — {(spec.get('purpose') or '').strip()}")
    out += ["", "### Text reveals (`data.reveal`)"]
    out += [f"- {n}" for n in (c.get("reveals") or {}) if n != "_doc"]
    out += ["", "### Scene transitions (`transition_out.kind`)"]
    out += [f"- {n}" for n in (c.get("transitions") or {}) if n != "_doc"]
    return "\n".join(out)


def effect_task_brief(comp: str, frame_id: str, scene_id: str, clip_ref: str = "", comment: str = "",
                      frame_paths: List[str] = None, clip_meta: Dict[str, Any] = None) -> str:
    """The GSAP task brief for the effect agent (retargeted from the Remotion `_effect_task_markdown`). Asks it
    to recreate a reference clip's effect as a scene-scoped `raw` GSAP effect, deduped against the HF catalog,
    written as a proposal JSON that `apply_effect` lands. Returned to the caller to dispatch into tmux."""
    spec, info = load_frame_spec(comp, frame_id)
    sc = _find_scene(spec["frames"][info["i"]], scene_id)
    dur = float(sc.get("dur", 0) or 0)
    transcript = (frame_transcripts(comp, frame_id) or {}).get(scene_id, "")
    proposal = (_comp_dir(comp) / "compositions" / "_effects" / f"{scene_id}.json").as_posix()
    frames_md = "\n".join(f"- {p}" for p in (frame_paths or [])) or "(no frames extracted — inspect the clip file)"
    src_md = ""
    if clip_meta:
        src_md = (f"\n- Source: {clip_meta.get('video')} "
                  f"[{clip_meta.get('start')}–{clip_meta.get('end')}s]")
    return f"""# Clone a video effect onto HyperFrames scene `{scene_id}` (GSAP, not Remotion)

You are recreating the motion/effect from a REFERENCE CLIP as a **scene-scoped GSAP effect** in NOLAN's
HyperFrames composer. Output is a `raw` block: `data.html` (clip HTML fragments) + `data.tl` (GSAP timeline
lines merged into the frame's ONE paused, seek-safe timeline). This is NOT Remotion — no React, no
`useCurrentFrame()`; use GSAP `tl.fromTo("#id",{{…}},{{…}},<absolute-seconds>)` on transforms/opacity only.

## The reference
- Clip: {clip_ref or "(none provided)"}{src_md}
- Sampled frames (LOOK at these — they ARE the effect to clone):
{frames_md}
- Human note: {comment or "(none)"}

## The target scene
- `{scene_id}` in frame `{frame_id}`, duration ~{dur:.2f}s. Its narration: "{transcript[:200]}"
- Author IDs prefixed with `{scene_id}-`, every timed element `class="clip"` with data-start / data-duration /
  data-track-index (ground=0, scrim=1, content=2, props=4+). Frame-ABSOLUTE times in `data.tl`.

## Steps
1. Describe the reference effect precisely (camera move / transition / text or graphic animation / color).
2. DEDUP FIRST against the HyperFrames catalog below. **PREFER a reusable block**: if an existing block already
   does it (e.g. `spotlight` = bg-removed subject center/left/right + position-responsive label), instantiate
   THAT with parameters — do NOT hand-author raw HTML for something a block covers. Only go `raw` when no
   block/reveal/transition fits.
3a. **Block form (preferred)** — the effect maps to a catalog block: pick it, fill its `data` from the catalog's
    `data_schema`. This is a parametric, reusable, gated landing.
3b. **Raw form (only if nothing fits)** — author a GSAP `raw` effect. Deterministic + seek-safe:
    transforms/opacity/onUpdate-proxy only, no CSS transitions, no `Math.random`/`Date.now`; IDs prefixed
    `{scene_id}-`, every timed element `class="clip"` with data-start/data-duration/data-track-index.
4. Write your proposal to `{proposal}` as JSON — ONE of:
   - block: `{{"dedup": "covered-by <block>", "rationale": "...", "block": {{"type": "<block>", "data": {{…}}}}}}`
   - raw:   `{{"dedup": "new", "rationale": "...", "html": ["<div ...>", …], "tl": ["tl.fromTo(...)", …]}}`
   Then the human accepts it (block lands via `apply_block`, raw via `apply_effect` — both gated by the composer).

{hf_catalog_md()}
"""
