"""Shared flow engine — ingest -> gate -> render -> deliver, flow-agnostic.

Everything downstream of the job JSON is identical across flows; only the ingest adapter
and the profile/palette (carried by the Flow) differ. Runs IN-PROCESS under the nolan env
python (ingest + gate are imported, not subprocessed); only node (the Remotion render) and
ffmpeg are subprocessed. See src/nolan/flows/README.md for the full design.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RS = ROOT / "render-service"
# node is a Windows binary; reach it the way the running interpreter can (WSL vs nolan-win python)
NODE = "C:/Program Files/nodejs/node.exe" if os.name == "nt" else "/mnt/c/Program Files/nodejs/node.exe"
FFMPEG = RS / "node_modules" / "@remotion" / "compositor-win32-x64-msvc" / "ffmpeg.exe"


def _win(p) -> str:
    """/mnt/d/foo -> D:/foo so Windows node/ffmpeg resolve it."""
    p = str(Path(p).resolve())
    m = re.match(r"^/mnt/([a-z])/(.*)$", p)
    return f"{m.group(1).upper()}:/" + m.group(2) if m else p


def run_gate(job_path: Path, flow_id: str) -> None:
    """Pre-render gate (Tier 0 validate+palette+pacing, Tier 1 contact), in-process.
    Lazy import avoids a cycle (gate modules import this module's constants)."""
    from .gate import run_gate as _run_gate
    _run_gate(job_path, flow_id)


def render_chapter(job_path: Path) -> Path:
    """Render a Chapter job to mp4 via the _lab_chapter Remotion bundle (Windows node)."""
    cfg = json.loads(Path(job_path).read_text(encoding="utf-8"))
    r = subprocess.run([NODE, "_lab_chapter/render.mjs", _win(job_path)],
                       cwd=str(RS), capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise RuntimeError(f"render failed for {job_path.name}")
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "rendered")
    return RS / "_lab_chapter" / "output" / cfg.get("out", "chapter.mp4")


def deliver(mp4: Path, dest: Path) -> Path:
    """Faststart-remux the render into the delivery dir (web-ready moov-at-front)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(FFMPEG), "-y", "-i", _win(mp4), "-c", "copy",
                    "-movflags", "+faststart", _win(dest)],
                   cwd=str(RS), capture_output=True, text=True)
    return dest


def run_flow(flow, spec_path, *, gate: bool = True, render: bool = True, deliver_to=None) -> Path:
    """Run one flow. Returns the delivered mp4 (or the job path if render=False).

    flow      — a Flow (see __init__.get_flow)
    spec_path — the flow spec (project-owned flow.spec.json, or a lab spec)
    render    — False stops after the gate (validate the plan without a full render)
    """
    spec_path = Path(spec_path)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    job_path = spec_path.with_name(spec_path.stem.replace(".spec", "") + ".job.json")

    print(f"[flow:{flow.id}] ingest {spec_path.name} -> {job_path.name}")
    flow.ingest(spec_path, job_path)                       # CODE fork: assemble | generate
    if gate:
        print(f"[flow:{flow.id}] gate")
        run_gate(job_path, flow.id)
    if not render:
        print(f"[flow:{flow.id}] gate-only (render skipped) -> {job_path}")
        return job_path
    out_name = json.loads(job_path.read_text(encoding="utf-8")).get("out", "chapter.mp4")
    print(f"[flow:{flow.id}] render ({flow.render_mechanism})")
    if flow.render_mechanism == "chapter-block":
        from .render import render_flow                # per-beat clips -> concat
        work = job_path.parent / ".flow" / "clips"
        mp4 = render_flow(job_path, work, work.parent / out_name)
    else:
        mp4 = render_chapter(job_path)                 # whole-composition master
    dest = Path(deliver_to) if deliver_to else (Path(spec["project"]) / "video" / out_name)
    dest = deliver(mp4, dest)
    # refresh the Scene-page view (Gate B) so the flow project shows its beats as scenes
    proj = Path(spec.get("project", spec_path.parent))
    if (proj / "flow.spec.json").exists():
        from .scene_view import build_scene_plan
        build_scene_plan(proj)
        print(f"[flow:{flow.id}] scene view -> {proj/'scene_plan.json'}")
    print(f"[flow:{flow.id}] delivered -> {dest}")
    return dest


def run_flow_for_project(project, **kw) -> Path:
    """Project-centric entry: resolve the project's flow + project-owned spec, then run."""
    from .project import load_flow_spec
    flow, spec_path = load_flow_spec(project)
    return run_flow(flow, spec_path, **kw)
