"""Who was asking — recorded beside every judgement.

THE INCIDENT. The same draft, judged twice, scored 17 and 99 — 5.8x, zero high findings versus
six. Explaining that took an hour of git archaeology, and the answer was partly that the two runs
used different output contracts (one wrote prose alongside the findings, one did not) and thirteen
days of prompt changes sat between them. `findings.json` records WHAT was found and nothing
whatsoever about the instrument that found it, so two numbers that are not comparable look exactly
like two numbers that are.

Every downstream question — did this round improve, is the judge stable, is the metric drifting —
is unanswerable without this. It is the cheapest thing in the pipeline and the precondition for
everything else.

THE CODE WRITES WHAT THE CODE KNOWS. Asking the agent to self-report its own prompt version is
asking the instrument to describe itself; it can be wrong, lazy or silent, and a provenance record
nobody can trust is worse than none because it invites belief. So the brief's exact bytes, the
rubric, the archetype, the contract and the repo commit are all captured HERE, from the objects
that produced them. Only `model` and `session` come from the agent, because only the agent knows
them — and their absence is recorded rather than guessed.

`brief_sha256` is the field that matters most: it changes the moment ANY word of the dispatched
task changes, which is the exact thing that silently invalidated the Phase 2 comparison.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA = 1


def _repo_commit() -> Optional[str]:
    """The exact code that produced this judgement. A prompt is only half the instrument; the
    rubric, the gate and the task builders are the other half and they live in git."""
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=Path(__file__).resolve().parents[3],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def judge_provenance(slug: str, store, *, brief: str, draft_n: int,
                     unattended: bool, phase: str = "review") -> Dict[str, Any]:
    """Everything knowable about this judgement WITHOUT asking the agent."""
    from .rubrics import get_rubric

    meta = store.get(slug) or {}
    archetype = store.resolve_archetype(slug)
    rubric = get_rubric(archetype)
    dims = [d.id for d in rubric.review_dimensions()]

    return {
        "schema": SCHEMA,
        "phase": phase,
        "slug": slug,
        "draft": f"draft-{draft_n:02d}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        # --- the instrument -------------------------------------------------------------
        # The single most important field. Any change to the dispatched text — a reworded
        # dimension, a different output contract, a new constraint — moves this hash, so two
        # findings files can be compared only when it matches.
        "brief_sha256": hashlib.sha256(brief.encode("utf-8")).hexdigest(),
        "brief_chars": len(brief),
        "contract": "unattended" if unattended else "attended",
        "archetype": archetype,
        "rubric_dims": dims,
        # A rubric can be edited without its id changing; the ids alone would not notice.
        "rubric_sha256": hashlib.sha256(
            json.dumps([(d.id, d.weight, d.question) for d in rubric.review_dimensions()],
                       sort_keys=True).encode("utf-8")).hexdigest(),
        "nolan_commit": _repo_commit(),
        # --- the run's own parameters ---------------------------------------------------
        # Two runs that differ in style, angle or spine are not the same experiment, and
        # nothing recorded that before.
        "style_id": meta.get("style_id"),
        "angle": meta.get("chosen_angle") or meta.get("angle") or None,
        "spine": (meta.get("composite_spine") or {}).get("structure"),
        "target_minutes": meta.get("target_minutes"),
        "mode": meta.get("mode"),
        "store_root": str(getattr(store, "root", "")),
        # --- filled by the agent, absent if it did not ----------------------------------
        "model": None,
        "session": None,
    }


def provenance_path(store, slug: str, draft_n: int, phase: str = "review") -> Path:
    return store.reviews_dir(slug) / f"{phase}-{draft_n:02d}.provenance.json"


def write_provenance(store, slug: str, draft_n: int, prov: Dict[str, Any],
                     phase: str = "review") -> Path:
    p = provenance_path(store, slug, draft_n, phase)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(prov, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def read_provenance(store, slug: str, draft_n: int, phase: str = "review") -> Optional[dict]:
    p = provenance_path(store, slug, draft_n, phase)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def comparable(a: Optional[dict], b: Optional[dict]) -> "tuple[bool, str]":
    """Can these two judgements be compared? Returns `(verdict, reason)`.

    THE GUARD THE PHASE 2 ANALYSIS NEEDED AND DID NOT HAVE. Scores from different instruments are
    not two measurements of a draft; they are one measurement each of two different questions.
    Anything that trends, diffs or routes on a pair of reviews must ask this first and refuse
    rather than quietly produce a number.

    Missing provenance is NOT comparable. A pre-provenance findings file is exactly the case that
    caused the incident, and treating absence as "probably fine" would reintroduce it.
    """
    if not a or not b:
        return False, "one or both judgements have no provenance recorded"
    for field, label in (("brief_sha256", "the dispatched brief"),
                         ("rubric_sha256", "the rubric"),
                         ("contract", "the output contract"),
                         ("archetype", "the archetype")):
        if a.get(field) != b.get(field):
            return False, (f"{label} differs ({field}: "
                           f"{str(a.get(field))[:12]} vs {str(b.get(field))[:12]})")
    if a.get("nolan_commit") != b.get("nolan_commit"):
        # A weaker signal than the brief hash — much of the repo cannot affect a judgement — so
        # it warns rather than refuses, and says so.
        return True, (f"comparable, but the repo moved "
                      f"({a.get('nolan_commit')} -> {b.get('nolan_commit')})")
    return True, "same instrument"
