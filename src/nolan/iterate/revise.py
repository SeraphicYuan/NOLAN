"""Apply a human comment to one scene -> a renderable field patch (the gate).

`revise_scene` runs an LLM that turns a free-text note + the existing scene into a
JSON patch of *only* the changed fields. Motion/graphic edits come back as a
`motion_brief` string which we compile to a validated `motion_spec` via
`nolan.motion.compile_spec`. `apply_edit` supports both modes the user chose:
an agent note OR a direct field patch, per scene.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

# Fields a human/agent may change. Kept narrow so a note can't corrupt routing.
# `assets` is the per-scene asset tray (UI-managed; the agent references it, see below).
# `transition`/`shots` are the editing umbrella's authored fields (gated by
# nolan.editing.validate_scene_editing at premium eligibility).
# `still_treatment` is the human camera lock (STILL_TREATMENTS vocabulary;
# assign_still_treatments honors it verbatim).
_BASE = {"narration_excerpt", "visual_description", "visual_type", "duration",
         "assets", "transition", "shots", "still_treatment", "texture"}
_SEGMENT = _BASE | {"search_query", "comfyui_prompt", "motion_spec"}
_ORCH = _BASE | {"layout_spec", "motion_spec", "search_query", "comfyui_prompt"}


def editable_fields(pipeline: str) -> set:
    return _SEGMENT if pipeline == "segment" else _ORCH


_GUIDE = (
    "You revise ONE scene of a video-essay scene plan from a human note. "
    "Output ONLY a JSON object containing the fields that should change — omit unchanged fields. "
    "Editable fields for this scene: {fields}. "
    "Rules:\n"
    "- To change an animated graphic/text effect, DO NOT write motion_spec directly. "
    "Instead return a `motion_brief` string: a precise natural-language description of the "
    "desired effect (what shows, where on screen, accent, timing). It will be compiled to a spec.\n"
    "- For a PHOTO MONTAGE / GRID of pictures (multiple images, a grid/tile, 'fly in', or "
    "'zoom one picture when the voiceover says X'), return a `photo_brief` OBJECT (do not write "
    "motion_spec). Schema:\n"
    "    {{kind:'photo-story', layout:'grid'|'free', images:[<path>... or {{src,caption?,place?:[x,y],scale?,frame?,motion?:[verbs]}}],\n"
    "     background?:'#hex', grid?:'RxC', fly_in?:'one-by-one'|'row'|'col',\n"
    "     focus?:{{image:<idx>, at:<TimeRef>, hold?, scale?}}}}\n"
    "  TimeRef anchors timing to the voiceover: a number (sec), 'start'/'end'/'mid', or "
    "{{cue:'<spoken word/phrase>'}} to fire when the VO says it. Free-layout motion verbs: "
    "{{enter:'left|right|top|bottom',at}}, {{fade:'in|out',at}}, {{tilt:<deg>,at}}, {{pan:<deg>,at}} (3D), "
    "{{move:[x,y],at}}, {{path:[{{to:[x,y],at}}...]}}, {{zoom:<scale>,at}}.\n"
    "  IMAGES: if the scene lists BOUND ASSETS below, reference them in `images` as "
    "{{ref:'<asset id>'}} (preferred) — match the note's wording ('pic 4', 'the breadline photo') "
    "to an asset's id/label. Otherwise use explicit image paths from the note.\n"
    "- For stock/library footage scenes, edit `search_query` (keywords) or `comfyui_prompt` "
    "(image-gen prompt).\n"
    "- For orchestrator `layout_spec` scenes you may return a full corrected `layout_spec` object "
    "({{template, params}}).\n"
    "- Keep edits minimal and faithful to the note. Return {{}} if nothing should change."
)


def _assets_summary(assets) -> str:
    """A compact, id-first listing of the scene's bound assets for the LLM to reference."""
    import os
    if not assets:
        return ""
    lines = []
    for i, a in enumerate(assets):
        if not isinstance(a, dict):
            continue
        label = a.get("label") or os.path.basename(str(a.get("src", "")))
        lines.append(f"  [{i}] id={a.get('id')} kind={a.get('kind', 'image')} label={label!r}")
    return "\nBOUND ASSETS (reference in a photo_brief by {ref:'<id>'}):\n" + "\n".join(lines) + "\n" if lines else ""


_MENTION_RE = re.compile(r"@([A-Za-z]\w*)")


def resolve_asset_mentions(note: Optional[str], assets) -> Optional[str]:
    """Expand `@<asset-id>` mentions in a human note into explicit references.

    The Scenes UI lets a human type `@a1` to point precisely at a bound asset.
    We replace it with `[asset a1 "label" (kind[, in-out])]` so both the revise
    LLM (which references assets by id) and a dispatched Claude agent get an
    unambiguous pointer instead of guessing from prose. Unknown ids are left as-is.
    """
    import os
    if not note or not assets:
        return note
    idx = {str(a.get("id")): a for a in assets if isinstance(a, dict)}
    def _sub(m):
        a = idx.get(m.group(1))
        if not a:
            return m.group(0)
        label = a.get("label") or os.path.basename(str(a.get("src", ""))) or m.group(1)
        kind = a.get("kind", "image")
        span = ""
        if kind in ("clip", "video") and a.get("clip_start") is not None:
            span = f", {a.get('clip_start')}-{a.get('clip_end')}s"
        return f'[asset {m.group(1)} "{label}" ({kind}{span})]'
    return _MENTION_RE.sub(_sub, note)


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


