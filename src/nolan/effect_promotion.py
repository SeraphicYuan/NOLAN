"""Effect promotion — agent-proposed motion effects through a deterministic gate.

The flagship application of the hybrid agent contract (CLAUDE.md): an agent's
output is a PROPOSAL artifact that passes a deterministic gate before becoming
canonical. The Clips lab's "Analyze effect" agent no longer edits registry.py
or Root.tsx directly; it writes a proposal, and this module gates + installs:

  proposal  projects/_clips/<clip_id>/proposal/
              effect.tsx   the Remotion composition (default export)
              entry.json   the registry entry AS DATA (+ sample_props,
                           provenance {clip_id, agent, date})
  gate      stage effect.tsx into the fixed Proposal harness slot, render
            against sample_props, check: renders cleanly, frames not blank,
            text not escaping the frame -> proposal/gate_report.json
  accept    install to src/promoted/<Comp>.tsx, register in Root.tsx at the
            managed markers, append the entry to motion/registry_custom.json
            (loaded by the registry at import — promoted effects are DATA,
            not code edits)

Python-backend proposals are analysis-only for now (renderer classes remain
hand-reviewed code); the gate rejects them with a clear message.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "render-service" / "remotion-lib"
HARNESS = LIB / "src" / "proposals" / "Current.tsx"
PROMOTED_DIR = LIB / "src" / "promoted"
ROOT_TSX = LIB / "src" / "Root.tsx"
CUSTOM_REGISTRY = Path(__file__).parent / "motion" / "registry_custom.json"

IMPORT_MARK = "/* PROMOTED-IMPORTS (managed by nolan.effect_promotion — do not edit by hand) */"
COMP_MARK = "{/* PROMOTED-COMPS (managed by nolan.effect_promotion — do not edit by hand) */}"

_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,40}$")
_COMP_RE = re.compile(r"^[A-Z][A-Za-z0-9]{2,40}$")


def proposal_dir(clip_id: str) -> Path:
    return REPO / "projects" / "_clips" / clip_id / "proposal"


# --- status --------------------------------------------------------------------

def promotion_status(clip_id: str) -> Dict[str, Any]:
    """Where this clip's effect sits on the analyzed→proposed→gated→registered arc."""
    base = REPO / "projects" / "_clips" / clip_id
    pdir = proposal_dir(clip_id)
    entry = _read_entry(pdir) if pdir.exists() else None
    gate_report = None
    gr = pdir / "gate_report.json"
    if gr.exists():
        try:
            gate_report = json.loads(gr.read_text(encoding="utf-8"))
        except Exception:
            gate_report = {"ok": False, "problems": ["gate_report.json unreadable"]}
    registered = False
    if entry:
        registered = any(e.get("id") == entry.get("id")
                         for e in _load_custom_entries())
    stage = ("registered" if registered
             else "gated" if gate_report and gate_report.get("ok")
             else "gate-failed" if gate_report
             else "proposed" if entry
             else "analyzed" if (base / "effect_analysis.md").exists()
             else "none")
    return {"clip_id": clip_id, "stage": stage,
            "entry": entry, "gate_report": gate_report,
            "has_analysis": (base / "effect_analysis.md").exists()}


def _read_entry(pdir: Path) -> Optional[Dict[str, Any]]:
    p = pdir / "entry.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"id": None, "_error": "entry.json unreadable"}


