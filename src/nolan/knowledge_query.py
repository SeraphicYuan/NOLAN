"""Knowledge-driven asset-query bridge — turn a beat (with WHOLE-SCRIPT context) into SPECIFIC,
era-correct search queries by tapping the model's own internal knowledge.

Today NOLAN's stock-query builder (`external_assets.build_query_variants`) literally *strips*
proper nouns and broadens to generic phrases ("archival documentary footage"). That throws away
the one thing an LLM editor is best at: knowing that a Homer / Odyssey beat should pull
Waterhouse's *Ulysses and the Sirens*, the François Vase, Turner's *Ulysses deriding Polyphemus*,
a red-figure krater — not "ancient greek scene stock".

Given a `ScriptContext` + a beat index, this asks the model to name concrete, sourceable assets
(famous artworks with artist+title, specific objects/artifacts, landmarks, archival imagery) plus
the search phrases to find them — AND to derive the beat's period/locale so the anachronism gate
no longer needs hand-typed strings. It complements the evocative operators (which find *evocative*
b-roll); this finds the *right specific real* asset.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .script_context import ScriptContext

# what kind of asset we want the model to reach for
_KIND_GUIDE = {
    "artwork": "Prioritize FAMOUS ARTWORKS: name the artist + the exact title of paintings, "
               "sculptures, frescoes, vase-paintings, engravings that depict or evoke this beat.",
    "footage": "Prioritize FILMABLE FOOTAGE: real places, landscapes, objects, phenomena, and "
               "archival/document imagery that a stock library would hold.",
    "any": "Reach for the STRONGEST specific asset of any kind — famous artworks (artist + title), "
           "real places/objects/landmarks, archival imagery, or documentary footage.",
}


@dataclass
class NamedAsset:
    title: str                       # "Ulysses and the Sirens"
    creator: str = ""                # "J. W. Waterhouse, 1891"
    kind: str = ""                   # painting | sculpture | vase | photo | place | artifact
    search: str = ""                 # the phrase to actually find it
    why: str = ""

    def to_dict(self) -> dict:
        return {"title": self.title, "creator": self.creator, "kind": self.kind,
                "search": self.search, "why": self.why}


@dataclass
class KnowledgeQueries:
    beat_idx: int
    queries: List[str] = field(default_factory=list)      # ordered search phrases, specific→general
    named_assets: List[NamedAsset] = field(default_factory=list)
    period: str = ""                 # derived era hint (for the gate)
    locale: str = ""                 # derived culture hint
    avoid: List[str] = field(default_factory=list)        # literal/anachronistic things to NOT search
    source: str = "llm"

    def all_queries(self) -> List[str]:
        """Named-asset search phrases first (most specific), then the general queries."""
        seen, out = set(), []
        for a in self.named_assets:
            q = (a.search or a.title).strip()
            if q and q.lower() not in seen:
                seen.add(q.lower()); out.append(q)
        for q in self.queries:
            if q and q.lower() not in seen:
                seen.add(q.lower()); out.append(q)
        return out

    def to_dict(self) -> dict:
        return {"beat_idx": self.beat_idx, "queries": self.queries,
                "named_assets": [a.to_dict() for a in self.named_assets],
                "period": self.period, "locale": self.locale, "avoid": self.avoid,
                "source": self.source}


_SYS = (
    "You are a visual researcher for a documentary editor. You know art history, material culture, "
    "geography, and archival collections deeply. Given a narration beat you name the SPECIFIC, "
    "period- and culture-correct images a professional would actually source — by title and maker "
    "where they exist — never generic stock. Reply STRICT JSON only.")


def _prompt(ctx: ScriptContext, beat_idx: int, kind: str, n: int) -> str:
    guide = _KIND_GUIDE.get(kind, _KIND_GUIDE["any"])
    return (
        f"{ctx.brief(max_chars=1600)}\n\n"
        f"{ctx.beat_context(beat_idx)}\n\n"
        f"TASK: {guide}\n"
        "Use your OWN knowledge — name real works/objects/places by their actual names. Everything "
        "must be plausible for this beat's era and culture (derive them and state them). Give, in "
        f"order of specificity, up to {n} concrete SEARCH PHRASES an editor could paste into a stock/"
        "image search to find these. Also flag the on-the-nose literal things we should NOT search.\n"
        'JSON: {"period": "<era, e.g. Bronze-Age / ancient Greece, or timeless>", '
        '"locale": "<culture/place>", '
        '"named_assets": [{"title": "<work/object/place name>", "creator": "<artist+year or empty>", '
        '"kind": "painting|sculpture|vase|fresco|photo|place|artifact|footage", '
        '"search": "<exact search phrase to find it>", "why": "<why it fits this beat, <=12 words>"}], '
        '"queries": ["<general fallback search phrases, specific first>"], '
        '"avoid": ["<literal/anachronistic things NOT to search>"]}')


def expand_queries(ctx: ScriptContext, beat_idx: int, *, llm, kind: str = "any",
                   n: int = 6) -> KnowledgeQueries:
    """Ask the model to name specific, era-correct assets + search phrases for one beat.
    Returns a KnowledgeQueries; on any failure returns an empty one (caller can fall back)."""
    try:
        txt = _run(llm.generate(_prompt(ctx, beat_idx, kind, n), _SYS))
        raw = _extract_json(txt)
    except Exception:
        raw = {}
    named = []
    for a in (raw.get("named_assets") or [])[:n]:
        if not isinstance(a, dict) or not a.get("title"):
            continue
        named.append(NamedAsset(title=str(a.get("title", "")).strip(),
                                creator=str(a.get("creator", "")).strip(),
                                kind=str(a.get("kind", "")).strip(),
                                search=str(a.get("search", "")).strip(),
                                why=str(a.get("why", "")).strip()))
    queries = [str(q).strip() for q in (raw.get("queries") or []) if str(q).strip()][:n]
    avoid = [str(q).strip() for q in (raw.get("avoid") or []) if str(q).strip()]
    return KnowledgeQueries(beat_idx=beat_idx, queries=queries, named_assets=named,
                            period=str(raw.get("period", "")).strip(),
                            locale=str(raw.get("locale", "")).strip(), avoid=avoid,
                            source="llm" if (named or queries) else "empty")


# ---- utils (shared shape with tempo_plan) -----------------------------------
def _run(coro):
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(lambda: asyncio.run(coro)).result()


def _extract_json(text: str) -> dict:
    if not text:
        return {}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}
