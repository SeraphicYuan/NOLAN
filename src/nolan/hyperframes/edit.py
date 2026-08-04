"""Composer-native scene-edit engine (Phase 1: direct/mechanical edits).

The unit of EDIT is a scene (a shot inside a frame); the unit of RE-RENDER is the frame (its scenes
share one merged GSAP timeline). So an edit patches ONE scene in a per-frame spec, re-gates the whole
frame through author.py (validate + compose -> frame HTML), and previews/renders that one frame.

Cross-platform notes: the gate (author.py) runs under this process's own python (sys.executable), so it
works Windows-side (the hub) and in WSL (tests). Previews/renders shell out to `npx hyperframes` on a
throwaway single-frame scaffold (self-contained headless Chrome), which also works in both.
"""
from __future__ import annotations

import contextlib
import copy
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[3]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
AUTHOR = BRIDGE / "author.py"
CATALOG_PATH = BRIDGE / "catalog.json"
LAB_VIDEOS = REPO / "render-service" / "_lab_hyperframes" / "videos"
PROJECTS = REPO / "projects"
THEMES = REPO / "themes"

_ROOTS = [("lab", LAB_VIDEOS), ("project", PROJECTS)]


def theme_exists(theme: Optional[str]) -> bool:
    return bool(theme) and (THEMES / str(theme) / "tokens.css").exists()


def list_themes() -> List[Dict[str, Any]]:
    """The selectable NOLAN themes (dirs under themes/ with a tokens.css), with mood/bestFor if present."""
    out = []
    for d in sorted(p for p in THEMES.iterdir() if p.is_dir()) if THEMES.is_dir() else []:
        if not (d / "tokens.css").exists():
            continue
        meta = {}
        tj = d / "theme.json"
        if tj.exists():
            try:
                meta = json.loads(tj.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        out.append({"id": d.name, "name": meta.get("name", d.name),
                    "mood": meta.get("mood", ""), "bestFor": meta.get("bestFor", "")})
    return out


def suggest_theme(text: str, top: int = 3) -> List[Dict[str, Any]]:
    """Deterministic, explainable theme ranking for a script (themes/scripts/select_theme.py --json).
    Returns [{id, score, why?}, …]; [] if the selector is unavailable (caller falls back to a default)."""
    script = THEMES / "scripts" / "select_theme.py"
    if not (script.exists() and (text or "").strip()):
        return []
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", str(script), text[:4000], "--json", "--top", str(top)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        return (json.loads(r.stdout) or {}).get("ranked", []) if r.returncode == 0 else []
    except Exception:
        return []


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
                   voiceover: bool = False, asset_density: str = "balanced",
                   theme: Optional[str] = None, motion: Optional[str] = None,
                   key_assets: bool = False, block_variety: Optional[str] = None) -> str:
    """The task brief the HF authoring agent reads to author a new essay (written to .hf_kickoff.md)."""
    rel = f"videos/{slug}"
    comp_rel = f"render-service/_lab_hyperframes/{rel}"
    bridge_rel = "render-service/_lab_hyperframes/bridge"
    style_line = f"\n- **Style:** {style}" if style else ""
    theme_line = (f"\n- **Theme (`{theme}`) — colours are automatic, LAYOUT is yours:** this essay renders in the "
                  f"`{theme}` theme (set in `{rel}/hyperframes.json`; `author.py` applies its tokens on every "
                  f"compose/recompose — do NOT hand-pick colours). But the theme also declares a COMPOSITION DIALECT "
                  f"(the macro-layouts it belongs in) and each block offers layout VARIANTS within it — author IN "
                  f"that dialect. See the composition-dialect brief below." if theme else "")
    try:                                                # the theme's composition dialect + sanctioned variant menu
        from nolan.hyperframes.layout_brief import theme_layout_brief
        theme_brief_txt = theme_layout_brief(theme) if theme else ""
    except Exception:
        theme_brief_txt = ""
    theme_section = ("\n\n---\n" + theme_brief_txt) if theme_brief_txt else ""
    try:                                                # the project's SOURCED data (datasets + documents) to bind
        from nolan.hyperframes.data_brief import data_brief
        data_brief_txt = data_brief(slug)
    except Exception:
        data_brief_txt = ""
    data_section = ("\n\n---\n" + data_brief_txt) if data_brief_txt else ""
    try:                                                # the style contract: craft targets + the full block palette
        from nolan.style_contract import StyleContract, authoring_brief
        dials = {"asset_density": asset_density}
        if motion:
            dials["video_share"] = motion
        if block_variety:
            dials["block_variety"] = block_variety
        contract_txt = authoring_brief(StyleContract.resolve("essay", **dials))
    except Exception:
        contract_txt = ""
    contract_section = ("\n\n---\n## STYLE CONTRACT — author to these targets, then lint & revise\n\n"
                        + contract_txt) if contract_txt else ""
    finish_line = (
        f"\n- **Anchor every scene:** give each scene an `anchor` — the distinctive SPOKEN phrase it illustrates "
        f"(the narrator's words, e.g. \"sixty-one thousand\", NOT on-screen typography like \"61,000\") — so the "
        f"aligner can land it on the word. Without anchors the sync step falls back to proportional spacing. "
        f"PREVIEW the implied windows in ~2s WITHOUT rendering: `python -X utf8 -m nolan.hyperframes.sync {comp_rel} "
        f"--report` prints every scene's window + SHORT/LONG/UNRESOLVED flags — re-space anchors until each reads, "
        f"then finish (it does NOT touch the specs)."
        f"\n- **Coverage check (plan-time):** `python -X utf8 -m nolan.acquire.coverage --comp {slug}` lists the named "
        f"subjects the narration references and flags any the library/pool can't depict — fix a corpus gap (a "
        f"named work you reference but haven't grounded) BEFORE authoring, not after."
        f"\n- **Finish — ONE idempotent command:** `python -X utf8 -m nolan.hyperframes.finish {comp_rel}` "
        f"(or `nolan hf-finish {slug}`) runs the whole DAG in the correct order and fails LOUD on the first broken "
        f"step: sync-durations → word-sync (force-align the VO + place each scene, firing its highlight on the SPOKEN "
        f"word) → recompose every frame in the theme → sound (bgm + sfx bed) → captions → assemble-index → "
        f"assemble_media (injects `ground:{{\"kind\":\"video\"}}` clips + a PRE-RENDER freeze-heal) → **STYLE GATE** → "
        f"render → hf_qa + style-lint. Re-run it after ANY spec edit (idempotent). Use `--no-render` to assemble + "
        f"preview first; copy video-ground / comparison-video clips into `{rel}/assets/` before running it."
        f"\n- **The STYLE GATE is HARD and runs BEFORE the render.** finish reads your specs (~1s) and REFUSES to "
        f"render while any contract GATE fails — so lint yourself first (command below) and revise until it passes, "
        f"rather than discovering it after a 20-minute render. Do NOT set `HF_ALLOW_STYLE=1` to get past it; that "
        f"escape hatch is the human's, not yours."
        f"\n- **QA + lint (draft → verify → revise):** `python -X utf8 -m nolan.hf_qa {comp_rel}` (freeze/audio) AND "
        f"`python -X utf8 -m nolan.style_contract {comp_rel} --dial asset_density={asset_density}"
        + (f" --dial video_share={motion}" if motion else "")
        + (f" --dial block_variety={block_variety}" if block_variety else "") + "` — fix every failing "
        f"GATE and QA fail, then re-render.")
    vo_line = (
        f"\n- **Voice — NOLAN-PROVIDED (do NOT synthesize a new voice):** the cloned voiceover is already "
        f"bridged into `{rel}/audio_meta.json` + `{rel}/assets/voice/0N.wav` (one wav per script section). "
        f"Author **exactly one frame per section** (frame N ↔ section N, in order). SKIP `audio.mjs generate` — "
        f"instead run `node audio.mjs sync-durations` to set each frame's duration FROM the VO (narration owns "
        f"duration), then `assemble-index` + `hyperframes render`; the narration mounts automatically as the "
        f"root voice track (data-track-index 10). Time within-frame reveals to the narration by ear."
        if voiceover else "")
    hero_line = (
        f"\n  The TOP of `asset-descriptions.md` is a **KEY-ASSETS HERO POOL** — the specific, NAMED things the essay "
        f"is ABOUT (real logos, portraits, the actual works/charts; some as bg-removed cutouts), each with its "
        f"narrative role + the spoken phrases where it fits. **Prefer a hero at the beat it belongs to — but YOU "
        f"decide where and whether:** use each hero where it best serves the story (usually ONCE, at its reveal or "
        f"first substantive mention), NOT mechanically at every occurrence of its name; a hero that doesn't earn a "
        f"frame stays unused. General b-roll follows below the heroes."
        if key_assets else "")
    if pool or key_assets:
        assets_line = (
            f"- **Assets — ASSET-BACKED:** real assets are being acquired into `{rel}/capture/` and listed in "
            f"`{rel}/capture/extracted/asset-descriptions.md` (the ONLY asset menu). SELECT `asset_candidates` from it "
            f"for image beats (collage / gallery / newshead / timeline / comparison); invent typography / diagram / "
            f"data-viz where no real asset fits. Resolve BGM/SFX via `/media-use`.{hero_line}"
            f"\n  **Read the menu's TAGS — they are constraints, not decoration.** `[NNNp — LOW-RES]` on a clip means "
            f"it was pulled from an archival/documentary source at well under 1080p: spend it as a DIMMED GROUND "
            f"behind type (scrimmed, slow push), never full-bleed as hero footage, where the softness reads. "
            f"`[copyrighted — short referenced excerpt only]` means the clip is a documentary/news reference: use it "
            f"BRIEFLY and in service of the point being made, prefer a copyright-free asset where either would work, "
            f"and never build a whole beat out of another channel's footage.")
    else:
        assets_line = (f"- **Assets:** no sourced pool (legacy invent-only mode) — invent per scene. Resolve "
                       f"BGM/SFX/images/logos via `/media-use`; land them in `{rel}/assets/`.")
    return f"""# New HyperFrames essay — kickoff (`{slug}`)

Author an **asset-backed video essay** from the source text, using the `/hf-author` authoring skill in
**NOLAN compose-first mode — the hybrid pipeline (the required default here)**. You are the orchestrator;
run its steps in order and pass each gate.

- **Project dir:** `{rel}/` (already scaffolded; the script is in `SOURCE.md`).
- **Input:** `{rel}/SOURCE.md` — the topic/script to explain.
- **Output:** composed frames at `{rel}/compositions/frames/NN-*.html` (+ `.spec.json`) and `{rel}/index.html`
  — that is what makes this composition appear on the hub's `/hyperframes` edit page.
{assets_line}{vo_line}
- **Plan blocks GLOBALLY first (don't make workers own the whole-video contract):** block distribution,
  grounding %, and adjacency are GLOBAL — a per-frame worker can't satisfy them alone. So propose per-beat
  candidate blocks (which templates fit each beat's content, best-first), then run
  `python -X utf8 -m nolan.hyperframes.block_plan <beats.json>` to get a contract-satisfying skeleton (block
  + grounded per scene). Dispatch workers WITH that assignment so they author only copy/reveals within it.
- **Pipeline — HYBRID / compose-first (required):** at Step 5, dispatch `sub-agents/compose-first-frame-worker.md`
  (NOT the stock `frame-worker.md`) with `BRIDGE_DIR=render-service/_lab_hyperframes/bridge/`. Express each Scene
  with a `bridge/catalog.json` composer template (stat · statement · geo · timeline · newshead · collage · diagram ·
  comparison · gallery · carousel · chart · linedraw · … + the `reveal`/`transition` vocabularies) and build it
  deterministically through the `author.py` gate; hand-author a bespoke `raw` / native-HF scene ONLY where no
  template fits.{style_line}{theme_line}{finish_line}

When the frames are composed, tell the user the composition id is **`{slug}`** — they'll refine it per-scene on `/hyperframes`.{data_section}{theme_section}{contract_section}
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
              voiceover: Optional[str] = None, asset_density: str = "balanced",
              theme: Optional[str] = None, motion: Optional[str] = None,
              gen_style: Optional[str] = None, key_assets: str = "curated",
              block_variety: Optional[str] = None) -> Dict[str, Any]:
    """Scaffold a new HyperFrames essay project under the lab videos root + write a kickoff brief for the
    HF authoring agent. Returns {comp, dir, prompt, acquire_pool, key_assets}; the caller runs the asset
    stages (key-assets heroes, then the b-roll pool) and dispatches `prompt` to a tmux agent. Shows up in
    /hyperframes once frames exist.

    key_assets: "curated" (default) builds the hero PULL-LIST at launch, human collects on /keyassets;
    "auto" collects immediately; "off" no heroes (pool-only). Heroes are OFFERED to the author (heroes-first
    in the menu, agent decides where/whether to use them), never mechanically placed.

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
    hf = {"paths": {"blocks": "compositions"}}          # record theme (so author.py applies it) + gen_style
    if theme and theme_exists(theme):
        hf["theme"] = theme
    if gen_style:                                       # explicit ComfyUI gen style; else pool.py derives from theme
        hf["gen_style"] = gen_style
    # persist the dials the author is BRIEFED to, so hf-finish's style gate scores the essay against the
    # same targets (it used to lint every essay at the preset defaults while the brief said `dense`)
    dials = {"asset_density": asset_density, **({"video_share": motion} if motion else {}),
             **({"block_variety": block_variety} if block_variety else {})}
    hf["style_dials"] = dials
    if len(hf) > 1:
        (pdir / "hyperframes.json").write_text(json.dumps(hf), encoding="utf-8")
    (pdir / ".hf_kickoff.md").write_text(
        _kickoff_brief(slug, style, acquire_pool, voiceover=bool(voiceover), asset_density=asset_density,
                       theme=(theme if theme and theme_exists(theme) else None), motion=motion,
                       key_assets=(key_assets != "off"), block_variety=block_variety),
        encoding="utf-8")
    prompt = (f"New HyperFrames essay: read render-service/_lab_hyperframes/videos/{slug}/.hf_kickoff.md and execute "
              f"it — author an asset-backed video essay from that project's SOURCE.md into its compositions/frames/ "
              f"using the /hf-author authoring skill in NOLAN compose-first (hybrid) mode. Report the "
              f"composition id '{slug}' when done.")
    res = {"comp": slug, "dir": str(pdir), "prompt": prompt,
           "acquire_pool": bool(acquire_pool), "key_assets": key_assets}
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


def ensure_storyboard(comp: str) -> Path:
    """Guarantee STORYBOARD.md exists before finish. audio.mjs (sync-durations/bgm/sfx), captions.mjs,
    and assemble-index.mjs all HARD-require it — its `format` frontmatter drives the canvas and the
    per-frame sections drive music/duration. new_essay scaffolds SOURCE.md but NOT this, so a cold
    first finish used to hard-fail here (homer POST_MORTEM ③). If missing, synthesize it from the
    composed frames + audio_meta + the SOURCE.md sections. IDEMPOTENT — never overwrites a hand-authored one."""
    from nolan.script import parse_script_sections
    pdir = _project_dir(comp)
    sb = pdir / "STORYBOARD.md"
    if sb.exists():
        return sb
    frames = list_frames(comp)
    fmt = "1920x1080"
    for fid in frames:                                   # canvas format from a frame spec, else landscape
        try:
            spec = json.loads((_frames_dir(comp) / f"{fid}.spec.json").read_text(encoding="utf-8"))
            f = spec.get("format") or (spec.get("frames") or [{}])[0].get("format")
            if f:
                fmt = str(f)
                break
        except Exception:
            continue
    voices = []                                          # durations + voice files (narration owns duration)
    am = pdir / "audio_meta.json"
    if am.exists():
        try:
            voices = sorted(json.loads(am.read_text(encoding="utf-8")).get("voices", []),
                            key=lambda v: v.get("frame", 0))
        except Exception:
            voices = []
    src = _project_script(pdir)
    sections = parse_script_sections(src) if src else []
    title = (sections[0]["title"] if sections else comp) or comp
    arc = " → ".join(s.get("title", "") for s in sections[1:]) or title
    message = next((ln.strip() for ln in (src or "").splitlines()
                    if ln.strip() and not ln.lstrip().startswith("#")), title)
    theme = ""
    try:
        theme = json.loads((pdir / "hyperframes.json").read_text(encoding="utf-8")).get("theme", "")
    except Exception:
        pass
    music = ("dark, cinematic, restrained strings — a low, elegiac underscore" if "dark" in (theme or "")
             else "cinematic, understated score that follows the narration")
    out = ["---", f"format: {fmt}", f"message: {message}", f"arc: {arc}", f"music: {music}", "---", ""]
    for i, fr in enumerate(frames):
        fid = fr.get("id") if isinstance(fr, dict) else fr    # list_frames returns dicts, not id strings
        dur = voices[i].get("duration_s") if i < len(voices) else None
        vfile = (voices[i].get("file") if i < len(voices) else None) or f"assets/voice/{i + 1:02d}.wav"
        sec = sections[i] if i < len(sections) else {}
        out += [f"## Frame {i + 1} — {sec.get('title') or fid}",
                f"- src: compositions/frames/{fid}.html",
                f"- duration: {dur if dur is not None else ''}s",
                f"- voiceover: {vfile}", "", (sec.get("body") or "").strip(), ""]
    sb.write_text("\n".join(out), encoding="utf-8")
    return sb