async def revise_scene(scene: dict, note: str, client, pipeline: str,
                       transcript_words: Optional[list] = None) -> dict:
    """Return a whitelisted patch of changed fields for `scene` given `note`.

    `transcript_words` (a word-timed transcript, abs seconds) is used to resolve
    voiceover cue timing in a `photo_brief`; falls back to scene.subtitle_cues.
    """
    wl = editable_fields(pipeline)
    system = _GUIDE.format(fields=", ".join(sorted(wl)))
    scene_json = json.dumps({k: v for k, v in scene.items() if k != "assets"}, default=str)[:2500]
    assets_block = _assets_summary(scene.get("assets"))
    note = resolve_asset_mentions(note, scene.get("assets"))  # expand @a1 -> explicit reference
    prompt = (f"SCENE:\n{scene_json}\n{assets_block}\nHUMAN NOTE:\n{note}\n\n"
              "Return the JSON patch now.")
    raw = await client.generate(prompt, system_prompt=system)
    patch = _extract_json(raw)

    # photo_brief (montage/grid) -> resolved motion_spec via the brief layer.
    # Resolved at design time so cue timing can use this scene's narration word-timing.
    pbrief = patch.pop("photo_brief", None)
    if pbrief:
        from nolan.brief import resolve_brief, SceneContext
        ctx = SceneContext.from_scene(scene, words=transcript_words)
        spec, messages = resolve_brief(pbrief, ctx)
        if spec:
            patch["motion_spec"] = spec
            patch.setdefault("visual_type", "graphic")
        for m in messages:
            print(f"[photo_brief] {m}")

    # motion_brief -> compiled motion_spec (skip on validation failure)
    brief = patch.pop("motion_brief", None)
    if brief:
        from nolan.motion import compile_spec
        spec, errors = await compile_spec(str(brief), client)
        if not errors:
            patch["motion_spec"] = spec

    return {k: v for k, v in patch.items() if k in wl}


# Editing one of these changes *which asset* the scene should use, so the
# resolve/match stage must re-run (not just the renderer) — clear the cached pick.
_RERESOLVE_TRIGGERS = {"search_query", "visual_type"}


def apply_patch(scene: dict, patch: dict) -> None:
    """Apply `patch` to `scene` in place and mark it dirty (force re-render)."""
    scene.update(patch)
    if "shots" in patch:
        scene["shots_auto"] = False    # human-authored shots outrank motion
    scene["rendered_clip"] = None   # dirty -> rerender_scenes will rebuild it
    if _RERESOLVE_TRIGGERS & set(patch):
        # Asset selection is now stale: drop the cached match so re-render re-resolves.
        scene["matched_clip"] = None
        scene["resolved_source"] = None


async def apply_edit(plan_path, scene_id: str, *, patch: Optional[dict] = None,
                     note: Optional[str] = None, client=None,
                     pipeline: Optional[str] = None,
                     transcript_words: Optional[list] = None) -> dict:
    """Load plan, revise one scene (via note OR direct patch), save, return the patch."""
    from .engine import load_plan_raw, save_plan_raw, find_scene, detect_pipeline

    plan_path = Path(plan_path)
    data = load_plan_raw(plan_path)
    scene = find_scene(data, scene_id)
    if scene is None:
        raise KeyError(f"scene '{scene_id}' not found in {plan_path}")
    pipeline = pipeline or detect_pipeline(plan_path)

    if note:
        if client is None:
            raise ValueError("note-based revision requires an llm client")
        resolved = await revise_scene(scene, note, client, pipeline, transcript_words=transcript_words)
    else:
        wl = editable_fields(pipeline)
        resolved = {k: v for k, v in (patch or {}).items() if k in wl}

    # taste ledger (SOTA #9): a human override is preference data — record
    # (what the pipeline had, what the human chose) per changed field. Test
    # projects are excluded inside record_taste_event.
    _STAGE_BY_FIELD = {"layout_spec": "slides", "motion_spec": "motion",
                       "transition": "editing", "shots": "editing",
                       "visual_type": "scenes", "search_query": "scenes",
                       "comfyui_prompt": "scenes", "duration": "tempo"}
    try:
        from nolan.taste import record_taste_event
        for k, v in resolved.items():
            if k not in _STAGE_BY_FIELD:
                continue
            old_v = scene.get(k)
            if old_v == v:
                continue
            record_taste_event(
                project=plan_path.parent.name,
                stage=_STAGE_BY_FIELD[k],
                context=f"{scene_id}: {k} ({(scene.get('narration_excerpt') or '')[:80]})",
                proposed=old_v, chose=v,
                project_path=plan_path.parent)
    except Exception:  # noqa: BLE001 — the ledger must never block an edit
        pass

    apply_patch(scene, resolved)
    save_plan_raw(plan_path, data)
    return resolved
