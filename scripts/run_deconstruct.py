"""Headless video-deconstruction runner (same code path as the hub job).

Runs Tier-1 facts + Tier-2 extract for one ingested library video, writes all
artifacts to video_deconstructions/<slug>/, and (optionally) dispatches the
synthesis task to a tmux Claude agent.

Usage:
    D:/env/nolan/python.exe -X utf8 scripts/run_deconstruct.py --match "Odyssey Explained"
    D:/env/nolan/python.exe -X utf8 scripts/run_deconstruct.py --match "..." --session nolan5
    (omit --session to skip the agent dispatch; add --no-vision / --no-llm to degrade)
"""

import argparse
import asyncio
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Job:
    """Minimal stand-in for the hub's job object."""

    def set_progress(self, p, msg):
        print(f"[{p*100:5.1f}%] {msg}", flush=True)

    def log(self, msg):
        print(f"        {msg}", flush=True)


def find_video(db: Path, needle: str) -> str:
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT path FROM videos WHERE path LIKE ?", (f"%{needle}%",)).fetchall()
    conn.close()
    if not rows:
        raise SystemExit(f"no library video matching {needle!r}")
    if len(rows) > 1:
        for (p,) in rows:
            print("  match:", p)
        raise SystemExit("ambiguous --match; be more specific")
    return rows[0][0]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True, help="substring of the library video path")
    ap.add_argument("--session", default="", help="tmux agent for synthesis (omit = no dispatch)")
    ap.add_argument("--provider", default="openrouter")
    ap.add_argument("--profile", default="balanced")
    ap.add_argument("--no-vision", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()

    from nolan.config import load_config
    from nolan.deconstruct import (DeconstructionStore, build_extract,
                                   deconstruction_synthesis_task)
    from nolan.indexer import VideoIndex
    from nolan.llm import create_text_llm
    from nolan.video_style import pairing as pairing_mod
    from nolan.vision import create_vision_provider
    from nolan.webui.operations import _dispatch_to_tmux, _select_vision

    job = Job()
    config = load_config()
    db = Path(config.indexing.database).expanduser()
    video_path = find_video(db, args.match)
    print("video:", video_path, flush=True)

    index = VideoIndex(db)
    store = DeconstructionStore(Path("video_deconstructions"))
    title = Path(video_path).stem
    slug = store.create(video_path, title=title)
    print("slug:", slug, flush=True)

    llm = None
    if not args.no_llm:
        try:
            llm = create_text_llm(config)
            job.log(f"text llm: {config.llm.provider} {config.llm.model}")
        except Exception as e:
            job.log(f"text LLM unavailable ({e}) — fallbacks")
    try:
        job.set_progress(0.02, "Loading BGE embedder…")
        embedder = pairing_mod.make_bge_embedder()
    except Exception as e:
        embedder = None
        job.log(f"BGE unavailable ({e})")
    vision = None
    if not args.no_vision:
        try:
            vp = create_vision_provider(_select_vision(config, args.provider, None, None, None))
            vision = vp if await vp.check_connection() else None
            job.log(f"vision: {'ok' if vision else 'unreachable — motion-only facts'}")
        except Exception as e:
            job.log(f"vision setup failed ({e})")

    job.set_progress(0.1, "Extract: shots → motion → vision → beats → operators → tempo…")
    extract, plan = await build_extract(video_path, index, llm=llm, embed=embedder,
                                        vision_provider=vision,
                                        frames_dir=store.frames_dir(slug),
                                        profile=args.profile)
    store.write_extract(slug, extract)
    store.write_plan(slug, plan)
    store.set_status(slug, "extracted")
    store.task_path(slug).write_text(
        deconstruction_synthesis_task(slug, title, video_path), encoding="utf-8")
    job.set_progress(0.9, f"extract done: {extract['shot_count']} shots → "
                          f"{len(extract['beats'])} beats (beats:{extract['beat_source']}, "
                          f"operators:{extract['operator_source']})")

    if args.session:
        task_posix = f"video_deconstructions/{slug}/synthesis_task.md"
        breakdown_posix = f"video_deconstructions/{slug}/breakdown.md"
        msg = (f"New NOLAN video deconstruction synthesis task — please read and "
               f"complete {task_posix} now, writing the breakdown to {breakdown_posix} "
               f"and refining the recovered plan.")
        _dispatch_to_tmux(args.session, msg)
        job.set_progress(1.0, f"synthesis dispatched to {args.session}")
    else:
        job.set_progress(1.0, "no --session: synthesis NOT dispatched (task file ready)")


if __name__ == "__main__":
    asyncio.run(main())
