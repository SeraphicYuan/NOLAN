"""S3 — auto-select ambient GROUNDS for long, ungrounded holds from the project POOL (image OR video).

A scene held longer than `_LONG_HOLD_S` (5s) on a flat field reads DEAD — whether it's a text statement
("You go to look it up" on bare paper) or a stat on a flat field. A thematically-apt image/clip behind it
(dimmed, with a slow push) lifts it: a data-centre aerial behind a spend chart, a Big-Hole mine behind
"the ground kept giving", a padlock behind "under US antitrust law".

RESTRAINT BY DEFAULT — a ground is EARNED, not mandatory. This only CANDIDATES the long holds on the six
blocks that actually RENDER a ground (`_GROUND_BLOCKS` — the composer fns that call media_ground); a short
or dense beat is fine bare, and the other 44 templates carry their own visual and would silently DROP the
field. When NOTHING in the pool genuinely fits a scene it LEAVES THE FRAME CLEAN: a bare
field beats a forced, mismatched photo (both are worse than clean type). Never forces.

Routing: the match is semantic (a spend chart wants *data-centre* imagery — no shared keyword), so the
primary picker is an LLM judgment over the pool captions (cheap, one batched call) that returns "none" when
nothing fits; a keyword scorer is the offline fallback. The chosen ground renders through the composer's
media_ground (image → `kb` Ken-Burns; video → looped clip, freeze-healed by assemble-media).

Wiring: the finish DAG calls `ground_data_scenes(comp, apply=True, min_dur=5, recompose=False)` AFTER
word-sync (durations known) and BEFORE its recompose step (which rebuilds the HTML from the specs we write).

CLI:  python -X utf8 -m nolan.hyperframes.autoground <comp> [--apply] [--no-llm] [--min-dur 5]
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

try:
    from nolan.hyperframes.sync import _LONG_HOLD_S
except Exception:                                            # keep the operator importable standalone
    _LONG_HOLD_S = 5.0

# The blocks that actually CONSUME `data.ground` — the ONE registry both this operator and the style
# linter read (`nolan/block_registry.py`). It used to be a private copy here AND a different private
# copy in style_contract/metrics.py; see that module's docstring for what the divergence cost.
from nolan.block_registry import GROUND_BLOCKS as _GROUND_BLOCKS

_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
_VID_EXT = (".mp4", ".mov", ".webm")
_KB = [1.0, 1.08]                                            # subtle Ken-Burns push so a still ground isn't dead
_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "is", "it", "that", "this", "for", "with",
         "vs", "on", "at", "by", "as", "all", "per", "its", "our", "your", "not", "no"}


def _comp_dir(comp) -> Path:
    p = Path(comp)
    if p.exists() and (p / "compositions").exists():
        return p
    from nolan.hyperframes.edit import _project_dir          # resolve a bare comp id → its dir
    return Path(_project_dir(comp))


def _pool_assets(comp_dir: Path) -> Dict[str, Dict]:
    """Usable pool assets (image + video) that physically resolve on disk → {file: {caption, media_type, src}}.
    Resolves under capture/assets{,/videos} (where the pool lives at finish time) OR assets/ (post-stage);
    `src` is the `assets/…` path we author into the ground — assemble-media stages it from capture."""
    pj = comp_dir / "pool.json"
    if not pj.exists():
        return {}
    try:
        pool = json.loads(pj.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    items = pool if isinstance(pool, list) else (pool.get("items") or pool.get("assets") or [])
    out: Dict[str, Dict] = {}
    for it in items:
        if not isinstance(it, dict) or it.get("usable") is False:
            continue
        f = str(it.get("file") or "")
        ext = Path(f).suffix.lower()
        mt = "image" if ext in _IMG_EXT else ("video" if ext in _VID_EXT else None)
        if not mt:
            continue
        # DERIVE `src` from where the file ACTUALLY resolves — never guess the subdir from media_type.
        # `file` is sometimes a bare basename and sometimes already carries its subdir ("videos/a21_03.mp4",
        # "generated/a3_gen.png"), and a manually-clipped video lands in assets/ rather than assets/videos/.
        # Guessing produced dead links both ways ("assets/videos/videos/…" for a pool clip, "assets/videos/x"
        # for a manual one) — and a dead ground is SILENT: freeze-heal skips it and the root mount finds
        # nothing. The authored path is the resolving root minus the `capture/` staging prefix.
        src = None
        for root in ("capture/assets", "capture/assets/videos", "assets", "assets/videos"):
            if (comp_dir / root / f).exists():
                src = f"{root[len('capture/'):] if root.startswith('capture/') else root}/{f}"
                break
        if not src:
            continue
        cap = (it.get("caption") or it.get("desc") or it.get("description") or it.get("query") or "").strip()
        out[f] = {"caption": cap, "media_type": mt, "src": src}
    return out


def _scene_text(sc: Dict) -> str:
    d = sc.get("data", {}) or {}
    parts = [str(d.get(k, "")) for k in ("kicker", "title", "titleHi", "center", "headline", "anchor")]
    if isinstance(d.get("lines"), list):
        parts += [x for x in d["lines"] if isinstance(x, str)]
    for it in (d.get("items") or []):
        if isinstance(it, dict):
            parts += [str(it.get("label") or ""), str(it.get("text") or "")]
    return " ".join(p for p in parts if p).strip()


def _toks(s: str) -> set:
    return {t for t in re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split() if len(t) >= 4 and t not in _STOP}


def _keyword_pick(sc: Dict, pool: List[Dict], taken: set) -> Optional[str]:
    """Offline fallback: the unused pool asset sharing the most distinctive content words with the scene text.
    Returns a file only on a real overlap (≥1 shared content token), else None (→ leave clean)."""
    q = _toks(_scene_text(sc))
    if not q:
        return None
    best, bf = 0, None
    for a in pool:
        if a["file"] in taken:
            continue
        shared = len(q & _toks(a["caption"]))
        if shared > best:
            best, bf = shared, a["file"]
    return bf if best >= 1 else None


def _needs_ground(sc: Dict, min_dur: float) -> bool:
    """A long ungrounded hold on a block that RENDERS a ground — the auto-ground candidate set."""
    if sc.get("type") not in _GROUND_BLOCKS:
        return False
    g = (sc.get("data", {}) or {}).get("ground")
    grounded = isinstance(g, dict) and g.get("kind") not in (None, "color", "flat")
    return (not grounded) and float(sc.get("dur", 0) or 0) >= min_dur


def _llm_pick(needing: List, pool: List[Dict]) -> Dict[str, str]:
    """One batched LLM call → {uid: pool_file} for the scenes it can place. `needing` is a list of
    (uid, scene) — uid is frame-qualified ('01-hook/s2') because scene ids REPEAT across frames. Picks the
    asset whose SUBJECT evokes the scene's topic (thematic, not literal); omits / 'none' when nothing fits.
    {} on any failure (→ keyword fallback)."""
    try:
        import asyncio
        from nolan.config import load_config
        from nolan.llm import create_text_llm
        llm = create_text_llm(load_config())
    except Exception:
        return {}
    catalog = "\n".join(f"- {a['file']} [{a['media_type']}]: {a['caption']}" for a in pool)
    scenes = "\n".join(f'- {uid}: "{_scene_text(sc)}" (a {sc.get("type")} block)' for uid, sc in needing)
    prompt = (
        "You are art-directing a video essay. Each SCENE below holds on screen for several seconds; pick a "
        "background IMAGE or VIDEO from the POOL to sit behind it (dimmed, slow push), so the hold isn't a "
        "dead flat field.\n"
        "Choose the asset whose SUBJECT evokes the scene's topic — thematic, not literal (a spending chart "
        "wants a data-centre / money image; 'under antitrust law' wants a lock/court; 'the ground kept giving' "
        "wants a mine). Only pick an asset that GENUINELY fits — if nothing in the pool suits a scene, return "
        "\"none\" for it (a bare field beats a mismatched photo). Do NOT reuse one asset for many scenes.\n\n"
        f"POOL:\n{catalog}\n\nSCENES (the key before the colon is the exact id to return):\n{scenes}\n\n"
        'Return ONLY JSON mapping each scene key to a file or "none": {"01-hook/s2": "a2_00.jpg", ...}')
    try:
        raw = asyncio.run(llm.generate(prompt, "You return only strict JSON. No prose."))
        m = re.search(r"\{.*\}", raw, re.S)
        obj = json.loads(m.group(0)) if m else {}
        valid = {a["file"] for a in pool}
        return {k: v for k, v in obj.items() if isinstance(v, str) and v in valid}
    except Exception:
        return {}


def ground_data_scenes(comp, apply: bool = False, min_dur: float = None, use_llm: bool = True,
                       recompose: bool = True) -> Dict:
    """Assign ambient grounds to long ungrounded holds (text AND data) from the pool; leave the rest clean.
    `apply` writes the specs; `recompose` (when applying) rebuilds their HTML — the finish DAG passes
    recompose=False because its own recompose step runs next. Returns {grounded, left_clean, scanned, …}."""
    comp_dir = _comp_dir(comp)
    min_dur = _LONG_HOLD_S if min_dur is None else min_dur
    assets = _pool_assets(comp_dir)                          # {file: {caption, media_type, src}}
    pool_list = [{"file": f, **v} for f, v in assets.items()]
    spec_files = sorted((comp_dir / "compositions" / "frames").glob("*.spec.json"))

    specs, needing_all = [], []                              # (uid, scene); uid frame-qualified
    for sf in spec_files:
        try:
            spec = json.loads(sf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        specs.append((sf, spec))
        for fr in spec.get("frames", []):
            for sc in fr.get("scenes", []):
                if _needs_ground(sc, min_dur):
                    needing_all.append((f"{fr.get('id')}/{sc.get('id')}", sc))

    picks_by_uid = _llm_pick(needing_all, pool_list) if (use_llm and pool_list and needing_all) else {}

    grounded, clean, taken = [], [], set()
    for sf, spec in specs:
        changed = False
        for fr in spec.get("frames", []):
            for sc in fr.get("scenes", []):
                if not _needs_ground(sc, min_dur):
                    continue
                sid, uid = sc.get("id"), f"{fr.get('id')}/{sc.get('id')}"
                dur = round(float(sc.get("dur", 0) or 0), 1)
                f = picks_by_uid.get(uid)
                if f in taken:                              # never reuse an asset (LLM asked not to; enforce it)
                    f = None
                if not f and pool_list:
                    f = _keyword_pick(sc, pool_list, taken)
                if f and f in assets:
                    a = assets[f]
                    sc.setdefault("data", {})["ground"] = (
                        {"kind": "video", "src": a["src"]} if a["media_type"] == "video"
                        else {"kind": "image", "src": a["src"], "kb": list(_KB)})   # 'kb' — the key compose reads
                    taken.add(f)
                    grounded.append({"frame": fr.get("id"), "scene": sid, "block": sc.get("type"),
                                     "dur": dur, "src": a["src"], "kind": a["media_type"]})
                    changed = True
                else:
                    clean.append({"frame": fr.get("id"), "scene": sid, "block": sc.get("type"), "dur": dur})
        if apply and changed:
            raw = sf.read_bytes()
            out = (json.dumps(spec, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            if b"\r\n" in raw:                              # preserve CRLF if the spec had it
                out = out.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            sf.write_bytes(out)

    if apply and recompose and grounded:
        try:
            from nolan.hyperframes.edit import recompose_frame
            for fid in {g["frame"] for g in grounded}:
                recompose_frame(str(comp_dir), fid)
        except Exception:
            pass
    return {"scanned": len(needing_all), "grounded": grounded, "left_clean": clean,
            "pool": len(assets), "llm_picks": len(picks_by_uid), "applied": bool(apply)}


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.autoground")
    ap.add_argument("comp")
    ap.add_argument("--apply", action="store_true", help="write specs + recompose (else dry-run)")
    ap.add_argument("--no-llm", action="store_true", help="deterministic keyword pick only (no LLM call)")
    ap.add_argument("--min-dur", type=float, default=_LONG_HOLD_S, help="only ground holds at least this long")
    a = ap.parse_args()
    rep = ground_data_scenes(a.comp, apply=a.apply, min_dur=a.min_dur, use_llm=not a.no_llm)
    print(f"auto-ground: {rep['scanned']} long ungrounded hold(s); pool {rep['pool']} asset(s); "
          f"LLM matched {rep['llm_picks']}. {'APPLIED' if rep['applied'] else 'DRY-RUN'}")
    for g in rep["grounded"]:
        print(f"  ✓ {g['frame']}/{g['scene']} ({g['block']}, {g['dur']}s) → {g['src']} [{g['kind']}]")
    for c in rep["left_clean"]:
        print(f"  · {c['frame']}/{c['scene']} ({c['block']}, {c['dur']}s) → left CLEAN (nothing fit — bare beats forced)")


if __name__ == "__main__":
    main()
