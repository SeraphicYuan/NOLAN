"""Run-bundle filesystem utilities."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_run_dir(runs_dir: Path, project_id: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", project_id).strip("-") or "project"
    candidate = Path(runs_dir) / f"{stamp}-{slug}"
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = Path(runs_dir) / f"{stamp}-{slug}-{suffix}"
    candidate.mkdir(parents=True)
    return candidate


def write_json_atomic(path: Path, payload: Any) -> None:
    text = (
        payload.model_dump_json(indent=2)
        if hasattr(payload, "model_dump_json")
        else json.dumps(payload, indent=2, ensure_ascii=False)
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sha256_json(payload: Any) -> str:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
