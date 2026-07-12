"""nolan hf-finish — ONE idempotent driver for the compose-first FINISH DAG.

The finish sequence used to be tribal knowledge (prose in the kickoff brief): get one step out of
order — captions after assemble-index, or assemble_media before it — and it silently ships a worse
video or errors. This encodes the DAG as code: run it, fail LOUD, re-run safely.

  sync-durations → hyperframes.sync (align+place) → recompose (rebuild HTML in the theme) →
  sound (bgm + sfx, soft) → captions → assemble-index → assemble_media (+ pre-render freeze-heal) →
  render → hf_qa + style-contract lint (report)

Node steps run cwd=<comp> (they use ./STORYBOARD.md, ./audio_meta.json …); python steps run as
subprocesses. `--dry-run` prints the plan without executing; `--no-render` stops before the render;
`--no-sound` skips the bgm/sfx bed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List

from .edit import BRIDGE, REPO, _project_dir, list_frames, recompose_frame

SKILL_SCRIPTS = REPO / ".agents" / "skills" / "faceless-explainer" / "scripts"


def _run(label: str, cmd: List[str], cwd: Path = None, *, dry: bool = False, soft: bool = False, env=None) -> bool:
    """Run one DAG step. Fail LOUD (raise) on non-zero unless `soft` (then warn + continue)."""
    shown = " ".join(str(c) for c in cmd)
    if dry:
        print(f"  [{label}] {shown}" + (f"   (cwd={cwd})" if cwd else ""))
        return True
    print(f"▶ {label}")
    # `npx`/`node` are .cmd shims on Windows — a WSL-launched Windows python can't spawn them without a
    # shell (node resolves, npx does NOT), so the render step died every run. Mirror render_frame's fix.
    shell = os.name == "nt" and bool(cmd) and cmd[0] in ("npx", "node")
    try:
        r = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", shell=shell, env=env)
    except FileNotFoundError as e:
        if soft:
            print(f"  ⚠ {label} skipped ({e})")
            return False
        raise RuntimeError(f"hf-finish: '{label}' — command not found ({cmd[0]})") from e
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0:
        print(out[-2000:])
        if soft:
            print(f"  ⚠ {label} failed (rc={r.returncode}) — continuing (soft step)")
            return False
        raise RuntimeError(f"hf-finish: step '{label}' failed (rc={r.returncode}) — see output above")
    if out:
        print("  " + out[-600:].replace("\n", "\n  "))
    return True


def finish(comp: str, *, render: bool = True, sound: bool = True, dry_run: bool = False) -> dict:
    """Run the compose-first finish DAG for a comp. Returns a summary dict."""
    pdir = _project_dir(comp)
    py = [sys.executable, "-X", "utf8"]
    audio = str(SKILL_SCRIPTS / "audio.mjs")
    # fail LOUD up front if a skill script path is wrong (a silent bad node path left a stale index + cost a render)
    for _s in ("audio.mjs", "captions.mjs", "assemble-index.mjs"):
        if not (SKILL_SCRIPTS / _s).exists():
            raise RuntimeError(f"hf-finish: skill script missing — {SKILL_SCRIPTS / _s}. Is the faceless-explainer skill installed?")
    print(f"hf-finish: {comp}  (render={render}, sound={sound}{', DRY-RUN' if dry_run else ''})")

    # 1 · frame durations FROM the VO (narration owns duration)
    _run("sync-durations", ["node", audio, "sync-durations", "--audio-meta", "./audio_meta.json",
                            "--storyboard", "./STORYBOARD.md"], cwd=pdir, dry=dry_run, soft=True)
    # 2 · word-sync: force-align the VO, place each scene + fire its highlight on the spoken word
    _run("word-sync", py + ["-m", "nolan.hyperframes.sync", str(pdir)], dry=dry_run)
    # 3 · recompose every frame's HTML from its (now retimed) spec, in the comp's theme
    if dry_run:
        print("  [recompose] hfedit.recompose_frame() for each frame (rebuild HTML in-theme)")
    else:
        print("▶ recompose")
        for fr in list_frames(comp):
            fid = fr.get("id") if isinstance(fr, dict) else fr
            res = recompose_frame(comp, fid)
            if not res.get("ok"):
                raise RuntimeError(f"hf-finish: recompose of frame {fid} failed:\n{res.get('output', '')[-1200:]}")
        print(f"  recomposed {len(list_frames(comp))} frame(s)")
    # 4 · SOUND (soft): a music bed + SFX cues, merged into audio_meta BEFORE assemble-index mounts them.
    # GUARD: the sound step must never wipe the bridged narration (a silent render is a loud failure).
    if sound:
        import json as _json
        am = pdir / "audio_meta.json"
        before = len(_json.loads(am.read_text(encoding="utf-8")).get("voices", [])) if (am.exists() and not dry_run) else 0
        _run("bgm", ["node", audio, "fetch-bgm", "--storyboard", "./STORYBOARD.md", "--hyperframes", "."],
             cwd=pdir, dry=dry_run, soft=True)
        _run("sfx", ["node", audio, "fetch-sfx", "--storyboard", "./STORYBOARD.md", "--hyperframes", "."],
             cwd=pdir, dry=dry_run, soft=True)
        if before and not dry_run:
            after = len(_json.loads(am.read_text(encoding="utf-8")).get("voices", [])) if am.exists() else 0
            if after < before:
                raise RuntimeError(f"hf-finish: the sound step wiped narration ({before}→{after} voices) — "
                                   "aborting before a silent render")
    # 5 · captions sub-comp from the word timings
    _run("captions", ["node", str(SKILL_SCRIPTS / "captions.mjs"), "build", "--storyboard", "./STORYBOARD.md",
                      "--audio-meta", "./audio_meta.json", "--hyperframes", ".", "--out", "./caption_groups.json"],
         cwd=pdir, dry=dry_run, soft=True)
    # 6 · mount all frames (+ bgm/sfx/voice tracks) into index.html
    _run("assemble-index", ["node", str(SKILL_SCRIPTS / "assemble-index.mjs"), "--storyboard", "./STORYBOARD.md",
                            "--hyperframes", "."], cwd=pdir, dry=dry_run)
    # 7 · inject video grounds + PRE-RENDER freeze-heal (AFTER assemble-index, BEFORE render)
    _run("assemble-media", py + [str(BRIDGE / "assemble_media.py"), str(pdir)], dry=dry_run)
    if not render:
        print("hf-finish: stopped before render (--no-render). Preview then re-run to render.")
        return {"comp": comp, "rendered": False}
    # 8 · render the whole composition → renders/video.mp4. For the target 7-8 min format the single
    # long ffmpeg encode times out; chunked encode is safer (nolan4 hit the timeout on the 468s render).
    total = 0.0
    _am = pdir / "audio_meta.json"
    if _am.exists():
        try:
            total = sum(float(v.get("duration_s", 0) or 0) for v in json.loads(_am.read_text(encoding="utf-8")).get("voices", []))
        except Exception:
            total = 0.0
    render_env = None
    if total > 300:                                   # 5+ min → chunk it
        render_env = {**os.environ, "PRODUCER_ENABLE_CHUNKED_ENCODE": "1"}
        print(f"  (chunked encode — {total:.0f}s render)")
    _run("render", ["npx", "hyperframes", "render", "--skill=faceless-explainer", "--quality", "high",
                    "--output", "renders/video.mp4"], cwd=pdir, dry=dry_run, env=render_env)
    # 9 · QA (soft: report — don't crash the driver on a gate fail)
    _run("hf-qa", py + ["-m", "nolan.hf_qa", str(pdir)], dry=dry_run, soft=True)          # freeze + audio (ffmpeg)
    _run("style-lint", py + ["-m", "nolan.style_contract", str(pdir)], dry=dry_run, soft=True)  # spec dimensions
    _run("perceptual", py + ["-m", "nolan.hyperframes.render_gate", str(pdir)], dry=dry_run, soft=True)  # VLM: legibility + relevance
    print("hf-finish: done → renders/video.mp4")
    return {"comp": comp, "rendered": True}


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan hf-finish", description="Run the compose-first finish DAG.")
    ap.add_argument("comp", help="composition id / dir")
    ap.add_argument("--no-render", action="store_true", help="stop before the render (assemble + preview)")
    ap.add_argument("--no-sound", action="store_true", help="skip the bgm/sfx bed")
    ap.add_argument("--dry-run", action="store_true", help="print the DAG without running it")
    a = ap.parse_args()
    try:
        finish(a.comp, render=not a.no_render, sound=not a.no_sound, dry_run=a.dry_run)
    except RuntimeError as e:
        print(f"\n✗ {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