# How much of the derived NEED list should be video, per video_share dial. The need list used to be
# dial-BLIND: asked for a `heavy` essay it still derived 24/24 image needs (measured), so the pool came
# back all stills and the author could not reach the video_share gate however well they authored — a gate
# the pipeline cannot satisfy is worse than no gate. The dial now reaches the acquisition that feeds it.
_VIDEO_NEED_SHARE = {"none": 0.0, "light": 0.2, "balanced": 0.3, "heavy": 0.45}


def _parse_need_items(raw: str, strict: bool = False) -> Optional[List[Dict[str, Any]]]:
    """The need array out of an LLM reply. `strict=True` returns None instead of salvaging, so the
    caller can retry the generation — salvage is the LAST resort, not the first.

    A whole 24-need plan used to be lost to one bad character — observed live: an unescaped quote at
    char 10590 raised JSONDecodeError and took the entire acquisition down with it. The array is a list
    of independent objects, so a malformed one should cost that ONE need, not the plan. Strict parse
    first (the normal path); on failure, scan brace-balanced top-level objects and keep each that parses.
    """
    i, j = raw.find("["), raw.rfind("]")
    if not (0 <= i < j):
        return [] if not strict else None
    body = raw[i:j + 1]
    try:
        items = json.loads(body)
        return [x for x in items if isinstance(x, dict)]
    except json.JSONDecodeError:
        if strict:
            return None                                    # caller decides: retry the generation
    out, depth, start, in_str, esc = [], 0, None, False, False
    for pos, ch in enumerate(body):
        if in_str:
            in_str, esc = (in_str and not (ch == '"' and not esc)), (ch == "\\" and not esc)
            continue
        if ch == '"':
            in_str, esc = True, False
        elif ch == "{":
            if depth == 0:
                start = pos
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    o = json.loads(body[start:pos + 1])
                    if isinstance(o, dict):
                        out.append(o)
                except json.JSONDecodeError:
                    pass                                  # this ONE need is malformed — drop it, keep going
                start = None
    print(f"  ⚠ asset-need JSON was malformed — salvaged {len(out)} need(s) object-by-object", flush=True)
    return out


async def derive_asset_needs(script: str, client, k: int = 24,
                             video_share: Optional[str] = None) -> List[Dict[str, Any]]:
    """LLM: an essay script -> a `needs` list for the pool bridge, with QUERY-VARIANT EXPANSION.

    Each need carries several distinct stock-search phrasings (`queries`) so the bridge casts a wide
    net (multi-query retrieval — recall is the bottleneck in stock search), an `evocative` flag that
    routes abstract subjects through the evoke_broll metaphor super-search, and a `gen_prompt` used
    for krea2 gap-fill when stock finds nothing. `query` (the plain phrasing) stays for back-compat.

    `video_share` is the essay's motion dial — it sets a FLOOR on how many needs must be video, so the
    pool can actually supply the footage the style contract will demand."""
    vshare = _VIDEO_NEED_SHARE.get((video_share or "").lower(), 0.0)
    want_video = int(round(k * vshare))
    video_rule = ((f"MOTION QUOTA — this essay is dialled `{video_share}`: AT LEAST {want_video} of the "
                   f"{k} needs MUST have \"media_type\":\"video\". Pick them where footage genuinely beats a "
                   "still — a process in motion, a place you move through, archival newsreel/documentary of "
                   "an event, machinery or crowds working, anything whose MOVEMENT is the point. Do not pad "
                   "the quota with subjects that read better as a photograph. ")
                  if want_video else "")
    system = ("You plan VISUAL ASSET needs for a video essay. From the script, list the visual subjects worth "
              "gathering — people, places, objects, events, archival footage, and abstract themes. Aim for ONE need "
              "per BEAT/claim so EVERY beat can be visually grounded — a multi-minute essay wants many needs "
              "(roughly one per 15-25 spoken words), NOT a handful. For EACH, give several DISTINCT stock-search "
              "phrasings so we cast a wide net, mark whether it is abstract, and give a fallback generation prompt. "
              "For a CONCRETE NAMED subject (a specific person, place, org, work, or event), inject the subject's "
              "real-world IDENTIFIERS into the phrasings — its role/affiliation/era/place — so the search "
              "disambiguates (e.g. 'Cecil Rhodes' -> 'Cecil Rhodes De Beers founder', 'Cecil John Rhodes 1890s "
              "portrait'; not a bare terse name that pulls a wrong-domain hit). For an ABSTRACT subject keep the "
              "phrasings evocative (mood/metaphor). "
              f"Return ONLY a JSON array of up to {k} items, each: "
              "{\"id\":\"a1\", \"query\":\"plain 3-6 word stock search\", "
              "\"queries\":[\"3-5 distinct SHORT phrasings (3-7 words each) incl. the plain one — for a named "
              "subject vary by its identifiers (role/affiliation/era) + name variants; for an abstract one by "
              "synonym/mood/shot\"], \"media_type\":\"image\" or \"video\", \"n\":3, "
              "\"evocative\": true if the subject is an ABSTRACT idea/emotion/theme (not a concrete photographable "
              "thing) else false, \"category\":\"art\" or \"archival\" or \"general\" "
              "(art = painting/fine-art/illustration; archival = historical photos or footage; "
              "general = modern photos/video — people, places, nature, objects), "
              "\"gen_prompt\":\"one cinematic image-generation prompt for this subject\"}. "
              + video_rule +
              "Otherwise prefer image; choose video for motion-critical subjects AND archival/historical FOOTAGE "
              "(newsreel, documentary, period film) so archival-video sources are used. No prose, no code fences.")
    # RETRY-then-salvage. Malformed JSON is recurrent here (a long array of prose-heavy objects), and
    # salvage costs whole needs: one live run lost 11 of 24 because a desync mid-array made everything
    # after it unrecoverable. A fresh generation is far cheaper than a 46%-thinner asset plan, so ask
    # again before falling back to picking the wreckage apart.
    items = None
    for attempt in range(2):
        raw = (await client.generate((script or "")[:6000], system_prompt=system)).strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        items = _parse_need_items(raw, strict=True)
        if items:
            break
        if attempt == 0:
            print("  ⚠ asset-need JSON was malformed — regenerating once before salvaging", flush=True)
    if not items:
        items = _parse_need_items(raw) or []
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
    if want_video:                       # the quota is a PROMPT instruction, so say so when it's missed
        got = sum(1 for n_ in out if n_["media_type"] == "video")
        if got < want_video:
            print(f"  ⚠ motion quota: asked for >={want_video} video need(s) of {k} (video_share="
                  f"{video_share}), the planner returned {got} — the pool will lean on clip-search over "
                  f"the image needs to reach the motion gate", flush=True)
    return out


def run_pool(comp: str, needs: List[Dict[str, Any]], per: int = 8,
             gen: bool = True, cull: bool = True) -> Dict[str, Any]:
    """Run the NOLAN->HF asset bridge (bridge/pool.py): ACQUIRE -> SCORE+CAPTION -> INVENTORY into <project>/capture/.
    Blocking (fan-out + captioning takes minutes) — call from a background job / thread. `gen` runs krea2/ComfyUI
    gap-fill for thin/evocative beats; `cull` runs the VLM usability floor (drop junk)."""
    if not needs:
        raise ValueError("no asset needs to acquire")
    pdir = _project_dir(comp)
    needs_file = pdir / "capture" / "needs.json"
    needs_file.parent.mkdir(parents=True, exist_ok=True)
    needs_file.write_text(json.dumps(needs, ensure_ascii=False, indent=2), encoding="utf-8")
    cmd = [sys.executable, "-X", "utf8", str(BRIDGE / "pool.py"),
           "--needs", str(needs_file), "--project", str(pdir), "--per", str(per)]
    if not gen:
        cmd.append("--no-gen")
    if not cull:
        cmd.append("--no-vlm-cull")
    r = subprocess.run(cmd, cwd=str(BRIDGE), capture_output=True, text=True, encoding="utf-8", errors="replace")
    pool_json = pdir / "pool.json"
    pool = json.loads(pool_json.read_text(encoding="utf-8")) if pool_json.exists() else []
    return {"ok": r.returncode == 0, "count": len(pool), "needs": needs,
            "inventory": str(pdir / "capture" / "extracted" / "asset-descriptions.md"),
            "output": (r.stdout + r.stderr)[-1200:]}


def run_key_assets(comp: str, script: Optional[str] = None, mode: str = "curated",
                   stage: bool = True) -> Dict[str, Any]:
    """Run the key-assets HERO stage for an essay (mirrors run_pool; a PRE-acquisition, global pass).
    `mode`: 'curated' builds the reviewable pull-list only (human collects on /keyassets); 'auto' also
    collects the heroes; 'off' is a no-op. `stage` writes the HERO block into asset-descriptions.md — the
    launch flow passes stage=False so the b-roll pool (which rewrites that file) runs BETWEEN collect and
    stage, and stages last. Blocking (LLM + optional ~minutes collect) — call from a background thread.
    Heroes are OFFERED to the author (heroes-first in the menu, agent decides where/whether), never placed."""
    if mode == "off":
        return {"ok": True, "mode": "off", "skipped": True}
    import asyncio
    from datetime import date

    from nolan.config import load_config
    from nolan.keyassets import build_proposal, collect
    from nolan.keyassets.inventory import write_hero_section
    from nolan.keyassets.schema import KeyAssetsProposal
    from nolan.llm import create_text_llm
    pdir = _project_dir(comp)
    script = script or _project_script(pdir)
    if not (script or "").strip():
        return {"ok": False, "error": "no script for key-assets"}
    cfg = load_config()
    prop_path = pdir / "key_assets.proposal.json"
    prop = KeyAssetsProposal.load(prop_path)              # reuse a human-reviewed proposal if present (idempotent)
    if prop is None:                                      # decompose → enrich → consolidate → querygen
        prop = asyncio.run(build_proposal(script, create_text_llm(cfg), comp=comp))
        prop.generated = date.today().isoformat()
        prop.save(prop_path)
    collected = 0
    if mode == "auto":
        collected = collect(cfg, pdir, prop).get("collected", 0)
        if stage:
            write_hero_section(pdir)                      # prepend heroes onto the author's menu (idempotent)
    return {"ok": True, "mode": mode, "entities": len(prop.entities), "collected": collected,
            "proposal": str(prop_path)}


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


def frame_video_path(comp: str, frame_id: str) -> Optional[Path]:
    """The newest per-frame rendered video, under EITHER name: `<id>.preview.mp4` (the on-demand
    render_frame path the edit page historically served) OR `<id>.clip.mp4` (what the incremental
    render emits). Unifying the two means an incremental render is visible on the edit page with no
    copy step. Returns None if neither exists."""
    fdir = _frames_dir(comp)
    cands = [p for p in (fdir / f"{frame_id}.preview.mp4", fdir / f"{frame_id}.clip.mp4") if p.exists()]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def list_frames(comp: str) -> List[Dict[str, Any]]:
    """The frame -> scene tree for a composition (the /hyperframes page payload)."""
    fdir = _frames_dir(comp)
    frames = []
    for sf in sorted(fdir.glob("*.spec.json")):
        spec = json.loads(sf.read_text(encoding="utf-8"))
        sf_mtime = sf.stat().st_mtime
        for fr in spec.get("frames", []):
            vid = frame_video_path(comp, fr["id"])
            ftr = fr.get("transition_out") or {}                # FRAME-level clip transition INTO the next frame
            frames.append({
                "id": fr["id"], "dur": fr.get("dur"), "spec_file": sf.name,
                "html_exists": (fdir / f'{fr["id"]}.html').exists(),
                "preview_mp4": vid is not None,
                "clip_transition": ftr.get("kind"), "clip_transition_dur": ftr.get("dur"),
                # the spec was edited after the last render → the preview video is stale (a seek could mislead)
                "stale": bool(vid and sf_mtime > vid.stat().st_mtime),
                "scenes": [{
                    "id": s.get("id"), "type": s.get("type"),
                    "start": s.get("start"), "dur": s.get("dur"),
                    "reveal": (s.get("data") or {}).get("reveal"),
                    "transition_out": (s.get("transition_out") or {}).get("kind"),
                    "summary": _scene_summary(s),
                } for s in fr.get("scenes", [])],
            })
    return frames


# ---- layer map: a frame's timeline broken into semantic LANES (for the layer-lanes view) --------------
_LANE_OF = {"ground": "bg", "backdrop": "bg", "image": "overlay", "source": "overlay",
            "subjects": "overlay", "avatar": "overlay", "art": "overlay", "right": "overlay", "left": "overlay"}
_MEDIA_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".webm")
_TEXT_FIELDS = ("lines", "title", "headline", "text", "kicker", "name", "sub", "subtitle", "track", "code", "items")


def _media_src(v: Any) -> Optional[str]:
    """The media path a field value points to — a bare path, or a {src}/{kind,src} object — else None."""
    if isinstance(v, str) and v.lower().endswith(_MEDIA_EXT):
        return v
    if isinstance(v, dict) and isinstance(v.get("src"), str) and v["src"].lower().endswith(_MEDIA_EXT):
        return v["src"]
    return None


def frame_layers(comp: str, frame_id: str) -> Dict[str, Any]:
    """A frame's timeline as LANES (bg / overlay / text / fx), one element per asset / text / motion, each with
    its time window + a `target` = the inspector control it edits (a data-f field name, or 'reveal'/'transition').
    So clicking a lane chip can jump straight to the right control instead of hunting the scene form. Derived
    from the SPEC (fields = layers — the author's mental model), which stays correct as blocks evolve."""
    spec, info = load_frame_spec(comp, frame_id)
    fr = spec["frames"][info["i"]]
    cat = catalog().get("scene_templates", {})
    els: List[Dict[str, Any]] = []
    for sc in fr.get("scenes", []):
        sid, typ = sc.get("id"), sc.get("type")
        start, dur = round(float(sc.get("start", 0) or 0), 3), round(float(sc.get("dur", 0) or 0), 3)
        d = sc.get("data", {}) or {}
        schema = cat.get(typ, {}).get("data_schema", {})

        def add(lane, label, target, kind, thumb=None):
            els.append({"scene_id": sid, "scene_type": typ, "lane": lane, "start": start, "dur": dur,
                        "label": label, "target": target, "kind": kind, "thumb": thumb})

        for f, lane in _LANE_OF.items():                 # BACKGROUND + OVERLAY: media-valued fields, lane by role
            if f not in schema:
                continue
            v = d.get(f)
            if f == "subjects" and isinstance(v, list) and v:
                add("overlay", f"{len(v)} subject(s)", "subjects", "asset", _media_src(v[0]))
                continue
            src = _media_src(v)
            if src:
                lbl = ((f"{v['kind']} " if isinstance(v, dict) and v.get("kind") else "") + f).strip()
                add(lane, lbl, f, "asset", src)
        tf = next((f for f in _TEXT_FIELDS if f in schema), None)   # TEXT + its reveal motion
        if tf:
            add("text", (_scene_summary(sc) or typ)[:28], tf, "text", None)
            if d.get("reveal"):
                add("text", f"↳ {d['reveal']}", "reveal", "motion", None)
        tr = sc.get("transition_out") or {}                # FX: transition + a ground colour grade
        if tr.get("kind"):
            add("fx", f"→ {tr['kind']}", "transition", "motion", None)
        g = d.get("ground")
        if isinstance(g, dict) and g.get("grade"):
            add("fx", f"grade: {g['grade']}", "ground", "effect", None)
        if isinstance(g, dict) and g.get("treatments"):                       # effects umbrella: one chip per treatment
            for _t in g["treatments"]:
                _tid = _t if isinstance(_t, str) else (_t.get("id") if isinstance(_t, dict) else "?")
                add("fx", f"fx: {_tid}", "ground", "effect", None)
    return {"frame_id": frame_id, "dur": fr.get("dur"), "lanes": ["bg", "overlay", "text", "fx"], "elements": els}


