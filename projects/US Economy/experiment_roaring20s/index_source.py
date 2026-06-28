"""Index the US Economy source video into a PROJECT-LOCAL database.

Part of the asset-first scene-building experiment (Roaring Twenties segment).
We deliberately do NOT use config.indexing.database (which points outside the
project at D:\\ClaudeProjects\\.nolan\\library.db). Instead we index into
projects/US Economy/index.db so the experiment stays self-contained and the
creator's own archival/chart frames become searchable b-roll candidates.

Usage:
    D:\\env\\nolan\\python.exe -X utf8 "projects/US Economy/experiment_roaring20s/index_source.py"
"""

import asyncio
from pathlib import Path

from nolan.config import load_config
from nolan.cli_legacy import _index_videos

PROJECT = Path("projects/US Economy")
DB_PATH = PROJECT / "index.db"


def find_source() -> Path:
    vids = sorted(PROJECT.glob("source/*.mp4"))
    if not vids:
        raise SystemExit("No .mp4 found under projects/US Economy/source/")
    return vids[0]


def main() -> None:
    config = load_config()
    # Redirect the index to a project-local DB (boundary rule + self-contained).
    config.indexing.database = str(DB_PATH)

    video = find_source()
    print(f"Source video : {video.name}")
    print(f"Index DB     : {DB_PATH}")
    print(f"Vision       : {config.vision.provider}:{config.vision.model}")
    print(f"Sampler      : {config.indexing.sampling_strategy}")
    print(f"Transcript   : SRT auto-detected (whisper disabled)\n")

    asyncio.run(_index_videos(
        config,
        video,
        recursive=False,
        frame_interval=5,
        sampling_strategy=config.indexing.sampling_strategy,
        vision_provider=config.vision.provider,
        whisper_enabled=False,            # .en.srt exists -> used automatically
        whisper_model="base",
        project_id=None,
        concurrency=8,                    # safer for the OpenRouter/Alibaba route
        force=False,
        is_single_file=True,
    ))
    print("\nIndexing complete.")


if __name__ == "__main__":
    main()
