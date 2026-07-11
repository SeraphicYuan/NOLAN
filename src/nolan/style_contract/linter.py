"""The style linter — the deterministic verifier half of the contract.

lint(scenes, contract) scores an authored essay against every dimension in the registry: GATES get
a pass/fail, ADVISORY dimensions are reported only. Returns a report the author revises against
(draft → lint → revise the failing gates → accept). Generic — driven entirely by `dimensions.py`.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from .contract import StyleContract, fmt_target
from .dimensions import DIMENSIONS, GATES
from .metrics import SceneView, measure, scene_media, scene_num_count, scene_words


def _check(value, lo, hi):
    if value is None:
        return False, "missing"
    if lo is not None and value < lo:
        return False, "below"
    if hi is not None and value > hi:
        return False, "above"
    return True, "ok"


def _frames_without_assets(scenes: List[SceneView]) -> List[str]:
    byf = defaultdict(list)
    for s in scenes:
        byf[s.frame_id].append(s)
    return [f for f, ss in byf.items() if all(x.media == "none" for x in ss)]


def _note(key, side, val, m, scenes) -> str:
    if key == "coverage":
        empt = _frames_without_assets(scenes)
        grounded = m["media_mix"].get("image", 0) + m["media_mix"].get("video", 0)
        return f"only {grounded}/{m['n_scenes']} scenes grounded" + (f"; frames with ZERO assets: {empt}" if empt else "")
    if key == "video_share":
        return f"{m['media_mix'].get('video',0)}/{m['n_scenes']} scenes on video — motion footage under target"
    if key == "pacing_cv":
        return f"scene lengths near-uniform (cv={val}) — rhythm reads flat" if side == "below" else f"pacing erratic (cv={val})"
    if key == "layout_max_share":
        top = next(iter(m["block_dist"].items()))
        return f"'{top[0]}' is {round(val*100)}% of scenes — one block dominates; dist={m['block_dist']}"
    if key == "layout_max_run":
        return f"{val}× the same block back-to-back — monotone stretch"
    return f"{side}: {val}"


def lint(scenes: List[SceneView], contract: StyleContract) -> Dict:
    m = measure(scenes)
    dims = []
    for d in DIMENSIONS:
        val = m.get(d.metric)
        if d.mode == "gate":
            lo, hi = contract.targets.get(d.key, d.target)
            ok, side = _check(val, lo, hi)
            note = "ok" if ok else _note(d.key, side, val, m, scenes)
        else:                                          # advisory: reported only, never fails
            lo, hi = (None, None)
            ok, side, note = True, "advisory", ""
        dims.append({"key": d.key, "label": d.label, "mode": d.mode, "value": val,
                     "target": (lo, hi), "ok": ok, "side": side, "note": note})
    failures = [x for x in dims if x["mode"] == "gate" and not x["ok"]]
    return {"preset": contract.preset, "dials": contract.dials, "metrics": m,
            "overall_pass": not failures, "n_fail": len(failures),
            "dimensions": dims, "failures": failures}


# --- adapters -----------------------------------------------------------------
def scenes_from_hf(comp_dir) -> List[SceneView]:
    """Normalize a HyperFrames composition (compositions/frames/*.spec.json) into SceneViews."""
    fdir = Path(comp_dir) / "compositions" / "frames"
    out: List[SceneView] = []
    for sf in sorted(fdir.glob("*.spec.json")):
        try:
            spec = json.loads(sf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for fr in spec.get("frames", []):
            scenes = fr.get("scenes", []) or []
            for i, sc in enumerate(scenes):
                data = sc.get("data", {}) or {}
                block = sc.get("type", "raw")
                out.append(SceneView(
                    frame_id=fr.get("id", sf.stem), scene_id=sc.get("id", f"s{i}"),
                    block=block, dur=float(sc.get("dur", 0) or 0),
                    media=scene_media(data), register=str(data.get("register", "paper")),
                    num_count=scene_num_count(block, data), words=scene_words(data),
                    first_in_frame=(i == 0),
                ))
    return out


# --- reference-derive hook ----------------------------------------------------
def fingerprint(scenes: List[SceneView]) -> Dict:
    """A reference essay's measured fingerprint (all dimension values) — the seed for
    'author in the style of THIS video' contracts."""
    m = measure(scenes)
    return {d.key: m.get(d.metric) for d in DIMENSIONS}


def contract_from_fingerprint(scenes, name: str = "reference", tol: float = 0.2) -> StyleContract:
    """Turn a reference fingerprint into a contract: a tolerance band around each GATE's measured value."""
    m = measure(scenes)
    targets = {}
    for d in GATES:
        v = m.get(d.metric) or 0
        pad = tol if d.pct else max(tol * v, 1)
        targets[d.key] = (round(max(0.0, v - pad), 3), round(v + pad, 3))
    return StyleContract(preset=f"reference:{name}", targets=targets, dials={})


# --- pretty printer -----------------------------------------------------------
def format_report(report: Dict) -> str:
    m = report["metrics"]
    head = (f"STYLE LINT — '{report['preset']}'" + (f" ({report['dials']})" if report['dials'] else "")
            + f" — {'PASS' if report['overall_pass'] else str(report['n_fail']) + ' GATE FAIL'}"
            + f"  [{m.get('n_scenes',0)} scenes / {m.get('n_frames',0)} frames / {m.get('total_dur',0)}s]")
    lines = [head]
    for d in report["dimensions"]:
        lo, hi = d["target"]
        if d["mode"] == "gate":
            mark = "✓" if d["ok"] else "✗"
            tgt = f"  target [{'' if lo is None else lo}..{'' if hi is None else hi}]"
            note = "" if d["ok"] else f"   — {d['note']}"
        else:
            mark, tgt, note = "·", "  (advisory)", ""
        lines.append(f"  {mark} {d['label']:24} = {d['value']}{tgt}{note}")
    return "\n".join(lines)
