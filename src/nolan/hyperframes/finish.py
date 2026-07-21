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

from .edit import BRIDGE, REPO, _project_dir, ensure_storyboard, list_frames, recompose_frame

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


def finish(comp: str, *, render: bool = True, sound: bool = True, dry_run: bool = False,
           render_mode: str = "whole", burn_captions: bool = False, duck: bool = False) -> dict:
    """Run the compose-first finish DAG for a comp. Returns a summary dict.

    `burn_captions` (default OFF): incremental mode composites captions as a SEPARATE full-length
    transparent overlay render — a single un-chunked ~20-min render that this host currently renders
    OPAQUE (no alpha) and then discards. Captions already live in the composition (index.html/Studio)
    and YouTube takes a soft .srt, so burning is opt-in — reserve it for muted-autoplay social cutdowns
    (and reimplement it chunked / via an ffmpeg-ASS burn when we do)."""
    pdir = _project_dir(comp)
    py = [sys.executable, "-X", "utf8"]
    audio = str(SKILL_SCRIPTS / "audio.mjs")
    # fail LOUD up front if a skill script path is wrong (a silent bad node path left a stale index + cost a render)
    for _s in ("audio.mjs", "captions.mjs", "assemble-index.mjs"):
        if not (SKILL_SCRIPTS / _s).exists():
            raise RuntimeError(f"hf-finish: skill script missing — {SKILL_SCRIPTS / _s}. Is the faceless-explainer skill installed?")
    print(f"hf-finish: {comp}  (render={render}/{render_mode}, sound={sound}{', DRY-RUN' if dry_run else ''})")

    # 0 · guarantee STORYBOARD.md (audio/captions/assemble-index HARD-require it; new_essay doesn't scaffold it)
    if not dry_run:
        _sb = ensure_storyboard(comp)
        if not (pdir / "STORYBOARD.md").exists():
            raise RuntimeError(f"hf-finish: STORYBOARD.md missing and could not be synthesized at {_sb}")

    # 1 · frame durations FROM the VO (narration owns duration)
    _run("sync-durations", ["node", audio, "sync-durations", "--audio-meta", "./audio_meta.json",
                            "--storyboard", "./STORYBOARD.md"], cwd=pdir, dry=dry_run, soft=True)
    # 2 · word-sync: force-align the VO, place each scene + fire its highlight on the spoken word
    _run("word-sync", py + ["-m", "nolan.hyperframes.sync", str(pdir)], dry=dry_run)
    # 2b · advisory (⑨): the reliever exists but wasn't in the loop — surface long static holds so the
    #      author can `nolan.hyperframes.relieve` them (or accept), instead of finding them post-render.
    if not dry_run:
        try:
            from .relieve import long_holds
            holds = long_holds(str(pdir))
            if holds:
                print(f"⚠ {len(holds)} long static hold(s) — consider "
                      f"`python -X utf8 -m nolan.hyperframes.relieve {comp}`:")
                for h in holds[:6]:
                    print(f"    {h.get('frame')}/{h.get('scene')} [{h.get('block')}] "
                          f"{h.get('dur')}s — {h.get('verdict')}")
        except Exception as e:
            print(f"  (long-hold advisory skipped: {type(e).__name__}: {e})")
    # 2c · VISUAL-LAG GATE: catch a scene whose visual trails the narration (a late/closing anchor left
    #      the previous scene overrunning) or a MIS-ORDERED scene, BEFORE the render spend — this is the
    #      drift the eye catches (the 3:13-says-43%-shows-at-3:33 class). Loud, pre-render; not a hard block
    #      (a mis-order needs a human spec reorder), but impossible to miss.
    if not dry_run:
        try:
            from .sync import sync_gate_report
            gate = sync_gate_report(str(pdir))
            lags, lates = gate["visual_lag"], gate["late_anchors"]
            mis = [lf for lf in lags if lf.get("kind") == "misorder"]
            if lags:
                print(f"\n⚠ VISUAL-LAG GATE — {len(lags)} scene(s) where the VISUAL trails the narration "
                      f"({len(mis)} MIS-ORDERED). The eye catches this drift; fix before shipping:")
                for lf in lags:
                    if lf.get("kind") == "misorder":
                        print(f"    {lf['frame']}/{lf['scene']} ({lf['block']}) — topic narrated @{lf['content_at']}s, "
                              f"BEFORE the previous scene's @{lf['prev_content_at']}s → REORDER these scenes in the spec")
                    else:
                        print(f"    {lf['frame']}/{lf['scene']} ({lf['block']}) — placed @{lf['start']}s but its content "
                              f"is spoken @{lf['content_at']}s (lag {lf['lag']}s) → anchor it to an EARLIER phrase")
            if lates:
                print(f"  ◆ {len(lates)} scene(s) anchored to a LATE/closing phrase (placement auto-corrects, "
                      f"but re-anchor to the OPENING for robustness): "
                      + ", ".join(f"{a['frame']}/{a['scene']}" for a in lates[:8]))
            if lags or lates:
                print("  (run `python -X utf8 -m nolan.hyperframes.sync <comp> --report` to re-check after fixing)")
        except Exception as e:
            print(f"  (visual-lag gate skipped: {type(e).__name__}: {e})")
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
        _snap = _json.loads(am.read_text(encoding="utf-8")).get("voices", []) if (am.exists() and not dry_run) else []
        before = len(_snap)
        _run("bgm", ["node", audio, "fetch-bgm", "--storyboard", "./STORYBOARD.md", "--hyperframes", "."],
             cwd=pdir, dry=dry_run, soft=True)
        _run("sfx", ["node", audio, "fetch-sfx", "--storyboard", "./STORYBOARD.md", "--hyperframes", "."],
             cwd=pdir, dry=dry_run, soft=True)
        # The skill's node bgm/sfx engine serializes its OWN (compose-first-unaware, empty) audio model back
        # over audio_meta.json, clobbering the bridged voices[] → a silent render (the guard below caught this
        # on the first full-pipeline run). RESTORE the bridged voices if the node steps dropped them, keeping
        # anything they legitimately added (e.g. a bgm field). Makes `hf-finish` usable with sound ON.
        if before and not dry_run and am.exists():
            _cur = _json.loads(am.read_text(encoding="utf-8"))
            if len(_cur.get("voices", [])) < before:
                _cur["voices"] = _snap
                am.write_text(_json.dumps(_cur, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"  ↺ restored {before} bridged voice(s) the node sound step dropped (kept bgm/sfx)")
        # 4b · SCENE-level SFX (compose-first): read scene.data.sfx off the ALIGNED specs →
        #      resolve from the curated bank (nolan.sound) → stage into assets/sfx/ → merge into
        #      audio_meta.sfx (assemble-index mounts them on track 20+i). Preserves voices[].
        #      DUCK mode SKIPS the flat mount — SFX are added post-render by sfx_mix with the VO
        #      sidechain-ducked under each cue (natural gains), so the render stays VO(+bgm)-only.
        if duck:
            print("  [scene-sfx] deferred → ducked post-mix (render stays VO-only)")
        elif dry_run:
            print("  [scene-sfx] read scene.data.sfx → resolve + stage → merge into audio_meta.sfx")
        else:
            try:
                from .sound import apply_scene_sfx
                res = apply_scene_sfx(comp)
                print(f"▶ scene-sfx\n  {res['events']} cue(s) placed, {res['staged']} file(s) staged")
                if res.get("invalid"):
                    print("  ⚠ malformed sfx cues: " + "; ".join(res["invalid"][:6]))
                if res.get("unresolved"):
                    gaps = ", ".join(f"{u['frame']}/{u['scene']}:{u['cue']}" for u in res["unresolved"][:6])
                    print(f"  ⚠ {len(res['unresolved'])} cue(s) with no curated sound (bank gap): {gaps}")
            except Exception as e:
                print(f"  ⚠ scene-sfx skipped ({type(e).__name__}: {e})")
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
    # 7.5 · deterministic layout lint (composition gate v2): overlap / caption-band / off-canvas on the
    #       composed frames' declared geometry — structural, pre-render, cheap. Soft: report before the
    #       render spend; the VLM render-gate + human LOOK stay the perceptual passes.
    _cg = pdir / "caption_groups.json"
    _cap_on = _cg.exists() and _cg.stat().st_size > 4
    _layout_cmd = py + ["-m", "nolan.hyperframes.layout_lint", str(pdir)] + ([] if _cap_on else ["--no-captions"])
    _run("layout", _layout_cmd, dry=dry_run, soft=True)
    if not render:
        print("hf-finish: stopped before render (--no-render). Preview then re-run to render.")
        return {"comp": comp, "rendered": False}
    # 8 · RENDER — MODE SWITCH (steps 1–7 above + step-9 QA below are SHARED). `whole`: one npx render of
    #     the assembled index.html. `incremental`: window that SAME index per-frame + concat (cached — a
    #     one-frame edit re-renders one frame, not the monolith). Both write renders/video.mp4.
    if render_mode == "incremental":
        if dry_run:
            print("  [render] incremental — window index.html per-frame + concat → renders/video.mp4")
        else:
            print("▶ render (incremental — per-frame windows of the assembled index)")
            from .incremental import render_incremental
            r = render_incremental(comp, out=pdir / "renders" / "video.mp4", captions=burn_captions)
            if not r.get("ok"):
                raise RuntimeError("hf-finish: incremental render failed — see output above")
            print(f"  incremental: {r.get('rendered', 0)} rendered, {r.get('reused', 0)} reused")
    else:
        # For the target 7-8 min format the single long ffmpeg encode times out; chunked encode is safer.
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
    # 8b · DUCKED SFX post-mix: the render above is VO(+bgm)-only, so now mix the scene SFX ON TOP
    #      with that audio sidechain-ducked under each cue (natural registry gains, no re-alignment —
    #      amplitude only). Replaces video.mp4 in place so QA + downstream see the final mix. Idempotent:
    #      the VO-only render always precedes this, so there is no double-mix.
    if duck:
        if dry_run:
            print("  [duck] sfx_mix: mix SFX onto the VO-only render, VO sidechain-ducked → video.mp4")
        else:
            try:
                from .sfx_mix import sfx_mix
                final = pdir / "renders" / "video.mp4"
                res = sfx_mix(comp, video_in=str(final), out=str(pdir / "renders" / "video.sfx.mp4"))
                os.replace(res["out"], final)
                print(f"▶ duck\n  {res['events']} SFX ducked-mixed onto the VO-only render → renders/video.mp4")
                if res.get("unresolved"):
                    print(f"  ⚠ {len(res['unresolved'])} cue(s) with no curated sound (bank gap)")
            except Exception as e:
                print(f"  ⚠ ducked sfx-mix skipped ({type(e).__name__}: {e}) — render left VO-only")
    # 9 · QA (soft: report — don't crash the driver on a gate fail)
    _run("hf-qa", py + ["-m", "nolan.hf_qa", str(pdir)], dry=dry_run, soft=True)          # freeze + audio (ffmpeg)
    _run("style-lint", py + ["-m", "nolan.style_contract", str(pdir)], dry=dry_run, soft=True)  # spec dimensions
    _run("temporal", py + ["-m", "nolan.hyperframes.temporal_gate", str(pdir)], dry=dry_run, soft=True)  # motion: frozen/static/dead-air
    _run("perceptual", py + ["-m", "nolan.hyperframes.render_gate", str(pdir)], dry=dry_run, soft=True)  # VLM: legibility + relevance
    print("hf-finish: done → renders/video.mp4")
    return {"comp": comp, "rendered": True}


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan hf-finish", description="Run the compose-first finish DAG.")
    ap.add_argument("comp", help="composition id / dir")
    ap.add_argument("--no-render", action="store_true", help="stop before the render (assemble + preview)")
    ap.add_argument("--no-sound", action="store_true", help="skip the bgm/sfx bed")
    ap.add_argument("--duck", action="store_true",
                    help="ducked SFX: render VO-only, then post-mix cues with the VO sidechain-ducked "
                         "under each hit (natural gains) instead of the flat, hot render-mount")
    ap.add_argument("--dry-run", action="store_true", help="print the DAG without running it")
    ap.add_argument("--render", dest="render_mode", default="whole", choices=["whole", "incremental"],
                    help="whole = one npx render of index.html (master/verify); incremental = per-frame "
                         "windows of the SAME index + concat (fast iteration, cached)")
    ap.add_argument("--burn-captions", action="store_true",
                    help="incremental mode: composite the caption overlay INTO the mp4 (slow, opt-in — "
                         "captions already play in the composition; reserve this for muted-autoplay social)")
    a = ap.parse_args()
    try:
        finish(a.comp, render=not a.no_render, sound=not a.no_sound, dry_run=a.dry_run,
               render_mode=a.render_mode, burn_captions=a.burn_captions, duck=a.duck)
    except RuntimeError as e:
        print(f"\n✗ {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
