"""Shared flow engine — ingest → gate → render → deliver, flow-agnostic.

Everything downstream of the job JSON is identical across flows; only the ingest adapter
and the profile/palette (carried by the Flow) differ. Matches the lab orchestration
precedent: runs under WSL python3, subprocess-out to Windows node for the Remotion render.
The `nolan render-flow` CLI bridge (Windows-python invocation) is a separate follow-up.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WVL = ROOT / "web-video-lab"
RS = ROOT / "render-service"
NODE = "/mnt/c/Program Files/nodejs/node.exe"
FFMPEG = RS / "node_modules" / "@remotion" / "compositor-win32-x64-msvc" / "ffmpeg.exe"


def _win(p) -> str:
    """/mnt/d/foo -> D:/foo so Windows node/ffmpeg resolve it."""
    p = str(Path(p).resolve())
    m = re.match(r"^/mnt/([a-z])/(.*)$", p)
    return f"{m.group(1).upper()}:/" + m.group(2) if m else p


def run_gate(job_path: Path, flow_id: str) -> None:
    """Pre-render gate (Tier 0 validate+palette+pacing, Tier 1 contact). Raises if blocked."""
    rc = subprocess.run([sys.executable, str(WVL / "art_check.py"), str(job_path),
                         "--profile", flow_id]).returncode
    if rc != 0:
        raise RuntimeError(f"GATE BLOCKED job {job_path.name} (flow={flow_id}) — fix before render")


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


def run_flow(flow, spec_path, *, gate: bool = True, deliver_to=None) -> Path:
    """Run one flow end to end. Returns the delivered mp4 path.

    flow      — a Flow (see __init__.get_flow)
    spec_path — the authored flow spec (e.g. art/dance.spec.json)
    """
    spec_path = Path(spec_path)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    job_path = spec_path.with_name(spec_path.stem.replace(".spec", "") + ".job.json")

    print(f"[flow:{flow.id}] ingest {spec_path.name} -> {job_path.name}")
    flow.ingest(spec_path, job_path)                       # CODE fork: assemble | generate
    if gate:
        print(f"[flow:{flow.id}] gate")
        run_gate(job_path, flow.id)
    print(f"[flow:{flow.id}] render")
    mp4 = render_chapter(job_path)
    out_name = json.loads(job_path.read_text(encoding="utf-8")).get("out", "chapter.mp4")
    dest = Path(deliver_to) if deliver_to else (Path(spec["project"]) / "video" / out_name)
    dest = deliver(mp4, dest)
    print(f"[flow:{flow.id}] delivered -> {dest}")
    return dest
