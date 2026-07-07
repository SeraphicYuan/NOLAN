"""Distill a raw KB source into parsed insight notes (P2).

Reads a status='raw' source, calls the LLM (qwen via OpenRouter) with the
video-craft prompt, parses + audits the JSON, and renders HYBRID notes:
one source-index note in parsed/ + N atomic technique notes in parsed/insights/,
each wikilinked back to the source and the raw transcript. Markdown stays canonical.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional

from . import paths
from . import sidecar
from .catalog import KBCatalog, Source
from . import taxonomy
from .prompts import SYSTEM, build_prompt

MAX_CONTENT_CHARS = 45000


# --------------------------------------------------------------------------- data
@dataclass
class Insight:
    title: str
    category: str
    technique: str = ""
    core_idea: str = ""
    how_to_apply: str = ""
    why_it_works: str = ""
    when_to_use: str = ""
    when_not: str = ""
    example: str = ""
    tools_or_assets: str = ""
    difficulty: str = "medium"
    tags: List[str] = field(default_factory=list)
    nolan_hook: str = "none"


@dataclass
class Distillation:
    tldr: str
    insights: List[Insight]
    creator_credibility: str = ""
    argument_quality: str = "MODERATE"
    freshness: str = "EVERGREEN"


# --------------------------------------------------------------------------- parse
def _strip_frontmatter(md: str) -> str:
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end != -1:
            return md[end + 4:].lstrip()
    return md


def _extract_json(text: str) -> dict:
    """Lenient: strip fences, take the outer object, repair trailing commas."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    a, b = t.find("{"), t.rfind("}")
    if a == -1 or b == -1:
        raise ValueError("no JSON object in LLM output")
    blob = t[a:b + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        fixed = re.sub(r",(\s*[}\]])", r"\1", blob)      # trailing commas
        return json.loads(fixed)


def _norm_insight(d: dict) -> Optional[Insight]:
    title = str(d.get("title") or "").strip()
    core = str(d.get("core_idea") or d.get("core") or "").strip()
    if not title or not core or core == "NOT_SPECIFIED":
        return None                                       # audit: drop empties
    tags = d.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    return Insight(
        title=title[:90],
        category=taxonomy.normalize_category(str(d.get("category", ""))),
        technique=str(d.get("technique") or "").strip(),
        core_idea=core,
        how_to_apply=str(d.get("how_to_apply") or "").strip(),
        why_it_works=str(d.get("why_it_works") or "").strip(),
        when_to_use=str(d.get("when_to_use") or "").strip(),
        when_not=str(d.get("when_not") or "").strip(),
        example=str(d.get("example") or "").strip(),
        tools_or_assets=str(d.get("tools_or_assets") or "").strip(),
        difficulty=taxonomy.normalize_enum(str(d.get("difficulty", "medium")),
                                           taxonomy.DIFFICULTY, "medium"),
        tags=[str(t).strip().lower() for t in tags if str(t).strip()][:6],
        nolan_hook=taxonomy.normalize_enum(str(d.get("nolan_hook", "none")),
                                           taxonomy.NOLAN_HOOKS, "none"),
    )


def _normalize(data: dict) -> Distillation:
    raw_insights = data.get("insights") or []
    insights = [i for i in (_norm_insight(d) for d in raw_insights if isinstance(d, dict)) if i]
    if not insights:
        raise ValueError("distillation produced no usable insights")
    sq = data.get("source_quality") or {}
    return Distillation(
        tldr=str(data.get("tldr") or "").strip(),
        insights=insights,
        creator_credibility=str(sq.get("creator_credibility") or "").strip(),
        argument_quality=str(sq.get("argument_quality") or "MODERATE").strip().upper(),
        freshness=str(sq.get("freshness") or "EVERGREEN").strip().upper(),
    )


# --------------------------------------------------------------------------- llm
async def _distill_async(title: str, content: str) -> Distillation:
    from nolan.config import load_config
    from nolan.llm import create_text_llm
    content = content[:MAX_CONTENT_CHARS]
    prompt = build_prompt(title, content, taxonomy.length_guidance(len(content)))
    llm = create_text_llm(load_config())
    raw = await llm.generate(prompt, system_prompt=SYSTEM)
    return _normalize(_extract_json(raw))


def distill_text(title: str, content: str) -> Distillation:
    return asyncio.run(_distill_async(title, content))


# --------------------------------------------------------------------------- render
def _yaml_str(v) -> str:
    s = str(v or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()
    return f'"{s}"'


def _yaml_list(items) -> str:
    return "[" + ", ".join(_yaml_str(i) for i in items) + "]"


def _link(rel: str, label: str = "") -> str:
    """A vault-relative, path-qualified Obsidian wikilink (disambiguates same-stem notes)."""
    rel = rel[:-3] if rel.endswith(".md") else rel
    rel = rel.replace("\\", "/")
    return f"[[{rel}|{label}]]" if label else f"[[{rel}]]"


def _insight_note(ins: Insight, source: Source, source_rel: str, raw_rel: str) -> str:
    fm = [
        "---", "kb: insight",
        f"category: {ins.category}",
        f"technique: {_yaml_str(ins.technique)}",
        f"difficulty: {ins.difficulty}",
        f"nolan_hook: {ins.nolan_hook}",
        f"tags: {_yaml_list(ins.tags)}",
        f"source: {_yaml_str(_link(source_rel, source.title))}",
        f"source_url: {_yaml_str(source.url)}",
        f"source_id: {source.id}",
        f"when_to_use: {_yaml_str(ins.when_to_use)}",
        "---", "",
    ]
    body = [f"# {ins.title}", ""]
    if ins.technique:
        body.append(f"**Technique:** {ins.technique}\n")
    body.append(f"**Core idea:** {ins.core_idea}\n")
    if ins.how_to_apply:
        body.append(f"**How to apply:** {ins.how_to_apply}\n")
    if ins.why_it_works:
        body.append(f"**Why it works:** {ins.why_it_works}\n")
    if ins.when_to_use:
        body.append(f"**When to use:** {ins.when_to_use}")
    if ins.when_not and ins.when_not != "NOT_SPECIFIED":
        body.append(f"**When NOT to:** {ins.when_not}")
    body.append("")
    if ins.example and ins.example != "NOT_SPECIFIED":
        body.append(f"**Example:** {ins.example}\n")
    if ins.tools_or_assets and ins.tools_or_assets != "NOT_SPECIFIED":
        body.append(f"**Tools / assets:** {ins.tools_or_assets}\n")
    body.append("---")
    body.append(f"From {_link(source_rel, source.title)} · raw: {_link(raw_rel, 'transcript')}")
    return "\n".join(fm + body) + "\n"


def _source_note(dist: Distillation, source: Source, insight_links: List[str], raw_rel: str) -> str:
    cats = sorted({i.category for i in dist.insights})
    fm = [
        "---", "kb: source",
        f"id: {source.id}",
        f"source_type: {source.source_type}",
        f"title: {_yaml_str(source.title)}",
        f"url: {_yaml_str(source.url)}",
        f"author: {_yaml_str(source.author)}",
        f"insight_count: {len(dist.insights)}",
        f"categories: {_yaml_list(cats)}",
        f"argument_quality: {dist.argument_quality}",
        f"freshness: {dist.freshness}",
        "status: distilled",
        f"raw: {_yaml_str(_link(raw_rel, 'transcript'))}",
        "---", "",
    ]
    body = [f"# {source.title}", "", f"> {dist.tldr}", ""]
    if dist.creator_credibility and dist.creator_credibility != "NOT_SPECIFIED":
        body.append(f"**Creator:** {dist.creator_credibility}")
    body.append(f"**Quality:** {dist.argument_quality} · {dist.freshness} · {len(dist.insights)} techniques\n")
    body.append("## Techniques")
    body += insight_links
    body.append("")
    body.append("---")
    url_part = f"[watch]({source.url}) · " if source.url else ""
    body.append(f"Source: {url_part}raw transcript: {_link(raw_rel, 'transcript')}")
    return "\n".join(fm + body) + "\n"


# --------------------------------------------------------------------------- orchestration
@dataclass
class DistillResult:
    source_id: str
    source_note: Path
    insight_notes: List[Path]
    n_insights: int


def distill_source(source_id: str, *, catalog: Optional[KBCatalog] = None,
                   force: bool = False) -> DistillResult:
    paths.ensure_dirs()
    cat = catalog or KBCatalog()
    src = cat.get(source_id)
    if src is None:
        raise ValueError(f"unknown source id: {source_id}")
    if src.status == "distilled" and not force:
        raise ValueError(f"already distilled (use force): {src.title}")

    raw_file = paths.VAULT / src.raw_path
    body = _strip_frontmatter(raw_file.read_text(encoding="utf-8"))
    dist = distill_text(src.title, body)

    stem = raw_file.stem
    raw_rel = src.raw_path                        # e.g. "raw/youtube/<stem>.md" (vault-relative)
    source_rel = f"parsed/{stem}.md"
    source_note_path = paths.PARSED / f"{stem}.md"

    # clear stale insight notes from a prior distill (titles/slugs change per run)
    for old in paths.INSIGHTS.glob(f"{stem}__*.md"):
        old.unlink()

    insight_paths, links, sidecar_insights = [], [], []
    for i, ins in enumerate(dist.insights, 1):
        islug = taxonomy_slug(ins.title)
        ipath = paths.INSIGHTS / f"{stem}__{i:02d}_{islug}.md"
        insight_rel = f"parsed/insights/{ipath.stem}.md"
        ipath.write_text(_insight_note(ins, src, source_rel, raw_rel), encoding="utf-8")
        insight_paths.append(ipath)
        links.append(f"- {_link(insight_rel, ins.title)}  (`{ins.category}`)")
        sidecar_insights.append({"id": ipath.stem, "seq": i, "path": insight_rel, **asdict(ins)})

    source_note_path.write_text(_source_note(dist, src, links, raw_rel), encoding="utf-8")

    # Structured sidecar — the reliable rebuild source for the derived index.
    record = {
        "source_id": src.id, "source_type": src.source_type,
        "title": src.title, "url": src.url, "author": src.author,
        "raw_path": raw_rel, "source_note": source_rel,
        "tldr": dist.tldr, "argument_quality": dist.argument_quality,
        "freshness": dist.freshness, "creator_credibility": dist.creator_credibility,
        "distilled_at": time.time(), "insights": sidecar_insights,
    }
    sidecar.write(record)

    cat.set_status(src.id, "distilled")

    # Incremental index update (keyword FTS + vectors). Best-effort: a distill
    # must not fail because the derived index is unavailable — `kb reindex`
    # rebuilds it from the sidecar. Delete-then-insert mirrors the .md refresh.
    try:
        from .index import KBIndex
        KBIndex().index_record(record, replace=True)
    except Exception as e:  # pragma: no cover - index is derived/optional
        print(f"[kb] warning: index update skipped for {src.id}: {e}")

    return DistillResult(src.id, source_note_path, insight_paths, len(dist.insights))


def taxonomy_slug(title: str, maxlen: int = 40) -> str:
    from nolan.publish.source import slugify
    return slugify(title or "insight", maxlen=maxlen) or "insight"
