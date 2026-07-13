"""Long-hold reliever — turn the advisory LONG-HOLD flag into an actionable PROPOSAL.

An ungrounded statement held 9-12s 'reads like a slide' (holbein POST_MORTEM #9). `short_holds` is the
only hard hold gate, so nothing carries taste to these beats: the gate rewards the hold being ALLOWED;
taste says ground or trim it. Per NOLAN's agent contract (draft -> validate -> accept) this proposes
concrete remedies rather than silently allowing the slide — the POST_MORTEM's own fix (a slow ground
push under the rhetoric), a split into denser beats, or a reveal cadence — and `--apply-ground`
commits the top ground remedy through the edit GATE.

  python -X utf8 -m nolan.hyperframes.relieve <comp> [--apply-ground]
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from nolan.imagelib.store import _distinctive_tokens

_KB_PUSH = [1.0, 1.12]                                   # a slow Ken-Burns push (matches the freeze-heal ratio)


def long_holds(comp) -> List[Dict]:
    """The LONG-HOLD ungrounded scenes, via the sync dry-run (no recompose / render / spec write)."""
    from nolan.hyperframes.sync import report_windows
    rep = report_windows(comp)
    return [w for w in rep.get("windows", []) if str(w.get("verdict", "")).startswith("LONG-HOLD")]


def _scene_text(sc: Dict) -> str:
    d = sc.get("data", {}) or {}
    parts: List[str] = []
    for k in ("anchor", "operative", "kicker", "title"):
        v = d.get(k) or sc.get(k)
        if isinstance(v, str):
            parts.append(v)
    lines = d.get("lines")
    if isinstance(lines, list):
        parts.extend(str(x) for x in lines)
    elif isinstance(lines, str):
        parts.append(lines)
    return " ".join(parts).strip()


def _load_pool(comp_dir: Path) -> List[Dict]:
    for p in (comp_dir / "pool.json", comp_dir / "capture" / "pool.json"):
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else (data.get("assets") or [])
            except (json.JSONDecodeError, OSError):
                return []
    return []


def best_ground(text: str, pool: List[Dict], floor: float = 0.15) -> Optional[Dict]:
    """The pool IMAGE asset whose caption/query best relates to the beat (for a slow push under the
    text). Score = fraction of the beat's distinctive tokens present in the asset caption+query;
    returns None below `floor` (author picks / generate instead of a bad literal match)."""
    btok = set(_distinctive_tokens(text))
    if not btok:
        return None
    best, best_score = None, 0.0
    for a in pool:
        if not isinstance(a, dict) or a.get("media_type", "image") != "image":
            continue
        hay = set(_distinctive_tokens(" ".join(str(a.get(k, "")) for k in ("caption", "query"))))
        if not hay:
            continue
        score = sum(1 for t in btok if t in hay) / len(btok)
        if score > best_score:
            best, best_score = a, score
    if best is None or best_score < floor:
        return None
    return {"file": best.get("file"), "caption": best.get("caption"), "score": round(best_score, 3)}


def propose(comp) -> List[Dict]:
    """For each LONG-HOLD scene, a ranked list of concrete remedies (ground / split / cadence)."""
    from nolan.hyperframes.edit import _comp_dir, load_frame_spec
    comp_dir = _comp_dir(comp)
    pool = _load_pool(comp_dir)
    out: List[Dict] = []
    for w in long_holds(comp):
        spec, info = load_frame_spec(comp, w["frame"])
        fr = spec["frames"][info["i"]]
        sc = next((s for s in fr.get("scenes", []) if s.get("id") == w["scene"]), None)
        if sc is None:
            continue
        text = _scene_text(sc)
        lines = (sc.get("data", {}) or {}).get("lines")
        n_lines = len(lines) if isinstance(lines, list) else 1
        remedies: List[Dict] = []

        g = best_ground(text, pool)
        if g and g.get("file"):
            remedies.append({
                "kind": "ground",
                "why": f"slow push on a related pool image ({g['file']}, cover {g['score']}) — grounds the "
                       "rhetoric so the theme dims it and the text reads over footage (POST_MORTEM's fix)",
                "asset": g["file"], "caption": g.get("caption"),
                "patch": {"data.ground": {"kind": "image", "src": f"assets/{g['file']}", "kb": _KB_PUSH}}})
        if n_lines >= 2:
            remedies.append({
                "kind": "split", "at": n_lines // 2,
                "why": f"split the {n_lines}-line statement into 2 denser beats (~{w['dur']/2:.1f}s each) so "
                       "the text lands progressively instead of holding as one static slide"})
        remedies.append({
            "kind": "cadence",
            "why": "if it must hold, spread the reveal — a per-line cadence / a mid-beat operative sweep — "
                   "so motion continues across the window instead of settling in the first ~2s"})
        out.append({"frame": w["frame"], "scene": w["scene"], "block": w["block"],
                    "dur": w["dur"], "anchor": w.get("anchor", ""), "remedies": remedies})
    return out


def apply_ground(comp, frame_id: str, scene_id: str, pool_file: str, kb=None) -> Dict:
    """Commit the ground remedy: copy the pool image into <comp>/assets/ and patch the scene's
    data.ground through the edit GATE (validate -> recompose). Returns the gate result."""
    from nolan.hyperframes.edit import _comp_dir, apply_scene_edit
    comp_dir = _comp_dir(comp)
    src = comp_dir / "capture" / "assets" / pool_file
    if not src.exists():
        src = comp_dir / "capture" / pool_file
    if not src.exists():
        raise FileNotFoundError(f"pool asset not found: {pool_file} (looked under capture/assets/)")
    dest_dir = comp_dir / "assets"
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest_dir / Path(pool_file).name)
    ground = {"kind": "image", "src": f"assets/{Path(pool_file).name}", "kb": kb or _KB_PUSH}
    return apply_scene_edit(comp, frame_id, scene_id, patch={"data.ground": ground})


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.relieve",
                                 description="Propose (and optionally apply) relief for LONG-HOLD scenes.")
    ap.add_argument("comp", help="composition dir / slug")
    ap.add_argument("--apply-ground", action="store_true",
                    help="commit the top ground remedy for each long-hold through the edit gate")
    a = ap.parse_args()

    proposals = propose(a.comp)
    if not proposals:
        print("long-hold reliever: no LONG-HOLD ungrounded scenes ✓")
        return
    print(f"long-hold reliever: {len(proposals)} scene(s) reading as a slide — proposals:")
    for p in proposals:
        print(f"\n  {p['frame']}/{p['scene']} [{p['block']}] {p['dur']:.1f}s  “{p['anchor']}”")
        for r in p["remedies"]:
            print(f"    · {r['kind']}: {r['why']}")

    if a.apply_ground:
        print("\napplying top ground remedy per scene (gate-validated)…")
        for p in proposals:
            g = next((r for r in p["remedies"] if r["kind"] == "ground"), None)
            if not g:
                print(f"  – {p['frame']}/{p['scene']}: no pool image matched — skip (split or generate)")
                continue
            res = apply_ground(a.comp, p["frame"], p["scene"], g["asset"])
            ok = res.get("ok")
            print(f"  {'✓' if ok else '✗'} {p['frame']}/{p['scene']}: grounded with {g['asset']}"
                  + ("" if ok else f" — gate rejected:\n{res.get('output','')[-400:]}"))


if __name__ == "__main__":
    main()
