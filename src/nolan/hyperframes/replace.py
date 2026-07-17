"""Per-scene asset REPLACE — the /hyperframes ✨ Replace sheet.

From a scene's OWN context (its narration transcript + the current asset's stored gen_prompt + the project
theme), derive an editable gen prompt + stock query, then fan out two ways:
  • STOCK  — searched instantly when the sheet opens (cheap).
  • GEN    — ComfyUI, on a one-tap "Generate ×N" (GPU-costly, so never auto-fired).
Every candidate lands in the pool TAGGED to the scene (add_scene_asset → scene shortlist + pool.json), so
nothing is wasted; picking one USES it through the normal apply flow (auto-fit + re-render).

Reuses nolan.acquire's providers (build_context: stock search + gated download + krea2/ComfyUI generate),
so this is a thin, scene-scoped front door to the same machinery the whole-project pool build uses.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .edit import (_comp_dir, load_frame_spec, _find_scene, asset_pool_meta, add_scene_asset,
                   frame_transcripts, _VID_EXT, _IMG_EXT)

REPO = Path(__file__).resolve().parents[3]                 # src/nolan/hyperframes/replace.py → repo root
_MEDIA_FIELDS = ("ground", "backdrop", "image", "source")  # priority order for "the scene's main asset"
_CTX: Dict[str, Any] = {}                                  # comp -> (Context, gen_style); build_context is heavyish
_STOP = set("the a an and or of to in on for with your you has have had is are was were it its as at by "
            "that this these those from into out up down over under s t".split())


def _theme(comp: str) -> str:
    try:
        return json.loads((_comp_dir(comp) / "hyperframes.json").read_text(encoding="utf-8")).get("theme") \
            or "highlighter-editorial"
    except Exception:
        return "highlighter-editorial"


def _context(comp: str):
    """(Context, gen_style) with stock + gen + download wired, cached per comp. load_config is read from the
    REPO nolan.yaml explicitly (not CWD) — the acquire engine is CWD-sensitive (ComfyUI port lives there)."""
    if comp not in _CTX:
        from nolan.config import load_config
        from nolan.acquire import build_context, gen_style_for
        cfg = load_config(REPO / "nolan.yaml")
        gs = gen_style_for(_theme(comp))
        _CTX[comp] = (build_context(cfg, gen_style=gs), gs)
    return _CTX[comp]


def _current_asset(data: Dict) -> tuple:
    """(field, src, kind) of the scene's main media asset — the first of ground/backdrop/image/source that
    points at a real media file. (field, None, 'image') when the scene has no media asset yet."""
    for f in _MEDIA_FIELDS:
        v = data.get(f)
        src = v.get("src") if isinstance(v, dict) else (v if isinstance(v, str) else None)
        if isinstance(src, str) and Path(src).suffix.lower() in (_VID_EXT + _IMG_EXT):
            return f, src, ("video" if Path(src).suffix.lower() in _VID_EXT else "image")
    return (data and _MEDIA_FIELDS[0]), None, "image"


def _keywords(text: str, k: int = 8) -> str:
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", text or "") if w.lower() not in _STOP]
    return " ".join(words[:k]) or (text or "").strip()[:60]


def brief(comp: str, frame_id: str, scene_id: str) -> Dict[str, Any]:
    """The editable starting point for a replace: which asset field, its current src, the modality, and a
    prompt/query DERIVED from the scene (the old asset's gen_prompt if it was generated, else the narration)."""
    spec, info = load_frame_spec(comp, frame_id)
    sc = _find_scene(spec["frames"][info["i"]], scene_id)
    d = sc.get("data", {}) or {}
    field, cur, kind = _current_asset(d)
    old_gen = (asset_pool_meta(comp).get(Path(cur).name) or {}).get("gen_prompt") if cur else None
    transcript = (frame_transcripts(comp, frame_id) or {}).get(scene_id, "")
    subject = (old_gen or "").strip() or transcript.strip() or str(d.get("kicker") or d.get("title") or "").strip()
    from nolan.acquire import gen_style_for                 # pure (theme→style) — no build_context here
    return {"field": field, "current": cur, "modality": kind, "theme": _theme(comp), "gen_style": gen_style_for(_theme(comp)),
            "transcript": transcript, "prompt": subject[:280], "query": _keywords(subject or transcript)}


_BRIEF: Dict[str, Any] = {}   # comp -> VisualBrief (the project's ONE look; derived once, cached)


def style_presets() -> List[Dict[str, str]]:
    """The text-to-image STYLE presets (BONUS_PROMPT_STYLE_* — Photorealism / Film Noir / Ghibli / …) the gen
    sheet's dropdown offers; the selected one is prepended to the prompt to set the tone."""
    try:
        return json.loads((Path(__file__).with_name("style_presets.json")).read_text(encoding="utf-8"))
    except Exception:
        return []


def enhance(comp: str, frame_id: str, scene_id: str, prompt: str, style: str = "") -> Dict[str, str]:
    """STEP 1 of the two-step gen: art-direct a raw prompt into the FINAL ComfyUI prompt — the LLM disambiguates
    the subject, the project's VisualBrief wraps a consistent medium/reference/era, and the chosen style preset
    is prepended. Returns {prompt, negative}; the user then tweaks it (step 2) and generates. Falls back to the
    raw prompt if the art-direction LLM is unavailable, so gen never blocks."""
    import asyncio
    from nolan.config import load_config
    from nolan.acquire import gen_style_for
    from nolan.acquire.art_direction import derive_brief, compose_prompt, load_or_none, VisualBrief
    theme = _theme(comp)
    cfg = load_config(REPO / "nolan.yaml")
    gen_style = gen_style_for(theme)
    if comp not in _BRIEF:                                  # the project's ONE look — saved by the pool build, else derive once
        b = load_or_none(_comp_dir(comp))
        if b is None:
            try:
                b = asyncio.run(derive_brief(cfg, subject=prompt, theme=theme, style_default=gen_style))
            except Exception:
                b = VisualBrief(style=gen_style)
        _BRIEF[comp] = b
    try:
        pos, neg = asyncio.run(compose_prompt(cfg, {"gen_prompt": prompt}, _BRIEF[comp], essay_context=theme))
    except Exception:
        pos, neg = prompt, ""
    final = f"{style.strip()}, {pos}" if style.strip() else pos
    return {"prompt": final[:1400], "negative": neg}


def _land(comp: str, frame_id: str, scene_id: str, path: Path, source: str,
          attribution: Optional[Dict] = None) -> Optional[Dict]:
    """Land a candidate file into the pool + the scene's shortlist; tag its source (stock|gen) for the grid."""
    try:
        r = add_scene_asset(comp, frame_id, scene_id, path.name, path.read_bytes())
        r["source"] = source
        if attribution:
            r["attribution"] = {k: v for k, v in attribution.items() if v}
        return r
    except Exception:                                      # pragma: no cover - a bad candidate shouldn't abort
        return None


def search(comp: str, frame_id: str, scene_id: str, query: str, n: int = 6, modality: str = "image") -> List[Dict]:
    """Stock search for `query` → download up to n → land tagged to the scene. Returns the pool entries."""
    ctx, _ = _context(comp)
    if not (ctx.search_stock and ctx.download and (query or "").strip()):
        return []
    q = _keywords(query, k=10)                             # stock matches literally → keywords beat a full sentence
    cand_dir = _comp_dir(comp) / "capture" / "_replace"
    cand_dir.mkdir(parents=True, exist_ok=True)
    out: List[Dict] = []
    for c in (ctx.search_stock({"media_type": modality, "queries": [q]}, n) or []):
        if len(out) >= n:
            break
        if c.path is None and not ctx.download(c, cand_dir):
            continue
        if c.path and Path(c.path).exists():
            r = _land(comp, frame_id, scene_id, Path(c.path), "stock",
                      {"provider": (c.meta or {}).get("source"), "by": (c.meta or {}).get("photographer"),
                       "url": (c.meta or {}).get("source_url")})
            if r:
                out.append(r)
    return out


def generate(comp: str, frame_id: str, scene_id: str, prompt: str, n: int = 3,
             negative: Optional[str] = None, log=None) -> List[Dict]:
    """ComfyUI-generate n images from `prompt` → land tagged to the scene. Background job (GPU, ~n×7s)."""
    ctx, gen_style = _context(comp)
    _log = log or (lambda _m: None)
    if not (ctx.generate and (prompt or "").strip()):
        _log("generation unavailable (no ComfyUI / empty prompt)")
        return []
    tmp = _comp_dir(comp) / "capture" / "_replace"
    tmp.mkdir(parents=True, exist_ok=True)
    out: List[Dict] = []
    for i in range(n):
        _log(f"generating {i + 1}/{n}…")
        p = tmp / f"gen_{scene_id}_{i}.png"
        try:
            if ctx.generate(prompt, p, negative=negative) and p.exists():
                r = _land(comp, frame_id, scene_id, p, "gen", {"gen_prompt": prompt, "style": gen_style})
                if r:
                    out.append(r)
                    _log(f"  ✓ {r.get('name')}")
        except Exception as e:                             # pragma: no cover - keep going on a single failure
            _log(f"  ⚠ gen {i + 1} failed: {type(e).__name__}: {e}")
    _log(f"done: {len(out)}/{n} generated")
    return out
