"""NOLAN publishing — turn a URL/doc into a self-contained, offline single-file
HTML article (reacticle + the figure library), via an agent-orchestrated workflow.

A second output medium alongside video: source -> plan -> author (figures) ->
build -> deliver. The deterministic render toolchain lives in `toolkit` (run in
WSL); agent authoring is driven through `orchestrator.claude_runner`.

    from nolan.publish import Publisher, PublishConfig
    res = await Publisher(PublishConfig(theme="press")).run("https://example.com/post")
    print(res.article_html)
"""
from __future__ import annotations

from . import source, toolkit  # noqa: F401
from .source import SourceDoc, load_source, slugify  # noqa: F401

__all__ = ["source", "toolkit", "SourceDoc", "load_source", "slugify"]

try:  # builder pulls orchestrator/llm; keep import optional so toolkit works standalone
    from .builder import Publisher, PublishConfig, PublishResult  # noqa: F401

    __all__ += ["Publisher", "PublishConfig", "PublishResult"]
except Exception:  # pragma: no cover
    pass
