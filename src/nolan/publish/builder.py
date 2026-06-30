"""Publisher — orchestrates source -> scaffold -> (agent author) -> build -> deliver.

Mirrors `nolan.segment.builder`: a config dataclass, a result dataclass, and a
class with a `run()` entry. The deterministic steps use `toolkit`; the authoring
step drives a Claude agent via `orchestrator.claude_runner` (auto / review modes).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import toolkit
from .source import load_source, slugify
from nolan.skills import handoff

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / ".claude" / "skills" / "beautiful-article"

# Offline-font css2 URLs for the typographic themes (others fall back to system fonts).
THEME_FONTS = {
    "press": "https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=Source+Serif+4:opsz,wght@8..60,400&family=JetBrains+Mono:wght@400;500&display=swap",
    "bodoni": "https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700;900&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=JetBrains+Mono:wght@400;500&display=swap",
    "freddie": "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Hanken+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap",
}


@dataclass
class PublishConfig:
    theme: str = "press"
    type: str = "explainer"
    retention: str = "~90%"
    width: str = "regular"
    images: str = "none"
    cover: bool = True
    brand_color: str | None = None
    brand_mode: str = "light"
    embed_fonts: bool = True
    mode: str = "auto"  # "auto" = author+build; "review" = stop after scaffold for a human/agent
    out_dir: Path | None = None  # defaults to <repo>/projects/_published
    agent_timeout: int = 2400


@dataclass
class PublishResult:
    workspace: Path
    plan_path: Path | None = None
    article_html: Path | None = None
    ok: bool = False
    stopped_for_review: bool = False
    summary: str = ""
    notes: list[str] = field(default_factory=list)


class Publisher:
    def __init__(self, config: PublishConfig | None = None, nolan_config=None):
        self.cfg = config or PublishConfig()
        self.nolan_config = nolan_config

    # ---- deterministic ----
    def prepare(self, src: str, slug: str | None = None) -> tuple[Path, Path]:
        """Source -> workspace (scaffolded) with source/source.md written. Returns (ws, source_md)."""
        doc = load_source(src)
        slug = slug or slugify(doc.title)
        out = (Path(self.cfg.out_dir) if self.cfg.out_dir else (REPO / "projects" / "_published")).resolve()
        ws = (out / slug).resolve()
        if ws.exists():
            raise FileExistsError(f"workspace already exists: {ws} (pick a slug or remove it)")
        toolkit.scaffold(ws, self.cfg.theme, cover=self.cfg.cover)
        src_md = ws / "source" / "source.md"
        header = f"# {doc.title}\n\n" if not doc.markdown.lstrip().startswith("#") else ""
        meta = f"> Source: {doc.url}\n\n" if doc.url else ""
        src_md.write_text(meta + header + doc.markdown, encoding="utf-8")
        if doc.notes:
            (ws / "source" / "extraction-notes.md").write_text("\n".join("- " + n for n in doc.notes), encoding="utf-8")
        if self.cfg.embed_fonts and self.cfg.theme in THEME_FONTS:
            toolkit.embed_fonts(ws, THEME_FONTS[self.cfg.theme])
        if self.cfg.brand_color:
            toolkit.brand_recolor(ws, self.cfg.theme, self.cfg.brand_color, self.cfg.brand_mode)
        return ws, src_md

    def finalize(self, ws: Path) -> Path:
        toolkit.build(ws)
        return toolkit.deliver(ws)

    # ---- agent authoring ----
    def _author_prompt(self) -> str:
        tpl = handoff("publish.author-article")
        from nolan.orchestrator.claude_runner import path_for_agent

        return (
            tpl.replace("{skill}", path_for_agent(SKILL))
            .replace("{theme}", self.cfg.theme)
            .replace("{type}", self.cfg.type)
            .replace("{retention}", self.cfg.retention)
            .replace("{width}", self.cfg.width)
            .replace("{images}", self.cfg.images)
        )

    async def author(self, ws: Path):
        from nolan.orchestrator.claude_runner import run_one_shot, path_for_agent

        user = (
            f"# workspace\n{path_for_agent(ws)}\n\n"
            f"Author the complete article here from source/source.md, then build it. "
            f"Theme={self.cfg.theme}, type={self.cfg.type}, retention={self.cfg.retention}."
        )
        log = ws / ".orchestrator" / "author.stream.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        result = await run_one_shot(
            system_prompt=self._author_prompt(),
            user_prompt=user,
            cwd=ws,
            permission_mode="bypassPermissions",
            timeout_seconds=self.cfg.agent_timeout,
            stream_log_path=log,
        )
        return result

    # ---- full pipeline ----
    async def run(self, src: str, slug: str | None = None) -> PublishResult:
        ws, _ = self.prepare(src, slug)
        res = PublishResult(workspace=ws, plan_path=ws / "plan" / "plan.md")
        if self.cfg.mode == "review":
            res.stopped_for_review = True
            res.summary = f"Scaffolded {ws.name} ({self.cfg.theme}); ready for authoring/review."
            return res
        await self.author(ws)
        # validate the agent actually authored sections, then build
        sections = list((ws / "article" / "sections").glob("*.tsx"))
        if not sections:
            res.notes.append("agent wrote no sections")
            return res
        res.article_html = self.finalize(ws)
        res.ok = res.article_html.exists() and toolkit.is_offline(res.article_html)
        res.summary = f"{ws.name}: {len(sections)} sections, {res.article_html.stat().st_size // 1024} KB, offline={res.ok}"
        return res
