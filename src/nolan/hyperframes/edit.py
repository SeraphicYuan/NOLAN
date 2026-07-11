"""Composer-native scene-edit engine (Phase 1: direct/mechanical edits).

The unit of EDIT is a scene (a shot inside a frame); the unit of RE-RENDER is the frame (its scenes
share one merged GSAP timeline). So an edit patches ONE scene in a per-frame spec, re-gates the whole
frame through author.py (validate + compose -> frame HTML), and previews/renders that one frame.

Cross-platform notes: the gate (author.py) runs under this process's own python (sys.executable), so it
works Windows-side (the hub) and in WSL (tests). Previews/renders shell out to `npx hyperframes` on a
throwaway single-frame scaffold (self-contained headless Chrome), which also works in both.
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[3]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
AUTHOR = BRIDGE / "author.py"
CATALOG_PATH = BRIDGE / "catalog.json"
LAB_VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"
PROJECTS = REPO / "projects"

_ROOTS = [("lab", LAB_VIDEOS), ("project", PROJECTS)]


# ------------------------------------------------------------------ discovery / read

def discover_compositions() -> List[Dict[str, Any]]:
    """Every project/lab dir that holds a composed HyperFrames frame (compositions/frames/*.spec.json)."""
    out = []
    for source, root in _ROOTS:
        if not root.exists():
            continue
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            fdir = d / "compositions" / "frames"
            if fdir.is_dir() and any(fdir.glob("*.spec.json")):
                out.append({"name": d.name, "source": source,
                            "dir": str(d), "frames": len(list(fdir.glob("*.spec.json")))})
    return out


def _kickoff_brief(slug: str, style: Optional[str] = None, pool: bool = True,
                   voiceover: bool = False, asset_density: str = "balanced") -> str:
    """The task brief the faceless-explainer agent reads to author a new essay (written to .hf_kickoff.md)."""
    rel = f"videos/{slug}"
    comp_rel = f"render-service/_lab_hyperframes/{rel}"
    bridge_rel = "render-service/_lab_hyperframes/bridge"
    style_line = f"\n- **Style:** {style}" if style else ""
    try:                                                # the style contract: craft targets + the full block palette
        from nolan.style_contract import StyleContract, authoring_brief
        contract_txt = authoring_brief(StyleContract.resolve("essay", asset_density=asset_density))
    except Exception:
        contract_txt = ""
    contract_section = ("\n\n---\n## STYLE CONTRACT — author to these targets, then lint & revise\n\n"
                        + contract_txt) if contract_txt else ""
    finish_line = (
        f"\n- **Finish (narration-timed + video + linted):** `node audio.mjs sync-durations` (frame dur = section "
        f"dur). For any `ground:{{\"kind\":\"video\"}}` or comparison `video` side, copy the pool clip into "
        f"`{rel}/assets/` and — AFTER `assemble-index`, BEFORE render — run "
        f"`python -X utf8 {bridge_rel}/assemble_media.py {comp_rel}` to mount the root / comparison videos "
        f"(archetype B); then `hyperframes render`."
        f"\n- **Lint & revise (draft → lint → revise):** score the composed essay and FIX the failing GATES until it "
        f"passes — `python -X utf8 -m nolan.style_contract {comp_rel} --dial asset_density={asset_density}`.")
    vo_line = (
        f"\n- **Voice — NOLAN-PROVIDED (do NOT synthesize a new voice):** the cloned voiceover is already "
        f"bridged into `{rel}/audio_meta.json` + `{rel}/assets/voice/0N.wav` (one wav per script section). "
        f"Author **exactly one frame per section** (frame N ↔ section N, in order). SKIP `audio.mjs generate` — "
        f"instead run `node audio.mjs sync-durations` to set each frame's duration FROM the VO (narration owns "
        f"duration), then `assemble-index` + `hyperframes render`; the narration mounts automatically as the "
        f"root voice track (data-track-index 10). Time within-frame reveals to the narration by ear."
        if voiceover else "")
    assets_line = (
        f"- **Assets — ASSET-BACKED (not faceless):** a NOLAN asset POOL is being acquired into `{rel}/capture/` "
        f"(stock images/video + qwen-VL captions, via the `pool.py` bridge). SELECT `asset_candidates` from "
        f"`{rel}/capture/extracted/asset-descriptions.md` for image beats (collage / gallery / newshead / timeline / "
        f"comparison); still invent typography / diagram / data-viz where no real asset fits. Resolve BGM/SFX/logos via `/media-use`."
        if pool else
        f"- **Assets:** faceless — invent per scene. Resolve BGM/SFX/images/logos via `/media-use`; land them in `{rel}/assets/`."
    )
    return f"""# New HyperFrames essay — kickoff (`{slug}`)

Author a **faceless explainer video** from the source text, using the `/faceless-explainer` skill in
**NOLAN compose-first mode — the hybrid pipeline (the required default here)**. You are the orchestrator;
run its steps in order and pass each gate.

- **Project dir:** `{rel}/` (already scaffolded; the script is in `SOURCE.md`).
- **Input:** `{rel}/SOURCE.md` — the topic/script to explain.
- **Output:** composed frames at `{rel}/compositions/frames/NN-*.html` (+ `.spec.json`) and `{rel}/index.html`
  — that is what makes this composition appear on the hub's `/hyperframes` edit page.
{assets_line}{vo_line}
- **Pipeline — HYBRID / compose-first (required):** at Step 5, dispatch `sub-agents/compose-first-frame-worker.md`
  (NOT the stock `frame-worker.md`) with `BRIDGE_DIR=render-service/_lab_hyperframes/bridge/`. Express each Scene
  with a `bridge/catalog.json` composer template (stat · statement · geo · timeline · newshead · collage · diagram ·
  comparison · gallery · carousel · chart · linedraw · … + the `reveal`/`transition` vocabularies) and build it
  deterministically through the `author.py` gate; hand-author a bespoke `raw` / native-HF scene ONLY where no
  template fits.{style_line}{finish_line}

When the frames are composed, tell the user the composition id is **`{slug}`** — they'll refine it per-scene on `/hyperframes`.{contract_section}
"""


def _resolve_vo_source(vo_source: str) -> Path:
    """A voiceover source is a NOLAN project name (under projects/) or an explicit path with assets/voiceover/."""
    p = Path(vo_source)
    if p.exists():
        return p
    cand = PROJECTS / vo_source
    if cand.exists():
        return cand
    raise FileNotFoundError(f"voiceover source not found: {vo_source!r} (a projects/<name> or a path)")


def attach_voiceover(comp: str, vo_source: str) -> Dict[str, Any]:
    """Bridge a NOLAN voiceover into a HyperFrames comp: writes <comp>/audio_meta.json + assets/voice/0N.wav
    via bridge/vo_bridge.py, so the faceless sync-durations + assemble-index chain runs on the cloned voice
    (no second TTS pass). vo_source = a projects/<name> (its assets/voiceover/) or an explicit path."""
    import importlib.util
    pdir = _project_dir(comp)
    vo = _resolve_vo_source(vo_source)
    spec = importlib.util.spec_from_file_location("vo_bridge", str(BRIDGE / "vo_bridge.py"))
    vb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vb)
    return vb.translate(pdir, vo)


def new_essay(name: str, script: str, style: Optional[str] = None, acquire_pool: bool = True,
              voiceover: Optional[str] = None, asset_density: str = "balanced") -> Dict[str, Any]:
    """Scaffold a new HyperFrames essay project under the lab videos root + write a kickoff brief for the
    faceless-explainer agent. Returns {comp, dir, prompt, acquire_pool}; the caller dispatches `prompt` to a
    tmux agent (and, if acquire_pool, first runs the asset pool). Shows up in /hyperframes once frames exist.

    voiceover: None -> faceless self-generated voice (default). A NOLAN project name / path with
    assets/voiceover/ -> its cloned VO is bridged in NOW (audio_meta.json written; frame durations come from
    the sections). 'auto' -> the caller synthesizes a VO from SOURCE.md first, then calls attach_voiceover."""
    if not (script or "").strip():
        raise ValueError("script is required")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", (name or "").strip()).strip("-").lower() or "essay"
    pdir = LAB_VIDEOS / slug
    fdir = pdir / "compositions" / "frames"
    if fdir.is_dir() and any(fdir.glob("*.spec.json")):
        raise ValueError(f"a composition named '{slug}' already exists — pick another name")
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "assets").mkdir(exist_ok=True)
    (pdir / "SOURCE.md").write_text(script, encoding="utf-8")
    (pdir / ".hf_kickoff.md").write_text(
        _kickoff_brief(slug, style, acquire_pool, voiceover=bool(voiceover), asset_density=asset_density),
        encoding="utf-8")
    prompt = (f"New HyperFrames essay: read render-service/_lab_hyperframes/videos/{slug}/.hf_kickoff.md and execute "
              f"it — author a faceless explainer from that project's SOURCE.md into its compositions/frames/ using the "
              f"/faceless-explainer skill in NOLAN compose-first (hybrid) mode. Report the composition id '{slug}' when done.")
    res = {"comp": slug, "dir": str(pdir), "prompt": prompt, "acquire_pool": bool(acquire_pool)}
    if voiceover and voiceover != "auto":          # bridge an existing NOLAN VO in now
        try:
            res["voiceover"] = attach_voiceover(slug, voiceover)
        except Exception as e:
            res["voiceover_error"] = f"{type(e).__name__}: {e}"
    elif voiceover == "auto":                      # caller runs synth from SOURCE.md, then attach_voiceover
        res["voiceover_auto"] = True
    return res


def _project_dir(comp: str) -> Path:
    """Composition dir whether it's fully composed (has frames) or just scaffolded (new essay, no frames yet)."""
    try:
        return comp_dir(comp)
    except FileNotFoundError:
        d = LAB_VIDEOS / comp
        if d.is_dir():
            return d
        raise


def _project_script(pdir: Path) -> str:
    """The project's script text, for deriving asset needs (SOURCE.md from new-essay, else the skill's SCRIPT.md)."""
    for cand in ("SOURCE.md", "SCRIPT.md", "STORYBOARD.md"):
        f = pdir / cand
        if f.is_file():
            return f.read_text(encoding="utf-8")
    return ""


async def derive_asset_needs(script: str, client, k: int = 8) -> List[Dict[str, Any]]:
    """LLM: an essay script -> a `needs` list for the pool bridge, with QUERY-VARIANT EXPANSION.

    Each need carries several distinct stock-search phrasings (`queries`) so the bridge casts a wide
    net (multi-query retrieval — recall is the bottleneck in stock search), an `evocative` flag that
    routes abstract subjects through the evoke_broll metaphor super-search, and a `gen_prompt` used
    for krea2 gap-fill when stock finds nothing. `query` (the plain phrasing) stays for back-compat."""
    system = ("You plan VISUAL ASSET needs for a video essay. From the script, list the visual subjects worth "
              "gathering — people, places, objects, events, archival footage, and abstract themes. For EACH, give "
              "several DISTINCT stock-search phrasings so we cast a wide net, mark whether it is abstract, and give "
              f"a fallback generation prompt. Return ONLY a JSON array of up to {k} items, each: "
              "{\"id\":\"a1\", \"query\":\"plain 3-6 word stock search\", "
              "\"queries\":[\"3-5 distinct phrasings incl. the plain one — synonyms, a concrete instance, "
              "a shot/era/mood descriptor\"], \"media_type\":\"image\" or \"video\", \"n\":3, "
              "\"evocative\": true if the subject is an ABSTRACT idea/emotion/theme (not a concrete photographable "
              "thing) else false, \"category\":\"art\" or \"archival\" or \"general\" "
              "(art = painting/fine-art/illustration; archival = historical photos or footage; "
              "general = modern photos/video — people, places, nature, objects), "
              "\"gen_prompt\":\"one cinematic image-generation prompt for this subject\"}. "
              "Prefer image; choose video for motion-critical subjects AND archival/historical FOOTAGE "
              "(newsreel, documentary, period film) so archival-video sources are used. No prose, no code fences.")
    raw = (await client.generate((script or "")[:6000], system_prompt=system)).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    i, j = raw.find("["), raw.rfind("]")
    items = json.loads(raw[i:j + 1]) if 0 <= i < j else []
    out = []
    for n, it in enumerate(items[:k]):
        q = str(it.get("query", "")).strip()
        if not q:
            continue
        variants = [str(x).strip() for x in (it.get("queries") or []) if str(x).strip()]
        if q not in variants:
            variants = [q] + variants
        seen, queries = set(), []                       # de-dup the phrasings, cap the fan-out
        for x in variants:
            key = x.lower()
            if key not in seen:
                seen.add(key)
                queries.append(x)
        cat = str(it.get("category", "general")).strip().lower()
        if cat not in ("art", "archival", "general"):
            cat = "general"
        out.append({"id": it.get("id") or f"a{n + 1}", "query": q, "queries": queries[:5],
                    "media_type": "video" if it.get("media_type") == "video" else "image",
                    "n": int(it.get("n", 3) or 3),
                    "evocative": bool(it.get("evocative")), "category": cat,
                    "gen_prompt": (str(it.get("gen_prompt") or q).strip())})
    return out


def run_pool(comp: str, needs: List[Dict[str, Any]], per: int = 3) -> Dict[str, Any]:
    """Run the NOLAN->HF asset bridge (bridge/pool.py): COLLECT -> CAPTION -> INVENTORY into <project>/capture/.
    Blocking (fan-out + captioning takes minutes) — call from a background job / thread."""
    if not needs:
        raise ValueError("no asset needs to acquire")
    pdir = _project_dir(comp)
    needs_file = pdir / "capture" / "needs.json"
    needs_file.parent.mkdir(parents=True, exist_ok=True)
    needs_file.write_text(json.dumps(needs, ensure_ascii=False, indent=2), encoding="utf-8")
    r = subprocess.run([sys.executable, "-X", "utf8", str(BRIDGE / "pool.py"),
                        "--needs", str(needs_file), "--project", str(pdir), "--per", str(per)],
                       cwd=str(BRIDGE), capture_output=True, text=True, encoding="utf-8", errors="replace")
    pool_json = pdir / "pool.json"
    pool = json.loads(pool_json.read_text(encoding="utf-8")) if pool_json.exists() else []
    return {"ok": r.returncode == 0, "count": len(pool), "needs": needs,
            "inventory": str(pdir / "capture" / "extracted" / "asset-descriptions.md"),
            "output": (r.stdout + r.stderr)[-1200:]}


def _comp_dir(comp: str) -> Path:
    for _source, root in _ROOTS:
        d = root / comp
        if (d / "compositions" / "frames").is_dir():
            return d
    raise FileNotFoundError(f"composition {comp!r} not found under lab videos or projects")


def _frames_dir(comp: str) -> Path:
    return _comp_dir(comp) / "compositions" / "frames"


def comp_dir(comp: str) -> Path:
    """Public: the composition's root directory (raises FileNotFoundError if unknown)."""
    return _comp_dir(comp)


def _frame_index(comp: str) -> Dict[str, Dict[str, Any]]:
    """frame_id -> {spec_file, i} across every spec file in the composition (usually one frame per file)."""
    idx: Dict[str, Dict[str, Any]] = {}
    for sf in sorted(_frames_dir(comp).glob("*.spec.json")):
        try:
            spec = json.loads(sf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for i, fr in enumerate(spec.get("frames", [])):
            if "id" in fr:
                idx[fr["id"]] = {"spec_file": sf, "i": i}
    return idx


def _scene_summary(s: Dict[str, Any]) -> str:
    d = s.get("data", {}) or {}
    for k in ("title", "headline", "kicker", "name", "track", "code", "text"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()[:60]
    if isinstance(d.get("lines"), list) and d["lines"]:
        return " ".join(str(x) for x in d["lines"])[:60]
    if isinstance(d.get("items"), list) and d["items"]:
        return f'{len(d["items"])} item(s)'
    return s.get("type", "?")


def list_frames(comp: str) -> List[Dict[str, Any]]:
    """The frame -> scene tree for a composition (the /hyperframes page payload)."""
    fdir = _frames_dir(comp)
    frames = []
    for sf in sorted(fdir.glob("*.spec.json")):
        spec = json.loads(sf.read_text(encoding="utf-8"))
        for fr in spec.get("frames", []):
            frames.append({
                "id": fr["id"], "dur": fr.get("dur"), "spec_file": sf.name,
                "html_exists": (fdir / f'{fr["id"]}.html').exists(),
                "preview_mp4": (fdir / f'{fr["id"]}.preview.mp4').exists(),
                "scenes": [{
                    "id": s.get("id"), "type": s.get("type"),
                    "start": s.get("start"), "dur": s.get("dur"),
                    "reveal": (s.get("data") or {}).get("reveal"),
                    "transition_out": (s.get("transition_out") or {}).get("kind"),
                    "summary": _scene_summary(s),
                } for s in fr.get("scenes", [])],
            })
    return frames


def load_frame_spec(comp: str, frame_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    info = _frame_index(comp).get(frame_id)
    if not info:
        raise KeyError(f"frame {frame_id!r} not found in composition {comp!r}")
    spec = json.loads(Path(info["spec_file"]).read_text(encoding="utf-8"))
    return spec, {"spec_file": str(info["spec_file"]), "i": info["i"]}


def save_frame_spec(spec_file: Path, spec: Dict[str, Any]) -> None:
    """Write the spec back, preserving all keys (lossless — unknown keys survive)."""
    Path(spec_file).write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")


def catalog() -> Dict[str, Any]:
    """The composer registry (scene_templates + data_schema + transitions + reveals) — the inspector's
    schema source, so the edit form is built from the same registry the gate validates against."""
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ patch helpers

def _set_path(obj: Any, path: str, value: Any) -> None:
    """Set a dotted path (list indices allowed) into an existing structure — e.g. 'data.items.0.to'."""
    keys = path.split(".")
    cur = obj
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur.setdefault(k, {})
    last = keys[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value


def _del_path(obj: Any, path: str) -> None:
    keys = path.split(".")
    cur = obj
    try:
        for k in keys[:-1]:
            cur = cur[int(k)] if isinstance(cur, list) else cur[k]
        last = keys[-1]
        if isinstance(cur, list):
            del cur[int(last)]
        elif last in cur:
            del cur[last]
    except (KeyError, IndexError, ValueError, TypeError):
        pass  # deleting an absent path is a no-op


def _apply_patch(scene: Dict[str, Any], patch: Dict[str, Any], deletes: Optional[List[str]]) -> None:
    for path, value in (patch or {}).items():
        _set_path(scene, path, value)
    for path in (deletes or []):
        _del_path(scene, path)


# ------------------------------------------------------------------ gate + build

def _gate_and_build(comp: str, spec_file: Path) -> Tuple[bool, str]:
    """Run the author.py gate on a spec file: validate + (re)build the frame HTML(s). Loud on drift."""
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(AUTHOR), "--spec", str(spec_file),
         "--out-dir", str(_frames_dir(comp))],
        cwd=str(BRIDGE), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def recompose_frame(comp: str, frame_id: str) -> Dict[str, Any]:
    """Re-gate + rebuild a frame's HTML from its current spec (no edit)."""
    info = _frame_index(comp).get(frame_id)
    if not info:
        raise KeyError(f"frame {frame_id!r} not found")
    ok, out = _gate_and_build(comp, info["spec_file"])
    return {"ok": ok, "output": out, "html": str(_frames_dir(comp) / f"{frame_id}.html")}


def _edit(comp: str, frame_id: str, mutate) -> Dict[str, Any]:
    """Shared transaction: load spec file, mutate the frame in place, save, gate+build; revert on reject."""
    info = _frame_index(comp).get(frame_id)
    if not info:
        raise KeyError(f"frame {frame_id!r} not found in composition {comp!r}")
    sf = info["spec_file"]
    original = sf.read_text(encoding="utf-8")
    spec = json.loads(original)
    fr = spec["frames"][info["i"]]
    mutate(fr)
    save_frame_spec(sf, spec)
    ok, out = _gate_and_build(comp, sf)
    if not ok:
        sf.write_text(original, encoding="utf-8")  # atomic revert — a rejected edit leaves nothing behind
        return {"applied": False, "errors": out}
    return {"applied": True, "gate": out, "html": str(_frames_dir(comp) / f"{frame_id}.html")}


def _find_scene(fr: Dict[str, Any], scene_id: str) -> Dict[str, Any]:
    sc = next((s for s in fr.get("scenes", []) if s.get("id") == scene_id), None)
    if sc is None:
        raise KeyError(f"scene {scene_id!r} not in frame {fr.get('id')!r}")
    return sc


def apply_scene_edit(comp: str, frame_id: str, scene_id: str,
                     patch: Optional[Dict[str, Any]] = None,
                     deletes: Optional[List[str]] = None) -> Dict[str, Any]:
    """Patch fields on one scene (dotted paths + deletes), then gate+recompose the frame. Reverts on
    gate failure so a bad edit never lands. Returns {applied, gate|errors, html}."""
    def mutate(fr):
        _apply_patch(_find_scene(fr, scene_id), patch, deletes)
    return _edit(comp, frame_id, mutate)


def add_scene(comp: str, frame_id: str, scene: Dict[str, Any], index: Optional[int] = None) -> Dict[str, Any]:
    """Insert a new scene into a frame (unlocks 'add media into a motion-only window'). `scene` must carry
    at least {id, type, start, dur, data}; the gate enforces the per-type required fields."""
    def mutate(fr):
        scenes = fr.setdefault("scenes", [])
        if any(s.get("id") == scene.get("id") for s in scenes):
            raise ValueError(f"scene id {scene.get('id')!r} already exists in frame {frame_id!r}")
        scenes.insert(len(scenes) if index is None else index, copy.deepcopy(scene))
    return _edit(comp, frame_id, mutate)


def remove_scene(comp: str, frame_id: str, scene_id: str) -> Dict[str, Any]:
    def mutate(fr):
        before = len(fr.get("scenes", []))
        fr["scenes"] = [s for s in fr.get("scenes", []) if s.get("id") != scene_id]
        if len(fr["scenes"]) == before:
            raise KeyError(f"scene {scene_id!r} not in frame {frame_id!r}")
    return _edit(comp, frame_id, mutate)


def retime_scene(comp: str, frame_id: str, scene_id: str,
                 start: Optional[float] = None, dur: Optional[float] = None) -> Dict[str, Any]:
    """Move/resize a scene on the frame timeline (plant-to-window). Leaves other scenes untouched."""
    def mutate(fr):
        sc = _find_scene(fr, scene_id)
        if start is not None:
            sc["start"] = float(start)
        if dur is not None:
            sc["dur"] = float(dur)
    return _edit(comp, frame_id, mutate)


# ------------------------------------------------------------------ within-frame transition planner

_SHIFT_TYPES = {"stat", "geo", "chart", "newshead", "timeline", "comparison", "diagram", "code",
                "social_card", "document", "gallery", "carousel", "collage"}


def beat_boundary_planner(comp: str, frame_id: str, apply: bool = False) -> Dict[str, Any]:
    """Deterministic WITHIN-FRAME seam planner: assign transition_out defaults between consecutive scenes
    by class — same block type in a row => crossfade (soft, related); a type change => a stronger seam
    (scale_out). The last scene in a frame gets none (frame-to-frame is the parked assemble-layer track).
    Returns the proposed transitions; only writes when apply=True."""
    spec, info = load_frame_spec(comp, frame_id)
    fr = spec["frames"][info["i"]]
    scenes = fr.get("scenes", [])
    proposals = []
    for i, s in enumerate(scenes[:-1]):
        nxt = scenes[i + 1]
        kind = "crossfade" if s.get("type") == nxt.get("type") else "scale_out"
        proposals.append({"scene_id": s.get("id"), "kind": kind, "dur": 0.6,
                          "current": (s.get("transition_out") or {}).get("kind")})
    if not apply:
        return {"applied": False, "proposals": proposals}

    def mutate(frame):
        by_id = {s.get("id"): s for s in frame.get("scenes", [])}
        for p in proposals:
            by_id[p["scene_id"]]["transition_out"] = {"kind": p["kind"], "dur": p["dur"]}
    res = _edit(comp, frame_id, mutate)
    res["proposals"] = proposals
    return res


# ------------------------------------------------------------------ note edit (Phase 2: comment → agent → gate)
# The open-ended half: a human note ("weave these photos in", "apply @reveal:scramble to @s2, dip to
# black after") is turned by an LLM into an ORDERED LIST OF OPS over the same engine primitives, then
# gated by author.py. This is the compose-first authoring path re-run on ONE frame with an edit note —
# draft → validate → accept. The LLM only PROPOSES; the gate decides. Injectable client for tests.

def _extract_json(text: str) -> Dict[str, Any]:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


_HF_MENTION_RE = re.compile(r"@(\w+(?::[\w-]+)?)")


def _resolve_hf_mentions(note: Optional[str], fr: Dict[str, Any], assets: Optional[List[str]]) -> str:
    """Expand @-grammar in a note into an explicit MENTIONS appendix the LLM can trust:
    @sN -> a scene id, @reveal:X / @transition:X -> a vocabulary entry, @assetN -> an asset path."""
    if not note:
        return ""
    ids = {s.get("id"): s for s in fr.get("scenes", [])}
    res = []
    for tok in dict.fromkeys(_HF_MENTION_RE.findall(note)):
        if tok in ids:
            res.append(f"  @{tok} = scene {tok} (type {ids[tok].get('type')})")
        elif tok.startswith("reveal:"):
            res.append(f"  @{tok} = reveal '{tok.split(':', 1)[1]}'")
        elif tok.startswith("transition:"):
            res.append(f"  @{tok} = transition '{tok.split(':', 1)[1]}'")
        elif assets and tok.startswith("asset"):
            try:
                res.append(f"  @{tok} = asset path {assets[int(tok[5:])]}")
            except (ValueError, IndexError):
                pass
    return ("MENTIONS:\n" + "\n".join(res) + "\n") if res else ""


_NOTE_GUIDE = (
    "You edit ONE frame of a HyperFrames video composition from a human note. A frame is a beat; its "
    "`scenes` are shots on ONE shared timeline (edit the shots, they re-render together). Output ONLY a "
    "JSON object {\"ops\":[...]} — an ORDERED list of edit operations. Op kinds:\n"
    "  {op:'patch', scene_id, patch:{<dotted path>:value,...}, deletes:[<dotted path>,...]}  "
    "# edit fields; paths like data.kicker, data.items.0.to, start, dur\n"
    "  {op:'add', scene:{id,type,start,dur,data:{...}}, index?}   "
    "# add a shot; type MUST be a known block and data MUST include its required fields\n"
    "  {op:'remove', scene_id}\n"
    "  {op:'retime', scene_id, start?, dur?}\n"
    "  {op:'transition', scene_id, kind, dur?}   # departing scene's within-frame transition_out\n"
    "Rules: keep edits minimal + faithful to the note; use ONLY block types, transition kinds, and reveal "
    "names from the registry below; a text block's motion is data.reveal. Timing is in seconds. Return "
    "{\"ops\":[]} if nothing should change."
)


def _catalog_brief(cat: Dict[str, Any]) -> str:
    lines = []
    for t, e in sorted(cat.get("scene_templates", {}).items()):
        keys = ", ".join((e.get("data_schema") or {}).keys())
        lines.append(f"  {t}: {(e.get('purpose', '') or '')[:70]}  data: {keys}")
    trans = ", ".join(k for k in cat.get("transitions", {}) if k != "_doc")
    revs = ", ".join(k for k in cat.get("reveals", {}) if k != "_doc")
    return "BLOCK TYPES (data fields):\n" + "\n".join(lines) + f"\nTRANSITIONS: {trans}\nREVEALS: {revs}"


def _apply_ops(fr: Dict[str, Any], ops: List[Dict[str, Any]]) -> None:
    """Apply an ordered edit plan to a frame in place, reusing the Phase-1 primitives."""
    scenes = fr.setdefault("scenes", [])

    def find(sid):
        s = next((x for x in scenes if x.get("id") == sid), None)
        if s is None:
            raise KeyError(f"scene {sid!r} not in frame")
        return s

    for op in ops:
        kind = op.get("op")
        if kind == "patch":
            _apply_patch(find(op["scene_id"]), op.get("patch"), op.get("deletes"))
        elif kind == "add":
            sc = op["scene"]
            if any(x.get("id") == sc.get("id") for x in scenes):
                raise ValueError(f"scene id {sc.get('id')!r} already exists")
            scenes.insert(len(scenes) if op.get("index") is None else int(op["index"]), copy.deepcopy(sc))
        elif kind == "remove":
            before = len(scenes)
            scenes[:] = [x for x in scenes if x.get("id") != op["scene_id"]]
            if len(scenes) == before:
                raise KeyError(f"scene {op['scene_id']!r} not found")
        elif kind == "retime":
            s = find(op["scene_id"])
            if op.get("start") is not None:
                s["start"] = float(op["start"])
            if op.get("dur") is not None:
                s["dur"] = float(op["dur"])
        elif kind == "transition":
            find(op["scene_id"])["transition_out"] = {"kind": op["kind"], "dur": float(op.get("dur", 0.6))}
        else:
            raise ValueError(f"unknown op {kind!r}")


def build_note_prompt(fr: Dict[str, Any], note: str, scene_id: Optional[str],
                      assets: Optional[List[str]], cat: Dict[str, Any]) -> Tuple[str, str]:
    """The (system, user) prompt for a note edit — spec + registry + resolved @mentions + note."""
    system = _NOTE_GUIDE + "\n\n" + _catalog_brief(cat)
    target = f"TARGET SCENE: {scene_id}\n" if scene_id else "TARGET: the whole frame\n"
    assets_block = ("AVAILABLE ASSETS (reference a path in scene data):\n"
                    + "\n".join(f"  [{i}] {a}" for i, a in enumerate(assets)) + "\n") if assets else ""
    prompt = (f"{target}FRAME SPEC:\n{json.dumps(fr, default=str)[:3500]}\n"
              f"{assets_block}{_resolve_hf_mentions(note, fr, assets)}HUMAN NOTE:\n{note}\n\nReturn the JSON ops now.")
    return system, prompt


async def revise_frame_note(comp: str, frame_id: str, note: str, scene_id: Optional[str] = None,
                            assets: Optional[List[str]] = None, client=None, retry: int = 1) -> Dict[str, Any]:
    """Turn a human note into gated edits on a frame. The LLM proposes an ops plan; author.py accepts or
    rejects (with one self-correct retry on rejection). Reverts on failure. Returns {applied, ops, errors}."""
    if client is None:  # lazy real client; tests inject a stub
        from nolan.config import load_config
        from nolan.llm import create_text_llm
        client = create_text_llm(load_config())
    spec, info = load_frame_spec(comp, frame_id)
    fr = spec["frames"][info["i"]]
    system, prompt = build_note_prompt(fr, note, scene_id, assets, catalog())
    last: Dict[str, Any] = {"applied": False, "ops": [], "errors": "no proposal"}
    for _attempt in range(max(0, int(retry)) + 1):
        raw = await client.generate(prompt, system_prompt=system)
        ops = _extract_json(raw).get("ops")
        if not ops:
            return {"applied": False, "ops": [], "errors": "the model proposed no ops", "raw": (raw or "")[:400]}
        try:
            res = _edit(comp, frame_id, lambda f: _apply_ops(f, ops))
        except (KeyError, ValueError, TypeError) as e:
            res = {"applied": False, "errors": f"op error: {e}"}
        res["ops"] = ops
        if res.get("applied"):
            return res
        last = res
        prompt += f"\n\nYour previous ops were REJECTED by the gate:\n{res.get('errors', '')}\nReturn corrected ops."
    return last


# ------------------------------------------------------------------ assets (picker target)
_IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif")
_VID_EXT = (".mp4", ".webm", ".mov", ".m4v")


def list_assets(comp: str) -> List[Dict[str, Any]]:
    """Assets already landed in <comp>/assets/ — the pick-from set for asset-typed fields."""
    root = _comp_dir(comp)
    adir = root / "assets"
    if not adir.is_dir():
        return []
    out = []
    for f in sorted(adir.rglob("*")):
        if f.is_file():
            ext = f.suffix.lower()
            out.append({"name": f.name, "path": f.relative_to(root).as_posix(),
                        "kind": "image" if ext in _IMG_EXT else "video" if ext in _VID_EXT else "file"})
    return out


def resolve_asset(comp: str, src: str) -> Dict[str, Any]:
    """Land an external/library asset into <comp>/assets/<basename> and return the comp-relative path to
    write into scene data (the 'get it into the project' step; use()/write avoids the /mnt/d chmod issue)."""
    s = Path(src)
    if not s.is_file():
        raise FileNotFoundError(f"asset source not found: {src}")
    adir = _comp_dir(comp) / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    (adir / s.name).write_bytes(s.read_bytes())
    return {"path": f"assets/{s.name}", "name": s.name}


def save_upload(comp: str, filename: str, data: bytes) -> Dict[str, Any]:
    adir = _comp_dir(comp) / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    safe = Path(filename).name
    (adir / safe).write_bytes(data)
    return {"path": f"assets/{safe}", "name": safe}


# ------------------------------------------------------------------ preview / render (npx scaffold)

def _scaffold_preview(comp: str, frame_id: str) -> Path:
    """Build a throwaway single-frame hyperframes project so `npx hyperframes snapshot|render` can target
    ONE frame in isolation (cross-platform: self-contained headless Chrome). Copies the frame HTML (+ any
    vendor dir a geo/diagram scene needs) so relative paths resolve."""
    fdir = _frames_dir(comp)
    html = fdir / f"{frame_id}.html"
    if not html.exists():
        recompose_frame(comp, frame_id)
    spec, info = load_frame_spec(comp, frame_id)
    dur = float(spec["frames"][info["i"]].get("dur", 5))
    pdir = _comp_dir(comp) / "compositions" / "_preview" / frame_id
    (pdir / "compositions" / "frames").mkdir(parents=True, exist_ok=True)
    (pdir / "compositions" / "frames" / f"{frame_id}.html").write_text(
        html.read_text(encoding="utf-8"), encoding="utf-8")
    vend = _comp_dir(comp) / "vendor"
    if not vend.is_dir():
        vend = BRIDGE / "vendor"
    if vend.is_dir():
        (pdir / "vendor").mkdir(exist_ok=True)
        for f in vend.glob("*"):
            if f.is_file():
                (pdir / "vendor" / f.name).write_bytes(f.read_bytes())
    assets = _comp_dir(comp) / "assets"          # so a frame referencing assets/<f> previews correctly
    if assets.is_dir():
        for f in assets.rglob("*"):
            if f.is_file():
                dest = pdir / f.relative_to(_comp_dir(comp))
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(f.read_bytes())
    # narrated preview: mount this frame's NOLAN voice as a root <audio> track (if a VO was bridged in).
    # frame_id starts with its 1-based section number (NN-*), matching audio_meta.json voices[].frame.
    audio_tag = ""
    meta_f = _comp_dir(comp) / "audio_meta.json"
    if meta_f.exists():
        try:
            meta = json.loads(meta_f.read_text(encoding="utf-8"))
            m = re.match(r"(\d+)", frame_id)
            fn = int(m.group(1)) if m else None
            voice = next((v for v in meta.get("voices", []) if v.get("frame") == fn), None)
            if voice and (pdir / voice["path"]).is_file():
                audio_tag = (f'<audio class="clip" src="{voice["path"]}" data-start="0" '
                             f'data-duration="{dur}" data-track-index="10" data-volume="1"></audio>')
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    (pdir / "hyperframes.json").write_text('{"paths":{"blocks":"compositions"}}', encoding="utf-8")
    (pdir / "index.html").write_text(
        '<!doctype html><html><head><meta charset="UTF-8"/>'
        '<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>'
        '<style>*{margin:0;padding:0;box-sizing:border-box}html,body{width:1920px;height:1080px;'
        'overflow:hidden;background:#000}#root{position:relative;width:1920px;height:1080px;'
        'overflow:hidden}.scene{position:absolute;inset:0}</style></head><body>'
        f'<div id="root" data-composition-id="main" data-start="0" data-duration="{dur}" '
        'data-width="1920" data-height="1080">'
        f'<div class="scene" data-composition-id="{frame_id}" '
        f'data-composition-src="compositions/frames/{frame_id}.html" '
        f'data-start="0" data-duration="{dur}" data-track-index="1"></div>'
        f'{audio_tag}</div>'
        '<script>window.__timelines=window.__timelines||{};var tl=gsap.timeline({paused:true});'
        f'tl.to({{}},{{duration:{dur}}},0);window.__timelines["main"]=tl;</script></body></html>',
        encoding="utf-8")
    return pdir


def snapshot_frame(comp: str, frame_id: str, at: Optional[float] = None) -> Dict[str, Any]:
    """Fast preview: a still of the frame at timecode `at` (default mid). Snapshot-first iteration."""
    spec, info = load_frame_spec(comp, frame_id)
    dur = float(spec["frames"][info["i"]].get("dur", 5))
    at = dur * 0.5 if at is None else float(at)
    pdir = _scaffold_preview(comp, frame_id)
    r = subprocess.run(["npx", "--yes", "hyperframes@latest", "snapshot", str(pdir),
                        "--at", f"{at:g}", "--no-end", "--describe", "false"],
                       cwd=str(pdir), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       shell=(os.name == "nt"))  # Windows: `npx` is npx.cmd -> needs a shell, else WinError 2
    snaps = sorted((pdir / "snapshots").glob("frame-*.png")) if (pdir / "snapshots").is_dir() else []
    return {"ok": r.returncode == 0 and bool(snaps),
            "png": str(snaps[0]) if snaps else None,
            "at": at, "output": (r.stdout + r.stderr).strip()[-800:]}


def render_frame(comp: str, frame_id: str, out: Optional[str] = None) -> Dict[str, Any]:
    """Full-frame render (the whole beat clip) — the on-demand step after snapshot iteration."""
    pdir = _scaffold_preview(comp, frame_id)
    outp = out or str(_frames_dir(comp) / f"{frame_id}.preview.mp4")
    r = subprocess.run(["npx", "--yes", "hyperframes@latest", "render", str(pdir),
                        "--output", outp],
                       cwd=str(pdir), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       shell=(os.name == "nt"))  # Windows: `npx` is npx.cmd -> needs a shell, else WinError 2
    return {"ok": r.returncode == 0 and Path(outp).exists(),
            "mp4": outp if Path(outp).exists() else None,
            "output": (r.stdout + r.stderr).strip()[-800:]}
