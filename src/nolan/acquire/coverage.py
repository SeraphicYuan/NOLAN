"""Named-entity <-> library/pool coverage check — the acquisition analog of the anchor-lint.

The narration can NAME a subject that nothing in the library/pool can depict: the holbein essay says
"pope" four times, but gutenberg-21790 has cardinal / bishop / abbot / emperor / king and NO pope — a
gap only the author caught, by happening to know the corpus (POST_MORTEM #8). This surfaces it at
PLAN time: extract the depictable named subjects the script references, probe whether the library (a
title match — reuses the named-work retrieval from POST_MORTEM #3) or the acquired pool can depict
each, and report the gaps LOUD before authoring — so the author stops being the coverage detector of
last resort.

Pure prompt / parse / probe (unit-testable without an LLM); the entity extraction is an injected
LLM call, same shape as derive_asset_needs / judge.

  python -X utf8 -m nolan.acquire.coverage --comp <slug> [--script SOURCE.md] [--library global]
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from nolan.imagelib.store import _distinctive_tokens


# --- pure prompt / parse (testable without an LLM) ------------------------------------------------
def entity_prompt(script: str) -> str:
    return (
        "You audit a video-essay script for VISUAL COVERAGE. List the CONCRETE, DEPICTABLE subjects the "
        "narration NAMES that a viewer would expect to SEE on screen — specific people, named works / "
        "artifacts, named places, and concrete objects. INCLUDE named roles the essay leans on (e.g. "
        "'pope', 'knight', 'merchant'). EXCLUDE pure abstractions (mortality, satire, irony), generic "
        "connective words, and anything not visually depictable.\n"
        "Return ONLY a JSON array, each item: {\"name\":\"short depictable subject (1-3 words)\", "
        "\"kind\":\"person|work|place|object\", \"mentions\": <approx times the narration refers to it>}. "
        "No prose, no code fences.\n\nSCRIPT:\n" + (script or "")[:6000])


def extract_json_list(raw: str) -> List:
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    i, j = raw.find("["), raw.rfind("]")
    if not (0 <= i < j):
        return []
    try:
        data = json.loads(raw[i:j + 1])
    except (json.JSONDecodeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def parse_entities(raw: str) -> List[Dict]:
    """Normalize the LLM output into [{name, kind, mentions}], deduped by lowercased name."""
    out, seen = [], set()
    for it in extract_json_list(raw):
        name = (str(it.get("name", "")).strip() if isinstance(it, dict) else str(it).strip())
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        kind = str(it.get("kind", "")).strip().lower() if isinstance(it, dict) else ""
        try:
            mentions = int(it.get("mentions", 1)) if isinstance(it, dict) else 1
        except (TypeError, ValueError):
            mentions = 1
        out.append({"name": name, "kind": kind or "object", "mentions": max(1, mentions)})
    return out


# --- probes ---------------------------------------------------------------------------------------
def probe_library(name: str, library, floor: float = 0.5):
    """The best title-match hit for `name` in the library, or None. Reuses search_by_title (the
    named-work retrieval), so 'the ploughman' resolves to THE PLOUGHMAN and 'pope' resolves to
    nothing when the corpus has no pope."""
    if library is None:
        return None
    try:
        hits = library.search_by_title(name, k=1, min_cover=floor)
    except Exception:
        return None
    return hits[0] if hits else None


def probe_pool(name: str, pool: Optional[List[Dict]], floor: float = 0.5) -> Optional[Dict]:
    """The first pool asset whose caption/title/query distinctively covers the entity, or None."""
    ntok = set(_distinctive_tokens(name))
    if not ntok or not pool:
        return None
    for a in pool:
        if not isinstance(a, dict):
            continue
        hay = set(_distinctive_tokens(" ".join(str(a.get(k, "")) for k in ("caption", "title", "query"))))
        if hay and sum(1 for t in ntok if t in hay) / len(ntok) >= floor:
            return a
    return None


def check_coverage(entities: List[Dict], library=None, pool: Optional[List[Dict]] = None,
                   floor: float = 0.5) -> Dict:
    """For each named entity, is it depictable by the library (title match) or the pool? Returns
    {covered:[...], gaps:[...]} — a gap is a named subject NEITHER can depict."""
    covered, gaps = [], []
    for e in entities:
        name = e.get("name") if isinstance(e, dict) else str(e)
        if not name:
            continue
        lib_hit = probe_library(name, library, floor)
        pool_hit = probe_pool(name, pool, floor)
        rec = {"name": name, "kind": e.get("kind") if isinstance(e, dict) else None,
               "mentions": e.get("mentions", 1) if isinstance(e, dict) else 1,
               "in_library": bool(lib_hit), "in_pool": bool(pool_hit),
               "library_title": (lib_hit.asset.title if lib_hit else None)}
        (covered if (lib_hit or pool_hit) else gaps).append(rec)
    gaps.sort(key=lambda r: -int(r.get("mentions", 1)))       # loudest (most-mentioned) gaps first
    return {"covered": covered, "gaps": gaps}


async def extract_entities(script: str, client) -> List[Dict]:
    """LLM: script -> the depictable named subjects it references. `client` is a create_text_llm."""
    raw = await client.generate(script, system_prompt=entity_prompt(script))
    return parse_entities(raw)


# --- CLI ------------------------------------------------------------------------------------------
def _load_pool(comp_dir: Path) -> Optional[List[Dict]]:
    pj = comp_dir / "pool.json"
    if pj.exists():
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else data.get("assets") or []
        except (json.JSONDecodeError, OSError):
            return None
    return None


def main():
    import argparse
    import asyncio

    ap = argparse.ArgumentParser(prog="nolan.acquire.coverage",
                                 description="Plan-time named-entity ↔ library/pool coverage check")
    ap.add_argument("--comp", help="composition dir/slug (reads its SOURCE.md + pool.json)")
    ap.add_argument("--script", help="script file (defaults to <comp>/SOURCE.md)")
    ap.add_argument("--library", default="global", help="library scope to probe (default: global)")
    ap.add_argument("--floor", type=float, default=0.5, help="title/caption coverage floor (0..1)")
    a = ap.parse_args()

    comp_dir = None
    if a.comp:
        from nolan.hyperframes.edit import _comp_dir
        try:
            comp_dir = _comp_dir(a.comp)
        except Exception:
            comp_dir = Path(a.comp)
    script_path = Path(a.script) if a.script else (comp_dir / "SOURCE.md" if comp_dir else None)
    if not script_path or not script_path.exists():
        raise SystemExit("need a script: --script <file> or --comp <slug> with a SOURCE.md")
    script = script_path.read_text(encoding="utf-8")

    from nolan.config import load_config
    from nolan.llm import create_text_llm
    from nolan.imagelib.store import ImageLibrary
    entities = asyncio.run(extract_entities(script, create_text_llm(load_config())))
    library = ImageLibrary(a.library) if a.library else None
    pool = _load_pool(comp_dir) if comp_dir else None
    rep = check_coverage(entities, library=library, pool=pool, floor=a.floor)

    print(f"COVERAGE — {len(entities)} named subject(s); {len(rep['gaps'])} gap(s) "
          f"(library={a.library}{', +pool' if pool else ''})")
    for g in rep["gaps"]:
        print(f"  ⚠ '{g['name']}' ({g['kind']}, ×{g['mentions']}) — NOT depictable "
              "by the library or pool; the narration names it but nothing grounds it.")
    if not rep["gaps"]:
        print(f"  all named subjects are depictable ✓")
    else:
        print("  (advisory — general subjects may still be covered by stock/gen at acquire time; "
              "corpus-bound named works are the ones to fix here.)")


if __name__ == "__main__":
    main()
