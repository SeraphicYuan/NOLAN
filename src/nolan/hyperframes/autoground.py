"""#3 — auto-select ambient GROUNDS for long, ungrounded data-viz scenes from the project POOL.

A long data hold reads dead on a flat field; a thematically-apt image behind it (with Ken-Burns) — a
data-centre aerial behind a spend chart, redacted court dockets behind a shell-company web, cracked
earth behind a "running dry" stat — lifts it (Layer 3 of the reveal-sync program). Hand-picking those is
taste, so this is the PAIRING step: for each ungrounded data scene held long enough to go stale, match
the scene's text to the pool images and set `data.ground`.

RESTRAINT BY DEFAULT — a ground is EARNED, not mandatory. Not every data/stat frame wants a photo: a
stark number on a clean field often hits harder than one buried under one, and over-grounding reads muddy
and samey. So this only CANDIDATES the long holds (the stale-risk ones — a short or dense beat is fine
bare), and when nothing genuinely fits it LEAVES THE FRAME CLEAN — it never papers or forces a mismatched
image (both are worse than clean). The `--apply` result is a PROPOSAL to curate, not a mandate.

Routing: the match is semantic (a spend chart wants *data-centre* imagery — no shared keyword), so the
primary picker is an LLM judgment over the pool captions (cheap, one batched call) that returns "none"
when nothing fits; a keyword scorer is the offline fallback. The chosen ground renders through
compose._data_ground's shaped legibility veil (#4).

CLI:  python -X utf8 -m nolan.hyperframes.autoground <comp> [--apply] [--no-llm] [--min-dur 8]
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

try:
    from nolan.hyperframes.sync import _DATAVIZ
except Exception:                                            # keep the operator importable standalone
    _DATAVIZ = {"chart", "stat", "sankey", "pie", "funnel", "quadrant", "cycle", "spectrum", "scale",
                "spans", "venn", "connection_board"}

_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "is", "it", "that", "this", "for", "with",
         "vs", "on", "at", "by", "as", "all", "per", "its", "our", "your", "not", "no"}


def _comp_dir(comp) -> Path:
    p = Path(comp)
    if p.exists() and (p / "compositions").exists():
        return p
    from nolan.hyperframes.edit import _project_dir       # resolve a bare comp id → its dir
    return Path(_project_dir(comp))


def _pool_images(comp_dir: Path) -> List[Dict]:
    """Usable still images in the project pool that physically exist in assets/ — {file, caption}."""
    pj = comp_dir / "pool.json"
    if not pj.exists():
        return []
    pool = json.loads(pj.read_text(encoding="utf-8"))
    items = pool if isinstance(pool, list) else (pool.get("items") or pool.get("assets") or [])
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        f = str(it.get("file") or "")
        if not f.lower().endswith((".jpg", ".jpeg", ".png")) or it.get("usable") is False:
            continue
        if not (comp_dir / "assets" / f).exists():
            continue
        cap = it.get("caption") or it.get("desc") or it.get("description") or it.get("query") or ""
        out.append({"file": f, "caption": cap.strip()})
    return out


def _scene_text(sc: Dict) -> str:
    d = sc.get("data", {}) or {}
    return " ".join(str(d.get(k, "")) for k in ("kicker", "title", "titleHi", "center", "headline")).strip()


def _toks(s: str) -> set:
    return {t for t in re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split() if len(t) >= 4 and t not in _STOP}


def _keyword_pick(sc: Dict, pool: List[Dict]) -> Optional[str]:
    """Offline fallback: the pool image sharing the most distinctive content words with the scene text.
    Returns a file only on a real overlap (≥1 shared content token), else None (→ paper)."""
    q = _toks(_scene_text(sc))
    if not q:
        return None
    best, bf = 0, None
    for img in pool:
        sc_shared = len(q & _toks(img["caption"]))
        if sc_shared > best:
            best, bf = sc_shared, img["file"]
    return bf if best >= 1 else None


def _needs_ground(sc: Dict, min_dur: float) -> bool:
    if sc.get("type") not in _DATAVIZ:
        return False
    g = (sc.get("data", {}) or {}).get("ground")
    grounded = isinstance(g, dict) and g.get("kind") not in (None, "color", "flat")
    return (not grounded) and float(sc.get("dur", 0) or 0) >= min_dur


def _llm_pick(needing: List, pool: List[Dict]) -> Dict[str, str]:
    """One batched LLM call → {uid: pool_file} for the scenes it can place. `needing` is a list of
    (uid, scene) — uid is frame-qualified ('01-hook/s2') because scene ids REPEAT across frames (every
    frame has an s2), so a bare id collides. Picks the image whose SUBJECT evokes the scene's topic
    (thematic, not literal); omits / 'none' when nothing fits. {} on any failure."""
    try:
        import asyncio
        from nolan.config import load_config
        from nolan.llm import create_text_llm
        llm = create_text_llm(load_config())
    except Exception:
        return {}
    catalog = "\n".join(f"- {img['file']}: {img['caption']}" for img in pool)
    scenes = "\n".join(f'- {uid}: "{_scene_text(sc)}" (a {sc.get("type")} block)' for uid, sc in needing)
    prompt = (
        "You are art-directing a video essay. Each SCENE below is a data chart/diagram that will hold on "
        "screen for several seconds; pick an ambient background IMAGE from the POOL to sit behind it (dimmed, "
        "with a slow Ken-Burns), so the hold isn't a dead flat field.\n"
        "Choose the image whose SUBJECT evokes the scene's topic — thematic, not literal (a spending chart "
        "wants a data-centre / money image; a shell-company web wants legal documents; a 'running dry' stat "
        "wants parched earth). Only pick an image that GENUINELY fits — if nothing in the pool suits a scene, "
        "return \"none\" for it (a bare field beats a mismatched photo). Do NOT reuse one image for many "
        "scenes just to fill them.\n\n"
        f"POOL:\n{catalog}\n\nSCENES (the key before the colon is the exact id to return):\n{scenes}\n\n"
        'Return ONLY JSON mapping each scene key to a file or "none": {"01-hook/s2": "a2_00.jpg", ...}')
    sys_p = "You return only strict JSON. No prose."
    try:
        raw = asyncio.run(llm.generate(prompt, sys_p))
        m = re.search(r"\{.*\}", raw, re.S)
        obj = json.loads(m.group(0)) if m else {}
        valid = {img["file"] for img in pool}
        return {k: v for k, v in obj.items() if isinstance(v, str) and v in valid}
    except Exception:
        return {}


def ground_data_scenes(comp, apply: bool = False, min_dur: float = 8.0, use_llm: bool = True,
                       dim: float = 0.62) -> Dict:
    """Assign ambient grounds to long ungrounded data scenes. `apply` writes the specs (+ recompose);
    otherwise a dry-run report. Returns {grounded: [...], paper: [...], scanned, applied}."""
    comp_dir = _comp_dir(comp)
    pool = _pool_images(comp_dir)
    spec_files = sorted((comp_dir / "compositions" / "frames").glob("*.spec.json"))
    picks_by_uid: Dict[str, str] = {}
    needing_all: List = []                                   # (uid, scene) — uid is frame-qualified
    specs = []
    for sf in spec_files:
        spec = json.loads(sf.read_text(encoding="utf-8"))
        specs.append((sf, spec))
        for fr in spec.get("frames", []):
            for sc in fr.get("scenes", []):
                if _needs_ground(sc, min_dur):
                    needing_all.append((f"{fr.get('id')}/{sc.get('id')}", sc))
    if use_llm and pool and needing_all:
        picks_by_uid = _llm_pick(needing_all, pool)

    grounded, clean = [], []
    for sf, spec in specs:
        changed = False
        for fr in spec.get("frames", []):
            for sc in fr.get("scenes", []):
                if not _needs_ground(sc, min_dur):
                    continue
                sid = sc.get("id")
                uid = f"{fr.get('id')}/{sid}"
                f = picks_by_uid.get(uid) or (_keyword_pick(sc, pool) if pool else None)
                if f:
                    sc.setdefault("data", {})["ground"] = {
                        "kind": "image", "src": f"assets/{f}", "kenburns": [1.0, 1.11], "dim": dim}
                    grounded.append({"frame": fr.get("id"), "scene": sid, "block": sc.get("type"),
                                     "dur": round(float(sc.get("dur", 0) or 0), 1), "src": f})
                    changed = True
                else:
                    # nothing fits → LEAVE IT CLEAN (a bare field beats paper/a mismatched photo)
                    clean.append({"frame": fr.get("id"), "scene": sid, "block": sc.get("type"),
                                  "dur": round(float(sc.get("dur", 0) or 0), 1)})
        if apply and changed:
            raw = sf.read_bytes()
            crlf = b"\r\n" in raw
            out = (json.dumps(spec, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            if crlf:
                out = out.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            sf.write_bytes(out)

    if apply and grounded:
        try:
            from nolan.hyperframes.edit import recompose_frame
            for fid in {g["frame"] for g in grounded}:
                recompose_frame(str(comp_dir), fid)
        except Exception:
            pass
    return {"scanned": len(needing_all), "grounded": grounded, "left_clean": clean,
            "pool": len(pool), "llm_picks": len(picks_by_uid), "applied": bool(apply)}


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.autoground")
    ap.add_argument("comp")
    ap.add_argument("--apply", action="store_true", help="write specs + recompose (else dry-run)")
    ap.add_argument("--no-llm", action="store_true", help="deterministic keyword pick only (no LLM call)")
    ap.add_argument("--min-dur", type=float, default=8.0, help="only ground data scenes at least this long")
    a = ap.parse_args()
    rep = ground_data_scenes(a.comp, apply=a.apply, min_dur=a.min_dur, use_llm=not a.no_llm)
    print(f"auto-ground: {rep['scanned']} long ungrounded data scene(s); pool {rep['pool']} image(s); "
          f"LLM matched {rep['llm_picks']}. {'APPLIED' if rep['applied'] else 'DRY-RUN'}")
    for g in rep["grounded"]:
        print(f"  ✓ {g['frame']}/{g['scene']} ({g['block']}, {g['dur']}s) → {g['src']}")
    for c in rep["left_clean"]:
        print(f"  · {c['frame']}/{c['scene']} ({c['block']}, {c['dur']}s) → left CLEAN (nothing fit — a bare field beats a forced ground)")


if __name__ == "__main__":
    main()