def asset_scene_usage(comp: str) -> Dict[str, Any]:
    """Reverse index for the /pool HF by-scene view: which SCENES reference each pool asset FILE. Walks every
    frame spec's scenes, collecting media refs (ground / overlay / subjects / any nested {src}) normalized to
    the pool `file` key — a path under assets/ or capture/assets/, backslashes tolerated. Scene ids are
    globally unique (frame-prefixed, e.g. f02s05). Returns {by_file: {file: [scene_id,…]}, scene_order: […]}.
    HF has no such index natively (its pool groups by acquisition NEED, not by where an asset actually lands)."""
    def _norm(src: str) -> Optional[str]:
        s = src.replace("\\", "/").lstrip("/")
        for pre in ("capture/assets/", "assets/"):
            if s.startswith(pre):
                return s[len(pre):] or None
        return s or None

    def _collect(v: Any, out: set) -> None:
        m = _media_src(v)
        if m:
            out.add(m)
        if isinstance(v, dict):
            for vv in v.values():
                _collect(vv, out)
        elif isinstance(v, list):
            for vv in v:
                _collect(vv, out)

    by_file: Dict[str, List[str]] = {}
    order: List[str] = []
    for fr_meta in list_frames(comp):
        fid = fr_meta.get("id")
        try:
            spec, info = load_frame_spec(comp, fid)
        except Exception:
            continue
        for sc in spec["frames"][info["i"]].get("scenes", []):
            sid = sc.get("id")
            if not sid:
                continue
            order.append(sid)
            refs: set = set()
            _collect(sc.get("data", {}) or {}, refs)
            for src in refs:
                f = _norm(src)
                if f:
                    lst = by_file.setdefault(f, [])
                    if sid not in lst:
                        lst.append(sid)
    return {"by_file": by_file, "scene_order": order}


