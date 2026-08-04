"""What the judge is entitled to read, resolved to real paths — ONE source of truth.

The fleet executor hands an agent a brief full of PATHS and the agent opens them itself. An API
call cannot do that: the model sees exactly one string, so every file has to be inlined. Those two
executors would drift the moment someone added a rubric dimension reading a new input, and the
comparison between them would quietly stop being a comparison.

So both resolve their context through here, and `test_context_parity.py` asserts this covers every
token in `tasks._REVIEW_INPUTS`. If a dimension starts reading something new and this map does not
know about it, the test fails rather than the API judge silently getting less to work with than
the agent did.

`style` is in that token list because of the style-fidelity dimension, which is the whole reason
this run exists — and it is the single largest input at ~5.2k tokens, 27% of the read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]


def context_paths(slug: str, store) -> Dict[str, Path]:
    """`{token: path}` for every `_REVIEW_INPUTS` token that EXISTS for this project.

    Missing optional files (a project with no factcheck.md yet) are simply absent from the map —
    the caller reports what it inlined, so an absence is visible rather than assumed.
    """
    sg = Path(store.root) / slug / "scriptgen"
    meta = store.get(slug)
    out: Dict[str, Path] = {}
    for token, rel in (("brief", "brief.md"), ("facts", "facts.md"),
                       ("beatmap", "beatmap.md"), ("citations", "citations.md"),
                       ("factcheck", "factcheck.md")):
        p = sg / rel
        if p.is_file():
            out[token] = p
    guide = REPO / "script_styles" / str(meta.get("style_id") or "") / "style_guide.md"
    if guide.is_file():
        out["style"] = guide
    return out


def draft_pair(slug: str, store) -> Tuple[Optional[Path], Optional[Path]]:
    """`(previous, current)` — the pairwise judge compares a CHANGE, so it needs both."""
    sg = Path(store.root) / slug / "scriptgen" / "drafts"
    drafts = sorted(sg.glob("draft-*.md"))
    if not drafts:
        return None, None
    return (drafts[-2] if len(drafts) > 1 else None), drafts[-1]


def inline_bundle(slug: str, store, *, skip: Tuple[str, ...] = ()) -> Tuple[str, List[str]]:
    """Every context file as one string, plus a manifest of what went in.

    Returns `(text, notes)` — `notes` records each file and its size so a run can report the
    context it actually sent rather than the context it meant to send.
    """
    parts: List[str] = []
    notes: List[str] = []
    prev, cur = draft_pair(slug, store)
    for token, p in sorted(context_paths(slug, store).items()):
        if token in skip:
            notes.append(f"{token}: SKIPPED")
            continue
        body = p.read_text(encoding="utf-8", errors="replace")
        parts.append(f"\n\n===== {token.upper()} · {p.name} =====\n{body}")
        notes.append(f"{token}: {len(body):,} ch")
    for label, p in (("previous draft", prev), ("current draft", cur)):
        if p is None:
            notes.append(f"{label}: (none)")
            continue
        body = p.read_text(encoding="utf-8", errors="replace")
        parts.append(f"\n\n===== {label.upper()} · {p.name} =====\n{body}")
        notes.append(f"{label} ({p.name}): {len(body):,} ch")
    return "".join(parts), notes