def _load_custom_entries() -> List[Dict[str, Any]]:
    if not CUSTOM_REGISTRY.exists():
        return []
    try:
        return json.loads(CUSTOM_REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return []


# --- validate ------------------------------------------------------------------

def validate_proposal(clip_id: str) -> List[str]:
    """Structural problems with the proposal (empty list = valid)."""
    from nolan.motion.registry import REGISTRY

    pdir = proposal_dir(clip_id)
    problems: List[str] = []
    entry = _read_entry(pdir)
    if entry is None:
        return [f"no proposal at {pdir} (entry.json missing)"]
    if entry.get("_error"):
        return [entry["_error"]]

    eid = entry.get("id", "")
    if not _ID_RE.match(str(eid)):
        problems.append(f"id {eid!r} must be kebab-case (3-40 chars)")
    taken = {e.id for e in REGISTRY} | {e.get("id") for e in _load_custom_entries()}
    if eid in taken:
        problems.append(f"id {eid!r} already exists in the motion registry")

    backend = entry.get("backend")
    if backend != "remotion":
        problems.append(f"backend {backend!r}: only 'remotion' proposals are "
                        "gateable (python renderers stay hand-reviewed code)")
    target = entry.get("target", "")
    if not _COMP_RE.match(str(target)):
        problems.append(f"target {target!r} must be a PascalCase composition id")
    if (PROMOTED_DIR / f"{target}.tsx").exists():
        problems.append(f"a promoted composition named {target} already exists")

    if not entry.get("purpose"):
        problems.append("entry needs a one-line 'purpose'")
    if not isinstance(entry.get("sample_props"), dict):
        problems.append("entry needs 'sample_props' (the gate renders with them)")
    prov = entry.get("provenance") or {}
    if not prov.get("clip_id"):
        problems.append("entry.provenance.clip_id missing (agent must stamp origin)")

    tsx = pdir / "effect.tsx"
    if not tsx.exists():
        problems.append("effect.tsx missing")
    else:
        src = tsx.read_text(encoding="utf-8")
        if "export default" not in src:
            problems.append("effect.tsx must `export default` its component")
        for banned in ("Math.random", "Date.now", "new Date("):
            if banned in src:
                problems.append(f"effect.tsx uses {banned} — compositions must be "
                                "pure functions of useCurrentFrame()")
    return problems


# --- gate ----------------------------------------------------------------------

def gate_proposal(clip_id: str, *, keep_stills: bool = True) -> Dict[str, Any]:
    """Render the candidate through the Proposal harness + run the checks.

    Deterministic and side-effect-free on the real registrations: the
    candidate is staged into the harness slot and the slot is ALWAYS
    restored. Report saved to proposal/gate_report.json.
    """
    pdir = proposal_dir(clip_id)
    problems = validate_proposal(clip_id)
    report: Dict[str, Any] = {"ok": False, "problems": problems, "stills": []}
    if problems:
        _save_report(pdir, report)
        return report

    entry = _read_entry(pdir)
    placeholder = HARNESS.read_text(encoding="utf-8")
    out_name = f"gate_{clip_id}.mp4"
    try:
        HARNESS.write_text((pdir / "effect.tsx").read_text(encoding="utf-8"),
                           encoding="utf-8")
        from nolan import remotion_source
        frames = int(float(entry.get("duration_default", 4.0)) * 30)
        props = dict(entry.get("sample_props") or {})
        props["durationInFrames"] = frames
        try:
            rendered = remotion_source.render("Proposal", props, out_name,
                                              duration_frames=frames)
        except Exception as exc:
            report["problems"].append(f"harness render failed: {exc}")
            _save_report(pdir, report)
            return report

        # frame checks: not blank, text not escaping the frame
        from nolan.flows.gate.contact import _edge_overflow
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        for frac in (0.5, 0.9):
            still = pdir / f"gate_{int(frac * 100)}.png"
            t = max(0.0, frames / 30 * frac - 0.05)
            r = subprocess.run([ff, "-y", "-v", "quiet", "-ss", f"{t:.2f}",
                                "-i", str(rendered), "-frames:v", "1", str(still)],
                               capture_output=True, text=True)
            if r.returncode != 0 or not still.exists():
                report["problems"].append(f"could not extract still at {frac}")
                continue
            report["stills"].append(still.name)
            bf = subprocess.run([ff, "-i", str(still),
                                 "-vf", "blackframe=amount=0:threshold=32",
                                 "-f", "null", "-"], capture_output=True, text=True)
            m = re.search(r"pblack:(\d+)", bf.stderr)
            if m and int(m.group(1)) >= 98:
                report["problems"].append(f"frame at {frac} is blank")
            over = _edge_overflow(still)
            if over:
                report["problems"].append(f"content escapes the frame ({over}) at {frac}")
    finally:
        HARNESS.write_text(placeholder, encoding="utf-8")

    report["ok"] = not report["problems"]
    _save_report(pdir, report)
    return report


def _save_report(pdir: Path, report: Dict[str, Any]) -> None:
    try:
        (pdir / "gate_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# --- accept --------------------------------------------------------------------

def accept_proposal(clip_id: str) -> Dict[str, Any]:
    """Install a GATED proposal: promoted/<Comp>.tsx + Root markers + custom registry."""
    pdir = proposal_dir(clip_id)
    status = promotion_status(clip_id)
    if status["stage"] != "gated":
        raise RuntimeError(f"proposal is '{status['stage']}' — only gated "
                           "proposals can be accepted (run the gate first)")
    entry = _read_entry(pdir)
    target = entry["target"]

    PROMOTED_DIR.mkdir(parents=True, exist_ok=True)
    dest = PROMOTED_DIR / f"{target}.tsx"
    shutil.copy(str(pdir / "effect.tsx"), str(dest))

    root = ROOT_TSX.read_text(encoding="utf-8")
    if IMPORT_MARK not in root or COMP_MARK not in root:
        raise RuntimeError("Root.tsx promotion markers missing — repo drift")
    imp = f"import {target} from './promoted/{target}';"
    # ONE line per promoted comp — uninstalls/audits are line-exact.
    comp = (f"      <Composition id=\"{target}\" "
            f"component={{{target} as React.FC<Record<string, unknown>>}} "
            f"durationInFrames={{120}} {{...common}} "
            f"defaultProps={{{{durationInFrames: 120}}}} calculateMetadata={{dur}} />")
    if imp not in root:
        root = root.replace(IMPORT_MARK, IMPORT_MARK + "\n" + imp, 1)
        root = root.replace(COMP_MARK, comp + "\n      " + COMP_MARK, 1)
        ROOT_TSX.write_text(root, encoding="utf-8")

    entries = _load_custom_entries()
    entries = [e for e in entries if e.get("id") != entry["id"]]
    entries.append({k: v for k, v in entry.items() if k != "sample_props"})
    CUSTOM_REGISTRY.write_text(json.dumps(entries, indent=2, ensure_ascii=False),
                               encoding="utf-8")

    # the effect must now load through the real registry
    import importlib
    import nolan.motion.registry as reg
    importlib.reload(reg)
    assert any(e.id == entry["id"] for e in reg.REGISTRY), "registry reload lost the entry"

    logger.info("promoted effect %s (comp %s) from clip %s",
                entry["id"], target, clip_id)
    return {"registered": True, "id": entry["id"], "target": target,
            "composition": str(dest.relative_to(REPO))}