def frame_transcripts(comp: str, frame_id: str) -> Dict[str, str]:
    """Per-scene NARRATION text — the VO words whose timing overlaps each scene's window (from audio_meta's
    per-frame word timings; scene start/dur and the words are both frame-local). Lets the editor read what a
    scene actually SAYS at a glance. Returns {scene_id: text}; empty strings where there's no aligned VO."""
    spec, info = load_frame_spec(comp, frame_id)
    fr = spec["frames"][info["i"]]
    out = {sc.get("id"): "" for sc in fr.get("scenes", [])}
    mp = _comp_dir(comp) / "audio_meta.json"
    if not mp.exists():
        return out
    try:
        meta = json.loads(mp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return out
    m = re.match(r"(\d+)", str(frame_id))
    n = int(m.group(1)) if m else None
    voice = next((v for v in meta.get("voices", []) if str(v.get("frame")) == str(n)), None)
    words = [w for w in (voice or {}).get("words", []) if isinstance(w, dict) and w.get("start") is not None]
    for sc in fr.get("scenes", []):
        s = float(sc.get("start", 0) or 0)
        e = s + float(sc.get("dur", 0) or 0)
        toks = [(w.get("word") or w.get("text") or "") for w in words
                if w["start"] < e and (w.get("end") or w["start"]) > s]
        out[sc.get("id")] = " ".join(t for t in toks if t).strip()
    return out


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
    schema source, so the edit form is built from the same registry the gate validates against. The
    `effects` catalog is injected from nolan.effects.REGISTRY (single source — the Treatments control
    reads it, never a hand-listed copy)."""
    cat = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    try:
        from nolan.effects import REGISTRY as _FX, stocked_effects, bakeable as _bake
        _stocked = stocked_effects()                        # element plates actually present in _library/overlays
        cat["effects"] = {e.id: {"family": e.family, "purpose": e.purpose, "when_to_use": e.when_to_use,
                                 "method": e.method,
                                 "needs_plate": bool(e.plate) and e.plate not in _stocked,
                                 "stocked": (not e.plate) or (e.plate in _stocked),
                                 "bakeable": _bake(e),       # can be baked onto a pool asset (per-asset "treat" op)
                                 "css": e.css, "css_bg": e.css_bg, "blend": e.blend,   # for the live fx-modal preview
                                 "opacity": e.default_opacity, "plate": e.plate}
                          for e in _FX}
    except Exception:                                       # effects pkg missing → edit page still loads (no Treatments control)
        pass
    try:                                                    # clip-driven FRAME transitions (stocked kinds from the manifest)
        from nolan.hyperframes.transitions import load_transitions
        cat["clip_transitions"] = {t["kind"]: {"type": t["type"], "dur": t.get("dur", 1.0),
                                               "desc": t.get("desc") or t.get("when_to_use", "")}
                                   for t in load_transitions()}
    except Exception:
        pass
    return cat


# ------------------------------------------------------------------ patch helpers

_APPEND = "+"


def _set_path(obj: Any, path: str, value: Any) -> None:
    """Set a dotted path (list indices allowed) into an existing structure — e.g. 'data.items.0.to'.

    `+` as the final segment APPENDS to a list: `data.series.+`. "Add another bar / row / bullet" is one
    of the commonest notes a human writes, and without this the only expression of it was re-sending the
    whole array as one patch — which silently clobbers any concurrent edit to a sibling element.

    An out-of-range index RAISES rather than growing the list. Silent growth would turn a typo
    (`data.series.7` on a two-element list) into five nulls that validate and render as blanks, which is
    strictly worse than the IndexError it replaced — and the message names the fix."""
    keys = path.split(".")
    cur = obj
    for i, k in enumerate(keys[:-1]):
        if isinstance(cur, list):
            if k == _APPEND:
                raise ValueError(f"{path!r}: '+' may only be the LAST segment (it appends a value)")
            idx = int(k)
            if not -len(cur) <= idx < len(cur):
                raise IndexError(f"{path!r}: index {idx} is out of range for a {len(cur)}-item list "
                                 f"at {'.'.join(keys[:i]) or '<root>'}")
            cur = cur[idx]
        else:
            cur = cur.setdefault(k, {})
    last = keys[-1]
    if isinstance(cur, list):
        if last == _APPEND:
            cur.append(value)
            return
        idx = int(last)
        if not -len(cur) <= idx < len(cur):
            raise IndexError(f"{path!r}: index {idx} is out of range for a {len(cur)}-item list — "
                             f"use '{'.'.join(keys[:-1])}.+' to APPEND")
        cur[idx] = value
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
    """Run the author.py gate on a spec file: validate + (re)build the frame HTML(s). Loud on drift.

    A4: if a scene BINDS a dataset, materialize it first (mirror the finish DAG's resolve_datasets step) so
    the accepted/recomposed preview shows real numbers instead of an empty block — the finish path resolves
    before recompose, and this makes the incremental accept path agree. Cheap: only fires when a
    `data.dataset` is present, so non-data frames pay nothing beyond a spec read.
    """
    raw = spec_file.read_bytes()
    spec = json.loads(raw.decode("utf-8"))

    def _binds_dataset(sc):
        d = sc.get("data") or {}
        if d.get("dataset"):
            return True
        return sc.get("type") == "layout" and any((s or {}).get("dataset") for s in d.get("slots", []) or [])
    if any(_binds_dataset(sc) for fr in spec.get("frames", []) for sc in fr.get("scenes", [])):
        try:
            from nolan.data import resolve_datasets_in_spec
            if resolve_datasets_in_spec(spec, str(_project_dir(comp))):
                out = (json.dumps(spec, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                if b"\r\n" in raw:
                    out = out.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                spec_file.write_bytes(out)
        except Exception as e:                                    # a bad binding fails loud, as a gate error
            return False, f"dataset resolution failed: {type(e).__name__}: {e}"

    # …and the same for MATH, for the same reason. A `math` scene's pixels are a Manim clip mounted
    # as its video ground; recomposing the HTML alone leaves `data.ground` pointing at the clip the
    # PREVIOUS maths produced, so an edit to a formula or a scene program appeared to succeed and
    # changed nothing on screen. Verified before this existed: editing a derivation's final step
    # recomposed the frame and left the ground byte-identical.
    #
    # Affordable because the resolver is content-addressed: an untouched scene hashes to its
    # existing clip and returns in milliseconds. Only maths the author actually changed costs a
    # render — which is precisely what they asked for by changing it.
    if any(sc.get("type") == "math" for fr in spec.get("frames", []) for sc in fr.get("scenes", [])):
        try:
            from nolan.mathanim.resolve import resolve_math_spec
            resolve_math_spec(comp, spec_file)
        except Exception as e:                                    # bad maths fails loud, as a gate error
            return False, f"math resolution failed: {type(e).__name__}: {e}"
        spec = json.loads(spec_file.read_bytes().decode("utf-8"))  # re-read: the ground was stamped

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


def _edit(comp: str, frame_id: str, mutate, *, kind: str = "edit", scene_id: Optional[str] = None,
          summary: Optional[str] = None, actor: str = "human") -> Dict[str, Any]:
    """Shared transaction: load spec file, mutate the frame in place, save, gate+build; revert on reject.
    Records the outcome (applied|rejected + reason) to the activity feed."""
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
    label = summary or (f"{kind} {frame_id}" + (f"/{scene_id}" if scene_id else ""))
    if not ok:
        sf.write_text(original, encoding="utf-8")  # atomic revert — a rejected edit leaves nothing behind
        log_activity(comp, kind, label, actor=actor, frame_id=frame_id, scene_id=scene_id,
                     outcome="rejected", detail=out[-300:])
        return {"applied": False, "errors": out}
    log_activity(comp, kind, label, actor=actor, frame_id=frame_id, scene_id=scene_id, outcome="applied")
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
    return _edit(comp, frame_id, mutate, kind="edit", scene_id=scene_id,
                 summary=f"edit {scene_id}: {', '.join((patch or {}).keys()) or 'delete'}")


def add_scene(comp: str, frame_id: str, scene: Dict[str, Any], index: Optional[int] = None) -> Dict[str, Any]:
    """Insert a new scene into a frame (unlocks 'add media into a motion-only window'). `scene` must carry
    at least {id, type, start, dur, data}; the gate enforces the per-type required fields."""
    def mutate(fr):
        scenes = fr.setdefault("scenes", [])
        if any(s.get("id") == scene.get("id") for s in scenes):
            raise ValueError(f"scene id {scene.get('id')!r} already exists in frame {frame_id!r}")
        scenes.insert(len(scenes) if index is None else index, copy.deepcopy(scene))
    return _edit(comp, frame_id, mutate, kind="add", scene_id=scene.get("id"),
                 summary=f"add {scene.get('type')} {scene.get('id')}")


def remove_scene(comp: str, frame_id: str, scene_id: str) -> Dict[str, Any]:
    def mutate(fr):
        before = len(fr.get("scenes", []))
        fr["scenes"] = [s for s in fr.get("scenes", []) if s.get("id") != scene_id]
        if len(fr["scenes"]) == before:
            raise KeyError(f"scene {scene_id!r} not in frame {frame_id!r}")
    return _edit(comp, frame_id, mutate, kind="remove", scene_id=scene_id, summary=f"remove {scene_id}")


def retime_scene(comp: str, frame_id: str, scene_id: str,
                 start: Optional[float] = None, dur: Optional[float] = None) -> Dict[str, Any]:
    """Move/resize a scene on the frame timeline (plant-to-window). Leaves other scenes untouched.

    Returns a `timing` list when the change will NOT survive the next finish — see
    `retime_durability`. This is the path where the silent revert was actually found: the edit
    applies, the render honours it, and word-sync puts it back with nobody told.
    """
    def mutate(fr):
        sc = _find_scene(fr, scene_id)
        if start is not None:
            sc["start"] = float(start)
        if dur is not None:
            sc["dur"] = float(dur)
    before = copy.deepcopy(load_frame_spec(comp, frame_id)[0]["frames"][_frame_index(comp)[frame_id]["i"]])
    res = _edit(comp, frame_id, mutate, kind="retime", scene_id=scene_id, summary=f"retime {scene_id}")
    if res.get("applied"):
        after = load_frame_spec(comp, frame_id)[0]["frames"][_frame_index(comp)[frame_id]["i"]]
        notes = retime_durability(before, after)
        if notes:
            res["timing"] = notes
    return res


def set_frame_transition(comp: str, frame_id: str, kind: Optional[str], dur: float = 1.2) -> Dict[str, Any]:
    """Set (or clear, when `kind` is falsy) a FRAME-level clip transition INTO the next frame:
    frame.transition_out = {kind, dur}. This is the frame→frame matte/reveal WIPE spliced at the concat
    seam (nolan.hyperframes.transitions), NOT the within-frame GSAP transition_out on a scene. Gated
    against the stocked clip-transition registry (author.py); reverts on reject like any other edit."""
    def mutate(fr):
        if kind:
            fr["transition_out"] = {"kind": kind, "dur": float(dur)}
        else:
            fr.pop("transition_out", None)
    return _edit(comp, frame_id, mutate, kind="frame-transition",
                 summary=f"frame transition → {kind or 'none'}")


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


_HF_MENTION_RE = re.compile(r"@([\w-]+(?::[\w-]+)?)")   # base token allows '-' so stable slugs (@bg-s08n37) match


def resolve_mentions(text: Optional[str], fr: Optional[Dict[str, Any]] = None,
                     assets: Optional[List[str]] = None,
                     mentions: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    """Resolve @-tokens in `text` to explicit '@token = resolution' lines. PREFERS persisted structured
    bindings (`mentions`=[{token,type,ref,label}]) — captured when the human picked from the tray, so they
    never drift. Falls back to LEGACY resolution when a token has no binding: @sN -> scene, @reveal:/
    @transition: -> vocabulary, @assetN -> the Nth asset (POSITIONAL — may drift; flagged loudly). Shared by
    the batch kickoff and the LLM note-edit so both resolve identically."""
    if not text:
        return []
    bound = {(m.get("token") or "").lstrip("@"): m for m in (mentions or []) if m.get("token")}
    ids = {s.get("id"): s for s in (fr.get("scenes", []) if fr else [])}
    out: List[str] = []
    for tok in dict.fromkeys(_HF_MENTION_RE.findall(text)):
        if tok in bound:                                   # stable, pick-time binding (the good path)
            m = bound[tok]
            lbl = f"  ({m['label']})" if m.get("label") else ""
            out.append(f"@{tok} = {m.get('type', 'ref')} → {m.get('ref')}{lbl}")
        elif tok in ids:
            out.append(f"@{tok} = scene {tok} (type {ids[tok].get('type')})")
        elif tok.startswith("reveal:"):
            out.append(f"@{tok} = reveal '{tok.split(':', 1)[1]}'")
        elif tok.startswith("transition:"):
            out.append(f"@{tok} = transition '{tok.split(':', 1)[1]}'")
        elif assets and tok.startswith("asset") and tok[5:].isdigit():
            try:
                out.append(f"@{tok} = asset {assets[int(tok[5:])]}  ⚠ UNBOUND (positional — may drift)")
            except (ValueError, IndexError):
                out.append(f"@{tok} = ⚠ UNRESOLVED (positional index out of range)")
    return out


def _resolve_hf_mentions(note: Optional[str], fr: Dict[str, Any], assets: Optional[List[str]],
                         mentions: Optional[List[Dict[str, Any]]] = None) -> str:
    """MENTIONS appendix for the LLM note-edit prompt (thin wrapper over `resolve_mentions`)."""
    lines = resolve_mentions(note, fr, assets, mentions)
    return ("MENTIONS:\n" + "\n".join("  " + ln for ln in lines) + "\n") if lines else ""


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
            # A SCENE's transition_out is a within-frame GSAP seam. On the frame's LAST scene it emits
            # its tween at exactly `frame.dur`, so it plays for zero visible frames — a batch agent
            # composed a trial and found this before proposing it, which is the only reason it wasn't
            # shipped as an inert edit. The seam a human means when they say "the cut into the next
            # section is harsh" is the FRAME-level one, so refuse and name the op that does it.
            s = find(op["scene_id"])
            if scenes and scenes[-1] is s:
                kinds = []
                try:
                    from nolan.hyperframes.transitions import transition_kinds
                    kinds = sorted(transition_kinds())
                except Exception:
                    pass
                raise ValueError(
                    f"scene {op['scene_id']!r} is the LAST in its frame: a scene `transition_out` fires "
                    f"at the frame boundary and is invisible. Use {{'op':'frame_transition','kind':…}} "
                    f"for the frame→frame seam — and note it takes a STOCKED CLIP transition"
                    + (f" ({', '.join(kinds)})" if kinds else "")
                    + ", not a within-frame GSAP kind like 'crossfade'.")
            s["transition_out"] = {"kind": op["kind"], "dur": float(op.get("dur", 0.6))}
        elif kind == "frame_transition":
            # The FRAME→FRAME clip wipe (`frame.transition_out`), spliced net-zero at the concat seam.
            # It had no op at all, so the one thing a batch agent needed for a seam note was
            # unreachable from the ops grammar and the fix was "a one-liner you run yourself".
            fr["transition_out"] = {"kind": op["kind"], "dur": float(op.get("dur", 1.2))}
        else:
            raise ValueError(f"unknown op {kind!r}")


def build_note_prompt(fr: Dict[str, Any], note: str, scene_id: Optional[str],
                      assets: Optional[List[str]], cat: Dict[str, Any],
                      mentions: Optional[List[Dict[str, Any]]] = None) -> Tuple[str, str]:
    """The (system, user) prompt for a note edit — spec + registry + resolved @mentions + note."""
    system = _NOTE_GUIDE + "\n\n" + _catalog_brief(cat)
    target = f"TARGET SCENE: {scene_id}\n" if scene_id else "TARGET: the whole frame\n"
    assets_block = ("AVAILABLE ASSETS (reference a path in scene data):\n"
                    + "\n".join(f"  [{i}] {a}" for i, a in enumerate(assets)) + "\n") if assets else ""
    prompt = (f"{target}FRAME SPEC:\n{json.dumps(fr, default=str)[:3500]}\n"
              f"{assets_block}{_resolve_hf_mentions(note, fr, assets, mentions)}HUMAN NOTE:\n{note}\n\n"
              f"Return the JSON ops now.")
    return system, prompt


async def revise_frame_note(comp: str, frame_id: str, note: str, scene_id: Optional[str] = None,
                            assets: Optional[List[str]] = None, client=None, retry: int = 1,
                            mentions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Turn a human note into gated edits on a frame. The LLM proposes an ops plan; author.py accepts or
    rejects (with one self-correct retry on rejection). Reverts on failure. Returns {applied, ops, errors}."""
    if client is None:  # lazy real client; tests inject a stub
        from nolan.config import load_config
        from nolan.llm import create_text_llm
        client = create_text_llm(load_config())
    spec, info = load_frame_spec(comp, frame_id)
    fr = spec["frames"][info["i"]]
    system, prompt = build_note_prompt(fr, note, scene_id, assets, catalog(), mentions)
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


def pool_entries(comp: str) -> Dict[str, Dict[str, Any]]:
    """The RAW pool.json rows, keyed by file basename — every field, nothing projected away.

    `asset_pool_meta` (below) is a narrow view built for the edit UI: it keeps source / gen_prompt /
    caption and drops the rest. Reading provenance through it was a real bug — every asset came back
    licence-less because the projection never carried `license` or `source_url`, and `derived_from`
    vanished the same way. Ask HERE for anything the pool records; ask there for the UI's five fields.
    """
    pool_f = _comp_dir(comp) / "pool.json"
    if not pool_f.exists():
        return {}
    try:
        pool = json.loads(pool_f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    entries = pool if isinstance(pool, list) else pool.get("assets", pool.get("items", []))
    out: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        if isinstance(e, dict):
            base = Path(str(e.get("file") or "")).name
            if base:
                out[base] = e
    return out


def asset_pool_meta(comp: str) -> Dict[str, Dict[str, Any]]:
    """Per-asset provenance from pool.json, keyed by file BASENAME so the edit UI can look an asset up from a
    scene's media src. Surfaces the enhanced generation prompt (`gen_prompt`) for ComfyUI/krea2-generated
    assets — the art-directed prompt we generated from — plus the VLM `caption` (a description of the RESULT,
    kept as a fallback for older assets that pre-date prompt persistence) and the source/generated flags."""
    pool_f = _comp_dir(comp) / "pool.json"
    if not pool_f.exists():
        return {}
    try:
        pool = json.loads(pool_f.read_text(encoding="utf-8"))
    except Exception:
        return {}
    entries = pool if isinstance(pool, list) else pool.get("assets", pool.get("items", []))
    out: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        base = Path(str(e.get("file") or "")).name
        if not base:
            continue
        src = str(e.get("source") or "")
        out[base] = {"source": src, "generated": bool(e.get("generated")) or "generated" in src.lower(),
                     "gen_prompt": e.get("gen_prompt") or "", "gen_negative": e.get("gen_negative") or "",
                     "caption": e.get("caption") or ""}
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
    _register_pool_asset(comp, s.name)                     # Q5: adding to a frame also registers in the pool
    return {"path": f"assets/{s.name}", "name": s.name}


def save_upload(comp: str, filename: str, data: bytes) -> Dict[str, Any]:
    adir = _comp_dir(comp) / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    safe = Path(filename).name
    (adir / safe).write_bytes(data)
    _register_pool_asset(comp, safe)                       # Q5: adding to a frame also registers in the pool
    return {"path": f"assets/{safe}", "name": safe}


def pool_original(comp: str, name: str, *, _depth: int = 0) -> Optional[str]:
    """Walk `derived_from` back to the asset a derivative came from — the TRUE original.

    This is the record that used to be the FILENAME. `fit_ground_to_scene` recovered the original by
    `re.sub(r"_fit\\d+s(?:_\\d+)?$", "", stem)` and looking in `assets/`; when only the derivative had
    been staged there the fit silently no-op'd (`ground auto-fit skipped (asset not found:
    assets/a19_04.mp4)`). A name is a convenience for humans; it is not a data model — parse it and
    every rename, every second derivation, every stage/store split breaks the chain.

    Returns None when the asset is not a derivative (or the chain is unknown), so callers can fall back
    without pretending they know. `_depth` bounds a corrupt cycle."""
    if _depth > 8:
        return None
    meta = pool_entries(comp).get(Path(name).name) or {}      # RAW row: the projection drops it
    parent = meta.get("derived_from")
    if not parent:
        return None
    return pool_original(comp, parent, _depth=_depth + 1) or parent


def _register_pool_asset(comp: str, name: str, *, scene_id: Optional[str] = None,
                         frame_id: Optional[str] = None, source: str = "manual",
                         caption: Optional[str] = None, pool_id: Optional[str] = None,
                         derived_from: Optional[str] = None, op: Optional[str] = None,
                         params: Optional[Dict[str, Any]] = None) -> None:
    """Q5: a frame-added asset also becomes a first-class POOL candidate — not just a one-off frame reference.
    Copies it into capture/assets/ (the pool's media dir) and appends an entry to pool.json (matching the
    acquire-engine schema) WITH scene/frame provenance when given. Idempotent by file name; best-effort."""
    try:
        cdir = _comp_dir(comp)
        src = cdir / "assets" / name
        if not src.is_file():
            return
        ext = src.suffix.lower()
        media_type = "video" if ext in _VID_EXT else "image" if ext in _IMG_EXT else "file"
        cap = cdir / "capture" / "assets"
        cap.mkdir(parents=True, exist_ok=True)
        (cap / name).write_bytes(src.read_bytes())         # pool media lives under capture/assets/
        pool_f = cdir / "pool.json"
        pool = []
        if pool_f.exists():
            try:
                pool = json.loads(pool_f.read_text(encoding="utf-8"))
            except Exception:
                pool = []
        if not isinstance(pool, list):
            pool = []
        existing = next((e for e in pool if isinstance(e, dict) and e.get("file") == name), None)
        if existing is not None:
            # Already registered — but BACKFILL the derivation if this call knows it and the entry
            # doesn't. An asset can be pooled by one path (a drag-drop) and derived by another (a
            # later fit), and the chain is what `pool_original` walks; dropping it on the second
            # call is how the record stays permanently absent.
            if derived_from and not existing.get("derived_from"):
                existing["derived_from"] = Path(derived_from).name
                if op:
                    existing["op"] = op
                if params:
                    existing["op_params"] = params
                pool_f.write_text(json.dumps(pool, indent=1), encoding="utf-8")
            return
        entry = {"id": pool_id or f"manual_{sum(1 for e in pool if isinstance(e, dict)) + 1}",
                 "file": name, "media_type": media_type, "query": "", "source": source,
                 "source_url": "", "photographer": "", "license": "user-provided",
                 "width": None, "height": None, "duration": None, "relevance": 1.0,
                 "caption": caption or f"{name} (added to a frame)", "flags": ""}
        if scene_id:
            entry["scene_id"] = scene_id
        if frame_id:
            entry["frame_id"] = frame_id
        # PROVENANCE of a derivation WE performed. Without it the only record that `a19_04_fit15s.mp4`
        # came from `a19_04.mp4` is the filename — and a filename is not a data model.
        if derived_from:
            entry["derived_from"] = Path(derived_from).name
        if op:
            entry["op"] = op
        if params:
            entry["op_params"] = params
        pool.append(entry)
        pool_f.write_text(json.dumps(pool, indent=1), encoding="utf-8")
    except Exception:
        pass                                               # pool bookkeeping must never break the asset add


def _next_edit_name(comp: str, scene_id: str, media_type: str, ext: str) -> str:
    """The next `{scene_id}_edit_{vid|pic}{N}{ext}` name for a scene's manual drag-drop adds (deterministic,
    scene-scoped, self-documenting as an edit-time add). N counts existing files with that scene+kind prefix."""
    kind = "vid" if media_type == "video" else "pic"
    prefix = f"{scene_id}_edit_{kind}"
    adir = _comp_dir(comp) / "assets"
    n = 1 + (sum(1 for p in adir.glob(f"{prefix}*") if p.is_file()) if adir.is_dir() else 0)
    return f"{prefix}{n}{ext}"


def _valid_media_file(path: Path, media_type: str) -> bool:
    """Reject junk (an HTML error page saved as .jpg, a 0-byte 'video'). Image → Pillow-decodable (SVG exempt);
    video → probes to a real, non-zero duration."""
    if media_type == "image":
        if path.suffix.lower() == ".svg":
            return path.stat().st_size > 20
        try:
            from PIL import Image
            with Image.open(path) as im:
                im.load()
            return True
        except Exception:
            return False
    if media_type == "video":
        try:
            from nolan.hf_qa import probe
            return (probe(path).duration or 0) > 0.05
        except Exception:
            return path.stat().st_size > 10000
    return False


def add_scene_asset(comp: str, frame_id: str, scene_id: str, filename: str, data: bytes) -> Dict[str, Any]:
    """Drop an asset onto a SPECIFIC scene (the /hyperframes drag-drop, #5). Validates it, names it
    `{scene_id}_edit_{vid|pic}{N}`, lands it in assets/ + the pool (with scene/frame provenance), dedupes by
    content, and adds it to the scene's SHORTLIST (scene.meta.shortlist). Does NOT wire it into the block —
    the human then picks it from the shortlist / 'use as ground' (a block-aware apply). Returns the entry."""
    import hashlib
    ext = Path(filename).suffix.lower() or ".bin"
    media_type = "video" if ext in _VID_EXT else "image" if ext in _IMG_EXT else "file"
    if media_type == "file":
        raise ValueError(f"unsupported asset type '{ext}' — drop an image or video")
    spec, info = load_frame_spec(comp, frame_id)
    fr = spec["frames"][info["i"]]
    sc = _find_scene(fr, scene_id)
    shortlist = (sc.setdefault("meta", {}) if isinstance(sc, dict) else {}).setdefault("shortlist", [])
    digest = hashlib.sha1(data).hexdigest()
    for item in shortlist:                                 # dedup: same content already dropped on this scene
        if item.get("sha1") == digest:
            return {**item, "deduped": True}
    adir = _comp_dir(comp) / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    name = _next_edit_name(comp, scene_id, media_type, ext)
    dest = adir / name
    dest.write_bytes(data)
    if not _valid_media_file(dest, media_type):
        dest.unlink(missing_ok=True)
        raise ValueError(f"not a decodable {media_type} file")
    _register_pool_asset(comp, name, scene_id=scene_id, frame_id=frame_id, source="manual-edit",
                         caption=f"{name} — dropped on {scene_id}", pool_id=name)
    item = {"name": name, "path": f"assets/{name}", "media_type": media_type, "sha1": digest}
    shortlist.append(item)
    save_frame_spec(Path(info["spec_file"]), spec)
    log_activity(comp, "asset-add", f"dropped {name} on {scene_id}", frame_id=frame_id, scene_id=scene_id, outcome="staged")
    return item


def remove_scene_asset(comp: str, frame_id: str, scene_id: str, name: str) -> Dict[str, Any]:
    """Remove one asset from a scene's shortlist (leaves the file + pool entry — the asset stays available)."""
    spec, info = load_frame_spec(comp, frame_id)
    sc = _find_scene(spec["frames"][info["i"]], scene_id)
    shortlist = (sc.get("meta", {}) or {}).get("shortlist", []) if isinstance(sc, dict) else []
    kept = [i for i in shortlist if i.get("name") != name]
    if isinstance(sc, dict):
        sc.setdefault("meta", {})["shortlist"] = kept
    save_frame_spec(Path(info["spec_file"]), spec)
    log_activity(comp, "asset-remove", f"removed {name} from {scene_id}", frame_id=frame_id, scene_id=scene_id)
    return {"removed": name, "remaining": len(kept)}


def add_pool_asset(comp: str, filename: str, data: bytes) -> Dict[str, Any]:
    """Q1: drop an asset straight into the POOL — NEUTRAL (no scene, no background assumption, plain name), so
    it can be referenced anywhere (a motion, props, any media field). Validates + dedups by content, lands it
    in assets/, registers it in pool.json. Distinct from add_scene_asset (which is scene-scoped + shortlisted)."""
    import hashlib
    ext = Path(filename).suffix.lower() or ".bin"
    media_type = "video" if ext in _VID_EXT else "image" if ext in _IMG_EXT else "file"
    if media_type == "file":
        raise ValueError(f"unsupported asset type '{ext}' — drop an image or video")
    adir = _comp_dir(comp) / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(data).hexdigest()
    for p in adir.glob("*"):                                # dedup by content: reuse an identical existing file
        if p.is_file() and p.suffix.lower() == ext and hashlib.sha1(p.read_bytes()).hexdigest() == digest:
            return {"name": p.name, "path": f"assets/{p.name}", "media_type": media_type, "deduped": True}
    stem = re.sub(r"[^\w.-]+", "_", Path(filename).stem).strip("._") or "clip"
    name, n = f"{stem}{ext}", 1
    while (adir / name).exists():
        name = f"{stem}_{n}{ext}"; n += 1
    dest = adir / name
    dest.write_bytes(data)
    if not _valid_media_file(dest, media_type):
        dest.unlink(missing_ok=True)
        raise ValueError(f"not a decodable {media_type} file")
    _register_pool_asset(comp, name, source="pool-drop", caption=f"{name} (dropped to pool)", pool_id=name)
    log_activity(comp, "asset-add", f"dropped {name} to pool", outcome="pooled")
    return {"name": name, "path": f"assets/{name}", "media_type": media_type}


def _resolve_asset_path(comp: str, path: str) -> Path:
    """A comp-relative asset path → an absolute file INSIDE the comp (guards against traversal).

    Falls back from the STAGE to the STORE. The two tiers are a real invariant
    (`assemble_media.stage_referenced_media` rebuilds `assets/` from `capture/assets/**`, so the stage
    is disposable and holds only what the specs currently reference), but this resolver only ever
    looked at the literal path. So asking for `assets/a19_04.mp4` when only its *derivative* had been
    staged raised FileNotFoundError and the caller — `fit_ground_to_scene` — silently no-op'd, even
    though the original was sitting in `capture/assets/videos/`.

    The basename is the key on both tiers (it is what `pool.json` records), so the fallback is a
    lookup, not a guess."""
    root = _comp_dir(comp).resolve()
    p = (root / path).resolve()
    if root in p.parents and p.is_file():
        return p
    store = (root / "capture" / "assets").resolve()
    if store.is_dir():
        for cand in store.rglob(Path(path).name):
            if cand.is_file():
                return cand.resolve()
    raise FileNotFoundError(f"asset not found in {comp} (stage or store): {path}")


def quickedit_asset(comp: str, path: str, op: str, params: Dict[str, Any],
                    mode: str = "new", name: Optional[str] = None) -> Dict[str, Any]:
    """Apply a fast ffmpeg quick-edit (crop, …) to an asset. mode='inplace' overwrites the file at `path`
    (stashing the ORIGINAL as `<stem>.orig<ext>` the first time, so it stays reversible via revert_asset);
    mode='new' writes a NEW pool asset and registers it. Returns the affected comp-relative path + meta."""
    import shutil
    from nolan.hyperframes import quickedit as qe
    src = _resolve_asset_path(comp, path)
    root = _comp_dir(comp)
    if mode == "inplace":
        orig = src.with_name(src.stem + ".orig" + src.suffix)
        if not orig.exists():
            shutil.copy2(src, orig)                        # first edit → back up the true original (once)
        tmp = src.with_name(src.stem + ".qe_tmp" + src.suffix)
        try:
            qe.apply_quick_edit(src, op, params, tmp)      # edit the CURRENT file (what the user sees)
            tmp.replace(src)
        finally:
            tmp.unlink(missing_ok=True)
        _register_pool_asset(comp, src.name)               # ensure it's a pool entry (no-op if already)
        log_activity(comp, "asset-edit", f"{op} in place: {src.name}", outcome="applied")
        return {"path": src.relative_to(root).as_posix(), "name": src.name, "mode": "inplace", "revertable": True}

    # new pool asset
    stem = re.sub(r"[^\w.-]+", "_", (name or f"{src.stem}_{op}")).strip("._") or f"{src.stem}_{op}"
    _oe = qe.QUICK_EDITS.get(op, {}).get("out_ext")                # may be a callable (treat: image+plate → .mp4)
    ext = (_oe(src, params) if callable(_oe) else _oe) or src.suffix   # e.g. remove_bg → .png (RGBA)
    adir = root / "assets"
    out, n = adir / f"{stem}{ext}", 1
    while out.exists():
        out = adir / f"{stem}_{n}{ext}"; n += 1
    qe.apply_quick_edit(src, op, params, out)
    _register_pool_asset(comp, out.name, source="quick-edit", caption=f"{out.name} ({op} of {src.name})",
                         pool_id=out.name, derived_from=src.name, op=op, params=params)
    log_activity(comp, "asset-edit", f"{op} → new pool asset {out.name}", outcome="pooled")
    return {"path": out.relative_to(root).as_posix(), "name": out.name, "mode": "new"}


def cleanup_analyze(comp: str, path: str, confirm: bool = True) -> Dict[str, Any]:
    """Analyze a pool asset (video OR image) for the composite cleanup — detect a corner LOGO, burned-in
    CAPTIONS, and (video) stray head/tail frames → a reviewable PLAN (crop + trim). `confirm` runs the
    OpenRouter vision filter over the CV proposals. No file is written."""
    from nolan.hyperframes import cleanup as cl
    src = str(_resolve_asset_path(comp, path))
    plan = cl.analyze(src, confirm=(cl.make_vision_confirm(src) if confirm else None))
    return {"path": path, "plan": plan}


def cleanup_asset(comp: str, path: str, confirm: bool = True,
                  plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Auto-clean a pool asset → a NEW pool asset in ONE ffmpeg pass (logo/caption crop + head/tail trim).
    Pass a reviewed `plan` to skip re-analysis; else it analyzes (with the vision `confirm`). Returns
    {changed, plan, path?, name?}. A no-op (nothing detected) writes NOTHING."""
    from nolan.hyperframes import cleanup as cl
    if plan is None:
        src = str(_resolve_asset_path(comp, path))
        plan = cl.analyze(src, confirm=(cl.make_vision_confirm(src) if confirm else None))
    if not plan.get("changed"):
        log_activity(comp, "asset-edit", f"cleanup: nothing to clean — {Path(path).name}", outcome="noop")
        return {"changed": False, "plan": plan}
    res = quickedit_asset(comp, path, "cleanup", {"plan": plan}, mode="new",
                          name=f"{Path(path).stem}_clean")
    bits = [b for b in ("logo" if plan.get("logos") else "", "captions" if plan.get("caption") else "",
                        "trim" if plan.get("trim_in") or (plan.get("trim_out") and plan.get("kind") == "video"
                        and plan["trim_out"] < (plan.get("dur") or 0) - 1e-3) else "") if b]
    log_activity(comp, "asset-edit", f"cleanup ({', '.join(bits) or 'crop'}) → {res.get('name')}", outcome="pooled")
    return {"changed": True, "plan": plan, **res}


def cleanup_analyze_batch(comp: str, paths: list, confirm: bool = True) -> Dict[str, Any]:
    """Analyze MANY pool assets for the review UI → {results:[{path, plan} | {path, error}]}. Builds ONE
    shared vision provider and reuses it across every asset, so a whole-pool review doesn't fan out N
    provider constructions. Per-asset failures are captured (not raised) so one bad file can't sink the batch."""
    from nolan.hyperframes import cleanup as cl
    provider = None
    if confirm:
        try:
            provider = cl.default_vision_provider()          # vision down → provider stays None → CV-only
        except Exception:
            provider = None
    results = []
    for path in paths:
        try:
            src = str(_resolve_asset_path(comp, path))
            conf = cl.make_vision_confirm(src, provider=provider) if confirm else None
            results.append({"path": path, "plan": cl.analyze(src, confirm=conf)})
        except Exception as e:
            results.append({"path": path, "error": str(e)})
    return {"results": results}


def treat_preview(comp: str, path: str, effects: list) -> Path:
    """A FAST, low-res REAL bake of the treat effects (NO pool registration) for the fx-modal 'Preview
    result' button — the true ffmpeg output the CSS preview only approximates. A single downscaled frame
    for a colour-only image, a ~1.5s downscaled clip otherwise. Overwrites a scratch file per comp."""
    from nolan.hyperframes import quickedit as qe
    src = _resolve_asset_path(comp, path)
    ext = qe._treat_ext(src, {"effects": effects}) or src.suffix
    pdir = _comp_dir(comp) / "_fxpreview"
    pdir.mkdir(parents=True, exist_ok=True)
    out = pdir / f"preview{ext}"
    qe.apply_quick_edit(src, "treat", {"effects": effects, "preview": True}, out)
    return out


def fit_ground_to_scene(comp: str, frame_id: str, scene_id: str) -> Dict[str, Any]:
    """#5: retime a scene's VIDEO ground so the WHOLE clip spans exactly the scene's duration when they differ.
    Creates a fitted clip (new pool asset — the original is untouched, so it's reversible by re-pointing the
    ground) and re-composes. No-op (fitted=False) if the ground isn't a video or already matches (±0.15s)."""
    spec, info = load_frame_spec(comp, frame_id)
    fr = spec["frames"][info["i"]]
    sc = _find_scene(fr, scene_id)
    g = (sc.get("data", {}) or {}).get("ground") or {}
    if not (isinstance(g, dict) and g.get("kind") == "video" and g.get("src")):
        return {"fitted": False, "reason": "the scene ground is not a video"}
    scene_dur = float(sc.get("dur", 0) or 0)
    if scene_dur <= 0:
        return {"fitted": False, "reason": "the scene has no duration"}
    # ALWAYS fit from the TRUE ORIGINAL. Fitting the CURRENT (already-fitted) clip is what made a retime
    # round-trip DEGRADE (each fit slowed the last one further) and spawn redundant `_fit13s_1/_2` copies.
    #
    # ASK THE INDEX, don't parse the name. This used to be `re.sub(r"_fit\d+s(?:_\d+)?$", "", stem)` plus a
    # lookup in `assets/` — so when only the derivative had been staged there (the original living in
    # `capture/assets/videos/`), the fit silently no-op'd: `ground auto-fit skipped (asset not found:
    # assets/a19_04.mp4)`. `pool_original` walks `derived_from`, which is recorded at derivation time.
    # The regex stays ONLY as a fallback for assets pooled before that field existed.
    cur = Path(g["src"])
    tracked = pool_original(comp, cur.name)
    if tracked:
        orig_rel = cur.with_name(tracked).as_posix()
        orig_stem = Path(tracked).stem
    else:
        orig_stem = re.sub(r"_fit\d+s(?:_\d+)?$", "", cur.stem)
        orig_rel = cur.with_name(orig_stem + cur.suffix).as_posix()  # forward slashes — the HTML src needs them
    fit_name = f"{orig_stem}_fit{scene_dur:.0f}s{cur.suffix}"
    fit_rel = cur.with_name(fit_name).as_posix()
    fit_path = _comp_dir(comp) / fit_rel
    if cur.name == fit_name and fit_path.exists():                 # already pointing at the right fit clip
        return {"fitted": False, "reason": "already fit to the scene"}
    if fit_path.exists() and fit_path.stat().st_size > 1000:       # a matching fit clip exists (round-trip) → re-point, no ffmpeg
        g["src"] = fit_rel
        save_frame_spec(Path(info["spec_file"]), spec)
        recompose_frame(comp, frame_id)
        return {"fitted": True, "to": round(scene_dur, 2), "path": fit_rel, "reused": True}
    src = _resolve_asset_path(comp, orig_rel)                      # fit the ORIGINAL, not the current fitted clip
    from nolan.hf_qa import probe
    src_dur = float(probe(src).duration or 0)
    if src_dur <= 0:
        return {"fitted": False, "reason": "could not read the video duration"}
    if abs(src_dur - scene_dur) < 0.15:                           # the original already matches → use it directly
        if cur.name != Path(orig_rel).name:
            g["src"] = orig_rel
            save_frame_spec(Path(info["spec_file"]), spec)
            recompose_frame(comp, frame_id)
            return {"fitted": True, "to": round(scene_dur, 2), "path": orig_rel, "reused": True}
        return {"fitted": False, "reason": "already matches the scene"}
    res = quickedit_asset(comp, orig_rel, "fit", {"target": scene_dur, "src_dur": src_dur},
                          mode="new", name=f"{orig_stem}_fit{scene_dur:.0f}s")
    g["src"] = res["path"]                                        # the ground now references the retimed clip
    save_frame_spec(Path(info["spec_file"]), spec)
    recompose_frame(comp, frame_id)
    log_activity(comp, "asset-edit", f"retimed ground {src_dur:.1f}s→{scene_dur:.1f}s on {scene_id}",
                 frame_id=frame_id, scene_id=scene_id, outcome="applied")
    return {"fitted": True, "from": round(src_dur, 2), "to": round(scene_dur, 2),
            "factor": round(src_dur / scene_dur, 3), "path": res["path"], "original": orig_rel}


def ensure_grounds_fit(comp: str, frame_id: str) -> List[str]:
    """DETERMINISTIC backstop for the video-ground auto-fit: fit EVERY video ground in a frame to its scene
    duration, whatever set it (UI / AI / batch / an old session) or however the scene was later retimed.
    Idempotent — fit_ground_to_scene is a no-op (±0.15s) once a ground matches, so this only does work the
    first render after a ground-set or a duration change. Run at render time so the fit no longer depends on a
    frontend trigger firing. Returns the scene ids that were (re)fit."""
    info = _frame_index(comp).get(frame_id)
    if not info:
        return []
    spec = json.loads(Path(info["spec_file"]).read_text(encoding="utf-8"))
    fr = spec["frames"][info["i"]]
    fit = []
    for sc in list(fr.get("scenes", [])):
        g = (sc.get("data", {}) or {}).get("ground") or {}
        if not (isinstance(g, dict) and g.get("kind") == "video" and g.get("src")):
            continue
        # fast-path: fit_ground_to_scene names the fitted clip `<stem>_fit<round(dur)>s`; if the current src
        # already carries a fit tag for ~this scene's duration, it's fit → skip the (ffmpeg) duration probe.
        m = re.search(r"_fit(\d+)s(?:_\d+)?\.[^.]+$", g["src"])
        if m and abs(int(m.group(1)) - float(sc.get("dur", 0) or 0)) < 0.6:
            continue
        try:
            if fit_ground_to_scene(comp, frame_id, sc["id"]).get("fitted"):
                fit.append(sc["id"])
        except Exception as e:                             # a bad asset shouldn't abort the render
            print(f"  ⚠ {frame_id}/{sc['id']}: ground auto-fit skipped ({e})")
    return fit


def revert_asset(comp: str, path: str) -> Dict[str, Any]:
    """Undo an in-place quick-edit: restore `<stem>.orig<ext>` over the asset and drop the backup."""
    src = _resolve_asset_path(comp, path)
    orig = src.with_name(src.stem + ".orig" + src.suffix)
    if not orig.exists():
        raise FileNotFoundError("no backup to revert (this asset wasn't edited in place)")
    orig.replace(src)
    _register_pool_asset(comp, src.name)
    log_activity(comp, "asset-edit", f"reverted {src.name} to original", outcome="applied")
    return {"path": src.relative_to(_comp_dir(comp)).as_posix(), "name": src.name, "reverted": True}


def quick_edit_ops() -> Dict[str, Any]:
    """The quick-edit registry (op → {label, media, ui, background}) for the edit UI to render controls from."""
    from nolan.hyperframes import quickedit as qe
    return {k: {"label": v["label"], "media": list(v["media"]), "ui": v.get("ui", "button"),
                "background": bool(v.get("background"))} for k, v in qe.QUICK_EDITS.items()}


# ------------------------------------------------------------------ per-frame comments (batch changeset)

def stage_comment(comp: str, frame_id: str, text: str, scene_id: Optional[str] = None,
                  mentions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Stage a free-text edit comment on a frame WITHOUT applying it — the batch-edit changeset (#4/#5).
    Persisted losslessly in the frame spec's meta.comments (survives every round-trip). `mentions` are the
    STABLE @-token bindings captured when the human picked from the tray — [{token,type,ref,label}] — so a
    referenced asset/scene resolves unambiguously downstream (the batch agent + the LLM path both read
    them); without this only the positional text '@asset0' survived and the reference drifted/was lost."""
    text = (text or "").strip()
    if not text:
        raise ValueError("comment text required")
    spec, info = load_frame_spec(comp, frame_id)
    fr = spec["frames"][info["i"]]
    comments = fr.setdefault("meta", {}).setdefault("comments", [])
    c = {"id": f"c{len(comments) + 1}", "text": text, "scene_id": scene_id, "status": "open"}
    clean = [{k: m.get(k) for k in ("token", "type", "ref", "label") if m.get(k) is not None}
             for m in (mentions or []) if isinstance(m, dict) and m.get("token") and m.get("ref")]
    if clean:
        c["mentions"] = clean
    comments.append(c)
    save_frame_spec(Path(info["spec_file"]), spec)
    log_activity(comp, "comment", f"staged: {text[:80]}", frame_id=frame_id, scene_id=scene_id, outcome="staged")
    return {**c, "frame_id": frame_id}


def list_changeset(comp: str, include_deferred: bool = False) -> List[Dict[str, Any]]:
    """All OPEN per-frame comments across the comp — the pending batch-edit changeset (for #5 dispatch).
    `include_deferred=True` also picks up work parked on an external resource, so "the GPU is back,
    re-run the batch" is one flag rather than a hand-written script."""
    want = {"open", "deferred"} if include_deferred else {"open"}
    out = []
    for fr in list_frames(comp):
        fid = fr.get("id") if isinstance(fr, dict) else fr
        spec, info = load_frame_spec(comp, fid)
        for c in spec["frames"][info["i"]].get("meta", {}).get("comments", []):
            if c.get("status", "open") in want:
                out.append({**c, "frame_id": fid})
    return out


# A comment is resolvable until it reaches a TERMINAL state. "dispatched" is deliberately NOT terminal
# (accepting an agent's proposal marks it applied; rejecting reopens it) — guarding on == "open" left
# every dispatched comment stuck forever.
#
# `deferred` is also non-terminal, and it exists because the alternatives were both lies. An agent with
# real work it could not do yet — ComfyUI down, a provider rate-limited, a render queued — could either
# say `blocked` (which means "there is no landing spot for this", a capability judgement it had not
# made) or leave the comment dispatched and write an activity line, which is invisible in the
# changeset. The batch that prompted this chose the second and the work simply vanished from the
# review. A state that means "real work, blocked on an external resource, retry HERE" keeps it visible
# and re-dispatchable.
COMMENT_STATES = ("open", "dispatched", "deferred", "applied", "blocked", "error")
TERMINAL_COMMENT_STATES = frozenset({"applied", "blocked", "error"})


def resolve_comment(comp: str, frame_id: str, comment_id: Optional[str] = None,
                    status: str = "applied", reason: Optional[str] = None,
                    retry: Optional[str] = None) -> Dict[str, Any]:
    """Resolve staged comment(s): 'applied' | 'blocked' (no gated landing spot — give a `reason`) |
    'error' | 'deferred' (real work, waiting on an external resource — give a `reason` and a `retry`
    command). comment_id=None resolves every open one in the frame. Records it to the activity feed."""
    if status not in COMMENT_STATES:
        raise ValueError(f"unknown comment status {status!r} — one of {list(COMMENT_STATES)}")
    spec, info = load_frame_spec(comp, frame_id)
    fr = spec["frames"][info["i"]]
    n = 0
    for c in fr.get("meta", {}).get("comments", []):
        if (comment_id is None or c.get("id") == comment_id) \
                and c.get("status", "open") not in TERMINAL_COMMENT_STATES:
            c["status"] = status
            if reason:
                c["reason"] = reason
            if status == "deferred":
                c["retry"] = retry or ""      # the command that resumes it — a deferral with no way
                c.pop("_dispatched_to", None)  # back is just a different way of dropping the work
            n += 1
            log_activity(comp, "comment", f"{status}: {c.get('text', '')[:80]}", actor="agent",
                         frame_id=frame_id, scene_id=c.get("scene_id"), outcome=status, detail=reason)
    save_frame_spec(Path(info["spec_file"]), spec)
    return {"ok": True, "resolved": n}


def list_deferred(comp: str) -> List[Dict[str, Any]]:
    """Comments parked on an external resource, with the command that resumes each — the queue a human
    (or the next batch) works through when the GPU is back / the provider is answering again."""
    out = []
    for fr in list_frames(comp):
        fid = fr.get("id") if isinstance(fr, dict) else fr
        spec, info = load_frame_spec(comp, fid)
        for c in spec["frames"][info["i"]].get("meta", {}).get("comments", []):
            if c.get("status") == "deferred":
                out.append({**c, "frame_id": fid})
    return out


# ------------------------------------------------------------------ activity feed (edit / agent process log)

def log_activity(comp: str, kind: str, summary: str, *, actor: str = "human",
                 frame_id: Optional[str] = None, scene_id: Optional[str] = None,
                 outcome: Optional[str] = None, detail: Optional[str] = None) -> None:
    """Append ONE event to the per-comp activity log (<comp>/.hf_activity.jsonl) — the process/update/error
    feed the /hyperframes page surfaces for every single AND batch/agent edit. Best-effort; never raises
    (bookkeeping must not break an edit). `outcome` ∈ applied|rejected|blocked|staged|dispatched|error."""
    try:
        import time
        ev = {"ts": round(time.time(), 3), "actor": actor, "kind": kind, "summary": summary,
              "frame_id": frame_id, "scene_id": scene_id, "outcome": outcome}
        if detail:
            ev["detail"] = detail[:500]
        with open(_comp_dir(comp) / ".hf_activity.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ------------------------------------------------------------------ capability-gap ledger
# A gate refusal is two different things wearing one face: "you did it wrong" and "the thing you asked
# for does not exist yet". The second is the more valuable signal and it used to evaporate — three of
# twenty-five notes in one batch asked for a background on a `juxtaposition` (a block with no ground),
# and that only became known because an agent happened to mention it in a retro. So a CAPABILITY-GAP
# refusal is RECORDED: the gate names the gap, this counts it, and a recurring count is the argument for
# building the capability instead of documenting the limitation.
_GAP_RE = re.compile(r"CAPABILITY-GAP\s+(?P<field>[\w.\[\]]+)\s+—\s+the\s+(?P<block>[\w_]+)\s+block")


def log_gap(comp: str, gate_out: str, *, frame_id: Optional[str] = None, scene_id: Optional[str] = None,
            note: Optional[str] = None, agent: Optional[str] = None, workaround: Optional[str] = None) -> int:
    """Record every CAPABILITY-GAP the gate reported in `gate_out`. Returns how many were logged.
    Best-effort: ledger bookkeeping must never break a proposal."""
    n = 0
    try:
        for m in _GAP_RE.finditer(gate_out or ""):
            row = {"ts": round(time.time(), 3), "block": m.group("block"), "field": m.group("field"),
                   "frame_id": frame_id, "scene_id": scene_id, "agent": agent,
                   "note": (note or "")[:300] or None, "workaround": workaround}
            with open(_comp_dir(comp) / ".hf_gaps.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    except Exception:
        pass
    return n


def report_gap(comp: str, block: str, field: str, note: str, *, frame_id: Optional[str] = None,
               scene_id: Optional[str] = None, agent: Optional[str] = None,
               workaround: Optional[str] = None) -> Dict[str, Any]:
    """File a capability gap the GATE could not have caught.

    `log_gap` only records what a refusal already named, which makes the ledger circular: it can count
    gaps we have already implemented a refusal for, and is blind to every new one. An agent asked for a
    3D exploded donut with a drop shadow on a `pie`; `data.explode/depth/shadow` all validate rc=0
    because they are simply unknown keys, so nothing was refused and nothing was logged — the agent had
    to write the row by hand for it to exist at all.

    So the ledger has two writers: the gate files what it refuses, and whoever discovers a gap files it
    directly. A count is only useful if the things it cannot see are few."""
    row = {"ts": round(time.time(), 3), "block": block, "field": field, "frame_id": frame_id,
           "scene_id": scene_id, "agent": agent, "note": (note or "")[:300] or None,
           "workaround": workaround, "source": "reported"}
    try:
        with open(_comp_dir(comp) / ".hf_gaps.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass
    log_activity(comp, "gap", f"{block}.{field}: {(note or '')[:70]}", actor=agent or "agent",
                 frame_id=frame_id, scene_id=scene_id, outcome="blocked")
    return row


def list_gaps(comp: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    """Capability gaps recorded for one comp, or ROLLED UP across every comp when `comp` is None —
    the cross-project count that turns 'an agent mentioned it' into 'N asks, M comps, build it'."""
    comps = [comp] if comp else [c["name"] for c in discover_compositions()]
    rows: List[Dict[str, Any]] = []
    for c in comps:
        try:
            f = _comp_dir(c) / ".hf_gaps.jsonl"
        except Exception:
            continue
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append({**json.loads(line), "comp": c})
                except json.JSONDecodeError:
                    pass
    tally: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in rows:
        k = (r.get("block", "?"), r.get("field", "?"))
        e = tally.setdefault(k, {"block": k[0], "field": k[1], "asks": 0, "comps": set(), "examples": []})
        e["asks"] += 1
        e["comps"].add(r.get("comp"))
        if r.get("note") and len(e["examples"]) < 3:
            e["examples"].append(r["note"])
    out = [{**e, "comps": sorted(x for x in e["comps"] if x)} for e in tally.values()]
    out.sort(key=lambda e: (-e["asks"], e["block"]))
    return out[:limit]


def list_activity(comp: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Recent activity events, NEWEST first (the /hyperframes activity feed)."""
    f = _comp_dir(comp) / ".hf_activity.jsonl"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return list(reversed(out))[:limit]


# ------------------------------------------------------------------ proposals (agent edit → human accept)
# The AGENT CONTRACT (CLAUDE.md): an agent's edit is a PROPOSAL that passes the deterministic gate AND a
# human accept before it becomes canonical — draft → validate → accept. Batch/agent edits land HERE (never
# straight into the canonical spec); the human reviews the ops + rationale and accepts/rejects each one.

def _proposals_path(comp: str) -> Path:
    return _comp_dir(comp) / ".hf_proposals.json"


def _load_proposals(comp: str) -> List[Dict[str, Any]]:
    f = _proposals_path(comp)
    try:
        d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _save_proposals(comp: str, props: List[Dict[str, Any]]) -> None:
    _proposals_path(comp).write_text(json.dumps(props, indent=1, ensure_ascii=False), encoding="utf-8")


@contextlib.contextmanager
def _proposals_lock(comp: str, timeout: float = 20.0):
    """Cross-PROCESS mutex around `.hf_proposals.json`.

    Every proposal mutation is a read-modify-write of one JSON array, and the writers are separate
    processes: the hub, each tmux fleet agent in a batch, the bespoke agent, the effect agent. Two
    concurrent `propose_scene_edit` calls both read N entries, both append, both write N+1 — one
    proposal is lost outright, and both are handed the id `p{N+1}` so even the survivor is ambiguous.
    That is latent today (a batch agent works sequentially) and guaranteed the moment a batch is sharded
    across agents, so the lock lands with the sharding it enables.

    An O_CREAT|O_EXCL lockfile is the portable primitive here — `fcntl` is absent on Windows and this
    tree is worked from both sides. A lock older than `timeout` is treated as abandoned (a killed agent
    must not wedge the comp forever) and broken."""
    lf = _comp_dir(comp) / ".hf_proposals.lock"
    deadline = time.time() + timeout
    fd = None
    while fd is None:
        try:
            fd = os.open(str(lf), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                stale = (time.time() - lf.stat().st_mtime) > timeout
            except OSError:
                stale = False
            if stale or time.time() > deadline:
                lf.unlink(missing_ok=True)          # abandoned by a dead writer — take it
                continue
            time.sleep(0.05)
    try:
        os.write(fd, f"{os.getpid()}".encode())
        os.close(fd)
        yield
    finally:
        lf.unlink(missing_ok=True)


def _next_proposal_id(props: List[Dict[str, Any]]) -> str:
    """`p{max+1}`, derived from the ids PRESENT rather than from `len()` — a rejected-then-pruned entry,
    or any gap, made `p{len+1}` collide with a live proposal."""
    n = 0
    for p in props:
        m = re.match(r"p(\d+)$", str(p.get("id", "")))
        if m:
            n = max(n, int(m.group(1)))
    return f"p{n + 1}"


def _comp_theme(comp: str) -> Optional[str]:
    """The comp's theme, from its hyperframes.json.

    Exists because `author.resolve_theme`'s fallback (read hyperframes.json from
    `Path(out_dir).parents[1]`) only works when out_dir is literally `<comp>/compositions/frames`.
    Both the proposal GATE (no out_dir at all) and the trial BUILD (a scratch dir two levels deeper)
    silently fell through to the default theme. Two call sites, one fixed and one missed for a day —
    so the answer lives here and both ask it."""
    try:
        return json.loads((_comp_dir(comp) / "hyperframes.json").read_text(encoding="utf-8")).get("theme")
    except (json.JSONDecodeError, OSError):
        return None


def _gate_validate_only(comp: str, spec: Dict[str, Any]) -> Tuple[bool, str]:
    """Run author.py --validate-only on a spec dict WITHOUT building/saving anything — the proposal gate.
    Written to a NON-*.spec.json temp under the comp dir so list_frames' glob never picks it up."""
    tmp = _comp_dir(comp) / f".proposal_gate.{int(time.time() * 1000)}.tmp.json"
    # GATE IN THE ESSAY'S OWN THEME. `--validate-only` passes no `--out-dir`, so `resolve_theme`'s
    # hyperframes.json fallback never fires and every proposal was validated as the DEFAULT theme.
    # That is not cosmetic here: variant resolution is theme-CONSTRAINED (`_resolve_variant` only
    # allows arrangements in `theme.allowed`), so the gate could accept a layout the real theme
    # forbids — and then the accept, which builds with the right theme, silently resolves something
    # else. Found by a cold agent on `swiss-ikb`; the sibling of the preview theme-drop fixed earlier
    # the same day, which is the tell that this needed a shared resolver rather than two call sites.
    theme = _comp_theme(comp)
    try:
        tmp.write_text(json.dumps(spec), encoding="utf-8")
        r = subprocess.run([sys.executable, "-X", "utf8", str(AUTHOR), "--spec", str(tmp), "--validate-only"]
                           + (["--theme", theme] if theme else []),
                           cwd=str(BRIDGE), capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    finally:
        tmp.unlink(missing_ok=True)


def frame_fit_error(fr: Dict[str, Any], tol: float = 0.05) -> Optional[str]:
    """Do this frame's scenes still FIT inside it? None when they do.

    Narration owns duration: `frame.dur` is set by the VO section, so scenes must fit it — a scene
    that runs past the end is clipped, and everything after a mistimed one plays against the wrong
    words. A batch agent asked to give a timeline "+6 seconds, taken from whatever else can spare it"
    granted +8.7s and took back only 7.16s, leaving `03-maker` 1.56s over its 47.58s. It reported the
    requirement `met` and the gate passed it, because the gate validates the SCHEMA and this is
    arithmetic.

    Measured before it was made blocking: 0 of 122 shipped frames overrun, so this has no false
    positives to spend (WIRING_CHECKLIST #11).
    """
    scenes = [s for s in (fr.get("scenes") or []) if isinstance(s, dict)]
    dur = float(fr.get("dur", 0) or 0)
    if not scenes or dur <= 0:
        return None
    end = max(float(s.get("start", 0) or 0) + float(s.get("dur", 0) or 0) for s in scenes)
    if end <= dur + tol:
        return None
    over = end - dur
    last = max(scenes, key=lambda s: float(s.get("start", 0) or 0) + float(s.get("dur", 0) or 0))
    return (f"frame {fr.get('id')!r} is {dur:.2f}s but its scenes run to {end:.2f}s "
            f"(+{over:.2f}s, last out is {last.get('id')!r}). Narration owns duration — the VO section "
            f"fixes the frame length, so time given to one scene must be taken from another. Retime a "
            f"neighbour by {over:.2f}s, or shorten this scene.")


def timing_advisories(before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
    """Overlaps and gaps a retime INTRODUCED — reported at review, never gated.

    Deliberately advisory. Same-track overlap is LEGAL in a frame composition (diamond-v2 post-mortem
    item 5 was withdrawn for exactly this: two scenes on screen together is a real compositional
    choice, and gating on it broke valid work). But an overlap that appears as the RESIDUE of an
    unbalanced retime is not a choice, and the reviewer should see it.

    Live example: asked to give a timeline "+6 seconds, taken from whatever else can spare it", an
    agent freed 7.16s from one neighbour and spent 8.72s, leaving the last two shots stacked for
    1.56s — and reported the requirement `met`. Nothing ran past the frame end, so no gate could
    honestly refuse it; only a human comparing the before and after would notice."""
    def seq(fr):
        return [(s.get("id"), float(s.get("start", 0) or 0),
                 float(s.get("start", 0) or 0) + float(s.get("dur", 0) or 0))
                for s in (fr.get("scenes") or []) if isinstance(s, dict)]

    def seams(rows):
        return {(a[0], b[0]): round(b[1] - a[2], 2) for a, b in zip(rows, rows[1:])}
    was, now = seams(seq(before)), seams(seq(after))
    out = []
    for k, delta in now.items():
        if abs(delta) < 0.02 or abs(was.get(k, 0.0) - delta) < 0.02:
            continue                                   # unchanged, or already there before the edit
        kind = "OVERLAP" if delta < 0 else "GAP"
        out.append(f"{kind} {abs(delta):.2f}s between {k[0]} and {k[1]} — introduced by this edit "
                   f"(was {was.get(k, 0.0):+.2f}s). Legal, but check it was intended.")
    return out


def retime_durability(before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
    """Will this timing change SURVIVE the next finish? A note per scene where it will not.

    `sync.place_scenes` rewrites `start` and `dur` for EVERY scene on every finish — start from the
    scene's own placement key (its `anchor`, else `operative`, else its visible text), dur from where
    the NEXT scene lands. Nothing is pinned, and that is the invariant, not a bug: narration owns
    duration. The consequence is that a timing number typed by hand is a PREVIEW of what sync will
    compute, never an instruction to it.

    Which nobody was told. A cold agent found a July retime on `06-dido/c1` already back at its
    pre-edit values in the spec — a human moved a scene through the edit UI, the render honoured it,
    and the next `hf-finish` silently put it back. The edit reported success both times.

    ADVISORY, and measured before choosing that: across 59 proposals on four comps a blocking rule
    scored 0 true positives and 2 false ones (v5's p5/p6 hand-compute a timeline around a scene they
    ADD with its own anchor — sync then recomputes it correctly, so the hand numbers are a harmless
    preview). Hence the structural exemption below: when the scene set changes, the timeline is being
    re-laid and sync's recompute is the point.
    """
    def rows(fr):
        return [s for s in (fr.get("scenes") or []) if isinstance(s, dict)]
    a, b = rows(before), rows(after)
    if [s.get("id") for s in a] != [s.get("id") for s in b]:
        return []                       # a scene was added/removed/reordered — see the docstring
    try:
        from .sync import _scene_query
    except Exception:
        return []
    key_a = {s.get("id"): _scene_query(s) for s in a}
    key_b = {s.get("id"): _scene_query(s) for s in b}
    out: List[str] = []
    for i, (was, now) in enumerate(zip(a, b)):
        sid = now.get("id")
        moved_start = abs(float(now.get("start", 0) or 0) - float(was.get("start", 0) or 0)) >= 0.02
        # The scene's END, not its dur: moving a start necessarily changes dur when the frame end is
        # fixed, and reporting that as a second finding made a plain move look like two problems.
        end_a = float(was.get("start", 0) or 0) + float(was.get("dur", 0) or 0)
        end_b = float(now.get("start", 0) or 0) + float(now.get("dur", 0) or 0)
        moved_dur = abs(end_b - end_a) >= 0.02
        if moved_start and key_a.get(sid) == key_b.get(sid):
            out.append(f"TRANSIENT: {sid}'s start was changed but its anchor was not — word-sync "
                       f"recomputes start from the anchor at the next hf-finish and this reverts. "
                       f"Move the anchor to the phrase the shot should land on instead.")
        if moved_dur:
            nxt = b[i + 1].get("id") if i + 1 < len(b) else None
            if nxt is None:
                out.append(f"TRANSIENT: {sid} is the LAST scene — its dur is frame.dur minus its "
                           f"start, so it cannot be authored at all. Move its anchor.")
            elif key_a.get(nxt) == key_b.get(nxt):
                out.append(f"TRANSIENT: {sid}'s dur was changed but {nxt}'s anchor was not — dur is "
                           f"derived as {nxt}'s start minus {sid}'s, so it reverts at the next "
                           f"hf-finish. To lengthen {sid}, move {nxt}'s anchor later.")
    return out


def _proposal_layout_lint(fr: Dict[str, Any], scene_id: Optional[str]) -> List[Dict[str, Any]]:
    """Deterministic layout lint of the proposal's touched RAW scene(s) — the composition gate v2.
    ADVISORY: surfaced at review (like `requirements`), never blocks accept. Only raw scenes are
    linted here (their declared geometry is in the spec; block scenes are linted post-compose in
    finish). Archetype comes from the scene's meta or its block type."""
    try:
        from nolan.hyperframes import layout_lint as _ll
        from nolan import composition as _comp
    except Exception:
        return []
    scenes = fr.get("scenes", []) if isinstance(fr, dict) else []
    targets = [s for s in scenes if isinstance(s, dict) and (scene_id is None or s.get("id") == scene_id)]
    out: List[Dict[str, Any]] = []
    for sc in targets:
        data = sc.get("data") or {}
        html = data.get("html")
        if sc.get("type") != "raw" or not html:
            continue
        arche = (sc.get("meta") or {}).get("archetype") or _comp.block_archetype(sc.get("type", ""))
        try:
            vios = _ll.lint_raw_scene(html if isinstance(html, list) else [html], arche, scene=sc.get("id") or "raw")
        except Exception:
            continue
        out.extend(v.as_dict() for v in vios)
    return out[:20]


def propose_scene_edit(comp: str, frame_id: str, scene_id: Optional[str] = None,
                       ops: Optional[List[Dict[str, Any]]] = None, rationale: str = "",
                       agent: Optional[str] = None, model: Optional[str] = None,
                       comment_id: Optional[str] = None,
                       requirements: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Create a PROPOSAL — apply `ops` (the _apply_ops plan) to a COPY of the frame, GATE it (validate-only),
    and record it WITHOUT touching the canonical spec. Returns the proposal (with gate_ok + any errors).
    `requirements` is the agent's coverage report against the comment's extracted checklist —
    [{req_id, status: met|partial|unmet|deferred, note}] — surfaced at review so a miss is visible, not
    silent (advisory: it never blocks accept)."""
    ops = ops or []
    spec, info = load_frame_spec(comp, frame_id)
    trial = copy.deepcopy(spec)
    err = None
    try:
        _apply_ops(trial["frames"][info["i"]], ops)
    except Exception as e:
        err = f"ops error: {type(e).__name__}: {e}"
    # Arithmetic the schema gate cannot see — checked BEFORE shelling out, since it is free.
    fit = None if err else frame_fit_error(trial["frames"][info["i"]])
    if fit:
        err = f"TIMING: {fit}"
    gate_ok, gate_out = (False, err) if err else _gate_validate_only(comp, trial)
    prop = {"id": None, "frame_id": frame_id, "scene_id": scene_id, "ops": ops,
            "rationale": (rationale or "").strip(), "gate_ok": gate_ok,
            "gate_out": "" if gate_ok else (gate_out or "")[-600:],
            "provenance": {"agent": agent, "model": model, "ts": round(time.time(), 3), "comment_id": comment_id},
            "status": "proposed"}
    if requirements:
        prop["requirements"] = [{k: r.get(k) for k in ("req_id", "status", "note") if r.get(k) is not None}
                                for r in requirements if isinstance(r, dict)]
    if not err:
        layout = _proposal_layout_lint(trial["frames"][info["i"]], scene_id)
        if layout:
            prop["layout"] = layout   # advisory composition-gate findings, shown at review
        tim = timing_advisories(spec["frames"][info["i"]], trial["frames"][info["i"]])
        tim += retime_durability(spec["frames"][info["i"]], trial["frames"][info["i"]])
        if tim:
            prop["timing"] = tim      # overlaps/gaps a retime introduced — legal, but worth a look
    if not gate_ok and log_gap(comp, gate_out or "", frame_id=frame_id, scene_id=scene_id,
                               note=rationale, agent=agent):
        prop["capability_gap"] = True   # this refusal is a feature request, not an agent mistake
    # The id is minted INSIDE the lock, against the ids actually on disk — see `_proposals_lock`.
    with _proposals_lock(comp):
        props = _load_proposals(comp)
        prop["id"] = _next_proposal_id(props)
        props.append(prop)
        _save_proposals(comp, props)
    log_activity(comp, "proposal", (rationale or f"proposal for {scene_id or frame_id}")[:80],
                 actor=agent or "agent", frame_id=frame_id, scene_id=scene_id,
                 outcome="proposed" if gate_ok else "blocked", detail=None if gate_ok else (gate_out or "")[-200:])
    return prop


def list_proposals(comp: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """All proposals for a comp (optionally filtered by status: proposed|accepted|rejected|accept-failed)."""
    return [p for p in _load_proposals(comp) if status is None or p.get("status") == status]


def accept_proposal(comp: str, proposal_id: str) -> Dict[str, Any]:
    """Accept a proposal → apply its ops to the CANONICAL spec through the gate (build + revert-on-reject),
    stamp provenance on the touched scene, resolve the linked comment, mark the proposal accepted."""
    with _proposals_lock(comp):        # claim it under the lock: two accepts of one id must not both run
        props = _load_proposals(comp)
        p = next((x for x in props if x.get("id") == proposal_id), None)
        if not p:
            raise KeyError(f"proposal {proposal_id!r} not found")
        if p.get("status") != "proposed":
            return {"applied": False, "errors": f"proposal already {p.get('status')}", "proposal": p}
        p["status"] = "accepting"
        _save_proposals(comp, props)
    prov = p.get("provenance") or {}

    def mutate(fr):
        _apply_ops(fr, p["ops"])
        target = _find_scene(fr, p["scene_id"]) if p.get("scene_id") else fr
        if isinstance(target, dict):
            target.setdefault("meta", {}).setdefault("provenance", []).append(
                {"kind": "proposal", "id": proposal_id, **prov})

    res = _edit(comp, p["frame_id"], mutate, kind="proposal-accept", scene_id=p.get("scene_id"),
                summary=f"accept proposal {proposal_id}", actor=prov.get("agent") or "agent")
    if res.get("applied") and prov.get("comment_id"):
        try:
            resolve_comment(comp, p["frame_id"], prov["comment_id"], status="applied")
        except Exception:
            pass
    with _proposals_lock(comp):        # re-read: another writer may have appended while the gate ran
        props = _load_proposals(comp)
        p = next((x for x in props if x.get("id") == proposal_id), p)
        p["status"] = "accepted" if res.get("applied") else "accept-failed"
        if not res.get("applied"):
            p["gate_out"] = (res.get("errors") or "")[-600:]
        _save_proposals(comp, props)
    return {**res, "proposal": p}


def _spec_snapshot(comp: str) -> Dict[str, str]:
    """Every frame spec's bytes, right now. They are small JSON files; the whole essay is a few hundred
    KB, which is a cheap price for being able to undo a batch."""
    return {str(p): p.read_text(encoding="utf-8") for p in sorted(_frames_dir(comp).glob("*.spec.json"))}


def _restore_snapshot(snap: Dict[str, str]) -> None:
    for path, text in snap.items():
        Path(path).write_text(text, encoding="utf-8")


def accept_proposals(comp: str, proposal_ids: List[str], *, all_or_nothing: bool = False) -> Dict[str, Any]:
    """Accept a SET of proposals — the operation the human is actually performing when they review a
    batch of 25.

    Two things one-at-a-time acceptance could not give:

    * **Undo.** `_edit` reverts a single failed edit, but once N proposals are accepted there was no way
      back, and git is not available as a safety net here (a shared working tree with concurrent agents,
      and `git stash` is forbidden in this repo). Every accept run snapshots the frame specs first, so
      `rollback_token` can put the essay back exactly as it was.
    * **Atomicity when it is wanted.** `all_or_nothing=True` restores the snapshot if ANY proposal
      fails to apply — for the case where the accepted set is one coherent change and half of it is
      worse than none of it. Default stays permissive: a reviewer accepting 25 independent notes wants
      the 24 that work.

    Proposals are applied grouped by frame in their proposal order, so a frame is gated and rebuilt once
    per contiguous run rather than once per proposal.
    """
    snap = _spec_snapshot(comp)
    token = _comp_dir(comp) / f".hf_rollback.{int(time.time() * 1000)}.json"
    token.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    results, applied, failed = [], [], []
    for pid in proposal_ids:
        try:
            r = accept_proposal(comp, pid)
        except KeyError as e:
            r = {"applied": False, "errors": str(e)}
        results.append({"proposal_id": pid, **{k: r.get(k) for k in ("applied", "errors")}})
        (applied if r.get("applied") else failed).append(pid)
    rolled_back = False
    if all_or_nothing and failed:
        _restore_snapshot(snap)
        for pid in applied:                     # the specs are back; the proposals must agree
            try:
                with _proposals_lock(comp):
                    props = _load_proposals(comp)
                    p = next((x for x in props if x.get("id") == pid), None)
                    if p:
                        p["status"] = "proposed"
                    _save_proposals(comp, props)
            except Exception:
                pass
        rolled_back = True
    log_activity(comp, "batch", f"accepted {len(applied)}/{len(proposal_ids)} proposal(s)"
                                + (" — ROLLED BACK" if rolled_back else ""),
                 outcome="applied" if applied and not rolled_back else "rejected",
                 detail=f"failed: {', '.join(failed)}" if failed else None)
    return {"ok": not failed, "applied": applied, "failed": failed, "results": results,
            "rolled_back": rolled_back, "rollback_token": str(token)}


def rollback_batch(comp: str, rollback_token: str) -> Dict[str, Any]:
    """Restore every frame spec to the snapshot taken before an `accept_proposals` run, and rebuild the
    frames it touched. The undo that a 25-proposal review has to have and did not."""
    snap = json.loads(Path(rollback_token).read_text(encoding="utf-8"))
    _restore_snapshot(snap)
    rebuilt, errors = [], []
    for path in snap:
        fid = Path(path).name[: -len(".spec.json")]
        try:
            ok, out = _gate_and_build(comp, Path(path))
            (rebuilt if ok else errors).append(fid if ok else f"{fid}: {out[-160:]}")
        except Exception as e:
            errors.append(f"{fid}: {type(e).__name__}: {e}")
    log_activity(comp, "batch", f"rolled back to {Path(rollback_token).name}",
                 outcome="applied" if not errors else "error", detail="; ".join(errors)[:300] or None)
    return {"ok": not errors, "restored": len(snap), "rebuilt": rebuilt, "errors": errors}


def reject_proposal(comp: str, proposal_id: str, reason: str = "") -> Dict[str, Any]:
    """Reject a proposal (discard it) and REOPEN the linked comment so it can be re-dispatched."""
    with _proposals_lock(comp):
        props = _load_proposals(comp)
        p = next((x for x in props if x.get("id") == proposal_id), None)
        if not p:
            raise KeyError(f"proposal {proposal_id!r} not found")
        p["status"] = "rejected"
        if reason:
            p["reject_reason"] = reason
        _save_proposals(comp, props)
    prov = p.get("provenance") or {}
    if prov.get("comment_id"):
        try:
            resolve_comment(comp, p["frame_id"], prov["comment_id"], status="open", reason=reason or None)
        except Exception:
            pass
    log_activity(comp, "proposal", f"rejected {proposal_id}", frame_id=p["frame_id"], scene_id=p.get("scene_id"),
                 outcome="rejected", detail=reason[:200] if reason else None)
    return {"rejected": proposal_id, "proposal": p}


def _build_trial_html(comp: str, frame_id: str, trial_frame: Dict[str, Any]) -> str:
    """Compose a TRIAL frame's HTML (ops already applied to `trial_frame`) via author.py, to a scratch dir —
    the CANONICAL frame HTML is never touched. Returns the HTML string; raises on gate failure."""
    scratch = _comp_dir(comp) / "compositions" / "_preview" / "_trial_build"
    (scratch / "frames").mkdir(parents=True, exist_ok=True)
    tmp = scratch / f".{frame_id}.trial.spec.json"
    # PASS THE THEME EXPLICITLY. `author.resolve_theme` falls back to reading `hyperframes.json` from
    # `Path(out_dir).parents[1]`, which assumes `<comp>/compositions/frames`. This scratch build is
    # `<comp>/compositions/_preview/_trial_build/frames`, so `parents[1]` is `_preview` — no
    # hyperframes.json — and every preview silently composed in the DEFAULT theme instead of the
    # essay's. Found by a cold agent on homer-hf (`dark-botanical`): its previews came out
    # highlighter-editorial yellow, and it reported a real edit as breaking the theme before realising
    # the preview was the thing that was wrong. A review artifact that lies about colour is worse than
    # no preview, because the reviewer believes it.
    theme = _comp_theme(comp)
    spec_obj = {"frames": [trial_frame]}
    if theme:
        spec_obj["theme"] = theme            # survives even if --theme is ever dropped
    tmp.write_text(json.dumps(spec_obj), encoding="utf-8")
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", str(AUTHOR), "--spec", str(tmp),
                            "--out-dir", str(scratch / "frames")]
                           + (["--theme", theme] if theme else []),
                           cwd=str(BRIDGE), capture_output=True, text=True, encoding="utf-8", errors="replace")
    finally:
        tmp.unlink(missing_ok=True)
    out_html = scratch / "frames" / f"{frame_id}.html"
    if r.returncode != 0 or not out_html.exists():
        raise RuntimeError((r.stdout + r.stderr).strip()[-400:] or "trial build failed")
    return out_html.read_text(encoding="utf-8")


def proposal_preview(comp: str, proposal_id: str, at: Optional[float] = None) -> Dict[str, Any]:
    """Render a still PREVIEW of what a proposal would look like — WITHOUT touching canonical (ops applied
    to a COPY, built to a scratch dir, snapshot). Lets the human eyeball the end result before accepting
    (esp. important for full-auto batch edits). Lazy by design: call on review + cache the PNG. Snapshots
    the EDITED scene's window (start + 60% of its dur) unless `at` is given."""
    props = _load_proposals(comp)
    p = next((x for x in props if x.get("id") == proposal_id), None)
    if not p:
        raise KeyError(f"proposal {proposal_id!r} not found")
    spec, info = load_frame_spec(comp, p["frame_id"])
    trial = copy.deepcopy(spec["frames"][info["i"]])
    _apply_ops(trial, p.get("ops") or [])                       # on a COPY — canonical untouched
    sc = next((s for s in trial.get("scenes", []) if s.get("id") == p.get("scene_id")), None)
    if at is None:
        at = (float(sc.get("start", 0)) + 0.6 * float(sc.get("dur", 5))) if sc else float(trial.get("dur", 5)) * 0.5
    html = _build_trial_html(comp, p["frame_id"], trial)
    pdir = _scaffold_preview(comp, p["frame_id"], html_text=html, preview_id=f"_prop_{proposal_id}")
    # Inject the frame's VIDEO grounds, as `render_frame` does. A `media_ground` video composes to a
    # TRANSPARENT div (the clip is meant to be root-mounted), so without this every footage-grounded
    # scene previewed as an empty plate — i.e. the preview was blank on exactly the scenes a reviewer
    # most needs to see. (A seeked <video> still may not decode into a snapshot; that is what
    # `render_scene` is for. Injecting is what makes the difference visible when it can.)
    try:
        from nolan.hyperframes.incremental import inject_grounds
        gs = []
        for s in trial.get("scenes", []):
            g = (s.get("data") or {}).get("ground") or {}
            if g.get("kind") == "video" and g.get("src"):
                gs.append({"src": g["src"], "start": round(float(s.get("start", 0) or 0), 3),
                           "dur": round(float(s.get("dur", 0) or 0), 3)})
        if gs:
            idx = pdir / "index.html"
            idx.write_text(inject_grounds(idx.read_text(encoding="utf-8"), gs), encoding="utf-8")
    except Exception:
        pass
    r = subprocess.run(["npx", "--yes", "hyperframes@latest", "snapshot", str(pdir),
                        "--at", f"{at:g}", "--no-end", "--describe", "false"],
                       cwd=str(pdir), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       shell=(os.name == "nt"))
    snaps = sorted((pdir / "snapshots").glob("frame-*.png")) if (pdir / "snapshots").is_dir() else []
    return {"ok": r.returncode == 0 and bool(snaps), "png": str(snaps[0]) if snaps else None,
            "at": round(float(at), 2), "output": (r.stdout + r.stderr).strip()[-400:]}


# ------------------------------------------------------------------ preview / render (npx scaffold)

_ASSET_REF_RE = re.compile(r"assets/[A-Za-z0-9._\-/]+")


def _referenced_assets(comp: str, frame_id: str, html_text: Optional[str]) -> List[str]:
    """The `assets/…` paths ONE frame's preview actually needs, as comp-relative strings.

    Scans the composed HTML *and* the frame SPEC: a video ground composes to a TRANSPARENT div (the clip
    is root-injected later by `render_frame`/`incremental`), so its path appears only in the spec. The
    frame's own voice wav is added from audio_meta because `_scaffold_preview` mounts it as a root <audio>.

    Why this exists: the old staging copied `assets/**` wholesale on EVERY snapshot/preview/render call.
    Measured on the-diamond-illusion-v3 — an 856 MB asset tree, 12 scratch dirs, 7.5 GB of `_preview` —
    so the "cheap" verify loop cost minutes of file copying per still and was abandoned on exactly the
    footage-heavy comps that most need it. Per frame the real requirement is 7-17 files (9-99 MB).
    """
    refs = set(_ASSET_REF_RE.findall(html_text or ""))
    try:                                                  # the spec carries paths the HTML can't (video grounds)
        spec, info = load_frame_spec(comp, frame_id)
        refs |= set(_ASSET_REF_RE.findall(json.dumps(spec["frames"][info["i"]], default=str)))
    except Exception:
        pass
    meta_f = _comp_dir(comp) / "audio_meta.json"
    if meta_f.exists():
        try:
            meta = json.loads(meta_f.read_text(encoding="utf-8"))
            m = re.match(r"(\d+)", str(frame_id))
            voice = next((v for v in meta.get("voices", []) if v.get("frame") == (int(m.group(1)) if m else None)),
                         None)
            if voice and voice.get("path"):
                refs.add(str(voice["path"]).replace("\\", "/"))
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    return sorted(r for r in refs if r.startswith("assets/") and not r.endswith("/"))


def _stage_asset(src: Path, dest: Path) -> None:
    """Materialise ONE asset into a scratch dir as cheaply as the filesystem allows: reuse an identical
    existing file, else hardlink (NTFS + DrvFs both support it, and unlike a symlink it is not a reparse
    point, so Windows and WSL can both stat it — see CLAUDE.md), else copy. Previews only ever READ these
    files, so sharing the inode is safe; every asset EDIT path writes a new file under a new name."""
    try:
        s = src.stat()
    except OSError:
        return
    if dest.exists():
        d = dest.stat()
        if d.st_size == s.st_size and (getattr(d, "st_ino", 0) == getattr(s, "st_ino", -1)
                                       or int(d.st_mtime) == int(s.st_mtime)):
            return                                        # already staged (same inode, or same size+mtime)
        dest.unlink(missing_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dest)
    except OSError:
        dest.write_bytes(src.read_bytes())


def prune_previews(comp: str) -> Dict[str, Any]:
    """Delete the per-frame/per-proposal preview scratch under <comp>/compositions/_preview.

    Scratch is disposable by construction (it is rebuilt from the spec on the next call), and comps built
    before assets were staged by reference carry whole-tree copies — 7.5 GB on one measured comp. Returns
    what was freed so the caller can report it rather than silently reclaiming disk."""
    root = _comp_dir(comp) / "compositions" / "_preview"
    if not root.is_dir():
        return {"removed": 0, "bytes": 0}
    import shutil
    n = total = 0
    for d in list(root.iterdir()):
        try:
            total += sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            shutil.rmtree(d, ignore_errors=True)
            n += 1
        except OSError:
            pass
    return {"removed": n, "bytes": total}


def _scaffold_preview(comp: str, frame_id: str, html_text: Optional[str] = None,
                      preview_id: Optional[str] = None, dur_override: Optional[float] = None) -> Path:
    """Build a throwaway single-frame hyperframes project so `npx hyperframes snapshot|render` can target
    ONE frame in isolation (cross-platform: self-contained headless Chrome). Copies the frame HTML (+ any
    vendor dir a geo/diagram scene needs) so relative paths resolve. `html_text` overrides the frame HTML
    (a TRIAL build for a proposal preview — canonical HTML untouched); `preview_id` isolates the scratch dir."""
    fdir = _frames_dir(comp)
    html = fdir / f"{frame_id}.html"
    if html_text is None and not html.exists():
        recompose_frame(comp, frame_id)
    spec, info = load_frame_spec(comp, frame_id)
    dur = float(dur_override if dur_override else spec["frames"][info["i"]].get("dur", 5))
    pdir = _comp_dir(comp) / "compositions" / "_preview" / (preview_id or frame_id)
    (pdir / "compositions" / "frames").mkdir(parents=True, exist_ok=True)
    (pdir / "compositions" / "frames" / f"{frame_id}.html").write_text(
        html_text if html_text is not None else html.read_text(encoding="utf-8"), encoding="utf-8")
    vend = _comp_dir(comp) / "vendor"
    if not vend.is_dir():
        vend = BRIDGE / "vendor"
    if vend.is_dir():
        (pdir / "vendor").mkdir(exist_ok=True)
        for f in vend.glob("*"):
            if f.is_file():
                (pdir / "vendor" / f.name).write_bytes(f.read_bytes())
    # Stage ONLY the assets this frame references (see `_referenced_assets`) — never the whole tree.
    cdir = _comp_dir(comp)
    for rel in _referenced_assets(comp, frame_id,
                                  html_text if html_text is not None else
                                  (html.read_text(encoding="utf-8") if html.exists() else "")):
        src = cdir / rel
        if src.is_file():
            _stage_asset(src, pdir / rel)
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
    _hj = {}
    try:                                               # preserve a theme new_essay wrote (author.py reads it)
        _hj = json.loads((pdir / "hyperframes.json").read_text(encoding="utf-8"))
    except Exception:
        _hj = {}
    _hj["paths"] = {"blocks": "compositions"}
    (pdir / "hyperframes.json").write_text(json.dumps(_hj), encoding="utf-8")
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


def scene_window_frame(fr: Dict[str, Any], scene_id: str, seconds: Optional[float] = None
                       ) -> Tuple[Dict[str, Any], float]:
    """PURE: a one-scene frame, retimed to start at 0 — the unit a scene-level render needs.

    Why by RECOMPOSITION and not by windowing the frame's HTML: the composed frame carries its scene
    times in two places, `data-start` attributes AND GSAP position parameters inside a generated
    `<script>` (`tl.fromTo(…, 6.40)`), plus a `tl.to({}, {duration: N})` spacer. Shifting all three with
    string surgery on generated JS is exactly the kind of second dialect that drifts. Re-composing a
    frame that contains only this scene reuses the composer, which is the thing that knows.

    `seconds` caps the window — a verify render wants 2-3 seconds of a 19-second hold, not the hold.
    """
    sc = next((s for s in fr.get("scenes", []) if s.get("id") == scene_id), None)
    if sc is None:
        raise KeyError(f"scene {scene_id!r} not in frame {fr.get('id')!r}")
    sc = copy.deepcopy(sc)
    dur = float(sc.get("dur", 5) or 5)
    if seconds:
        dur = min(dur, float(seconds))
    sc["start"], sc["dur"] = 0, round(dur, 3)
    return {**{k: v for k, v in fr.items() if k != "scenes"}, "dur": round(dur, 3), "scenes": [sc]}, dur


def render_scene(comp: str, frame_id: str, scene_id: str, seconds: float = 3.0,
                 out: Optional[str] = None) -> Dict[str, Any]:
    """Render JUST one scene's window — the verify tier between a still and a full frame render.

    A still answers most questions in seconds, but not the ones a still structurally cannot: a seeked
    `<video>` does not decode into a snapshot, so every footage-grounded scene previews black, and a
    note about MOTION has nothing to look at. Those were the cases that forced a full frame render
    (minutes) to check one scene's geometry.

    Use it exactly there — video ground, or a motion note. Everything else stays on `snapshot_frame`."""
    spec, info = load_frame_spec(comp, frame_id)
    trial, dur = scene_window_frame(spec["frames"][info["i"]], scene_id, seconds)
    html = _build_trial_html(comp, frame_id, trial)
    pdir = _scaffold_preview(comp, frame_id, html_text=html, preview_id=f"_scene_{scene_id}",
                             dur_override=dur)
    from nolan.hyperframes.incremental import inject_grounds
    grounds = []
    for s in trial["scenes"]:
        d = s.get("data", {}) or {}
        g = d.get("ground") or {}
        src = g.get("src") if (g.get("kind") == "video" and g.get("src")) else None
        if not src and isinstance(d.get("backdrop"), str) \
                and d["backdrop"].lower().endswith((".mp4", ".mov", ".webm")):
            src = d["backdrop"]
        if src:
            grounds.append({"src": src, "start": 0, "dur": round(dur, 3)})
    idx = pdir / "index.html"
    if grounds:
        idx.write_text(inject_grounds(idx.read_text(encoding="utf-8"), grounds), encoding="utf-8")
    outp = out or str(_frames_dir(comp) / f"{frame_id}.{scene_id}.scene.mp4")
    r = subprocess.run(["npx", "--yes", "hyperframes@latest", "render", str(pdir), "--output", outp],
                       cwd=str(pdir), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       shell=(os.name == "nt"))
    return {"ok": r.returncode == 0 and Path(outp).exists(),
            "mp4": outp if Path(outp).exists() else None, "dur": round(dur, 3),
            "grounds": len(grounds), "output": (r.stdout + r.stderr).strip()[-600:]}


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
    """Full-frame render (the whole beat clip) — the on-demand step after snapshot iteration. Reconstructs the
    frame's VIDEO grounds from the spec and injects them, so a JUST-ADDED/CHANGED video ground previews
    correctly: a `media_ground` video composes to a TRANSPARENT ground in the frame HTML (the clip is meant to
    be root-injected), so without this the preview would show nothing where the video should be."""
    from nolan.hyperframes.incremental import frame_grounds, inject_grounds
    try:
        recompose_frame(comp, frame_id)                  # frame HTML reflects the CURRENT spec (e.g. a social_card
    except Exception:                                    # text edit), not whatever was last built — best-effort
        pass
    pdir = _scaffold_preview(comp, frame_id)
    idx = pdir / "index.html"
    grounds = frame_grounds(comp, frame_id)
    if grounds:
        idx.write_text(inject_grounds(idx.read_text(encoding="utf-8"), grounds), encoding="utf-8")
    outp = out or str(_frames_dir(comp) / f"{frame_id}.preview.mp4")
    r = subprocess.run(["npx", "--yes", "hyperframes@latest", "render", str(pdir),
                        "--output", outp],
                       cwd=str(pdir), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       shell=(os.name == "nt"))  # Windows: `npx` is npx.cmd -> needs a shell, else WinError 2
    return {"ok": r.returncode == 0 and Path(outp).exists(),
            "mp4": outp if Path(outp).exists() else None,
            "output": (r.stdout + r.stderr).strip()[-800:]}
