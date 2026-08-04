"""Two ways to run the same brief: a Claude agent on the fleet, or a direct API call.

The point of the pair is a controlled comparison. The loop, the briefs, the verdict schema, the
parser and the routing are all identical; the ONLY variable is who does the thinking. Anything
else that differs between the two runs is a confound, and Phase 2 already lost time to one of
those (an attended/unattended contract change mistaken for judge variance).

The two are not equivalent in kind, and that is the finding under test:

  **FleetExecutor** dispatches to an ephemeral Claude session. It is agentic — it opens files
  itself, can re-read a passage, can spend as long as it likes, and decides for itself how much
  of the style guide to consult. Costs a whole session per call.

  **ApiExecutor** is one request. The model cannot open anything, so every byte it is allowed to
  see must be inlined up front (hence `context.inline_bundle`), and it gets exactly one pass with
  no opportunity to go back and check. Costs one completion.

NOLAN's routing policy says taste belongs to agents and cheap structured judgement belongs to API
calls. A pairwise script verdict sits exactly on that line, which is what makes it worth measuring
rather than assuming.
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent))

import context as ctx                                              # noqa: E402
import fleet_kinds as fk                                           # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


@dataclass
class RunResult:
    ok: bool
    seconds: float
    detail: str = ""
    notes: List[str] = field(default_factory=list)


def _extract_json(text: str) -> Optional[dict]:
    """Pull the JSON object out of a model reply.

    Models wrap JSON in prose or fences however they feel that day, so this is deliberately
    forgiving — but it never GUESSES. If nothing parses, the caller gets None and reports a
    failure, rather than a half-parsed object that would silently become a verdict.
    """
    for candidate in (text,
                      *(m.group(1) for m in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.S))):
        s = candidate.strip()
        if not s:
            continue
        try:
            v = json.loads(s)
            if isinstance(v, dict):
                return v
        except json.JSONDecodeError:
            pass
    # Last resort: the outermost brace pair.
    i, j = text.find("{"), text.rfind("}")
    if i >= 0 and j > i:
        try:
            v = json.loads(text[i:j + 1])
            return v if isinstance(v, dict) else None
        except json.JSONDecodeError:
            return None
    return None


class FleetExecutor:
    """An ephemeral Claude agent reads the brief's paths and writes the artifact itself."""

    name = "fleet"

    def __init__(self, timeout_s: float = 900):
        self.timeout_s = timeout_s

    def run(self, *, brief: str, want: Path, slug: str, store, label: str,
            expect: str = "json") -> RunResult:
        # `expect` is ignored: an agent writes whatever file the brief told it to write, so the
        # output shape is the brief's business rather than the executor's.
        t0 = time.time()
        res = fk.reserve(fk.SCRIPT_LOOP, meta={"slug": slug, "phase": label})
        if not res:
            return RunResult(False, 0.0, f"no agent available (ceiling "
                                         f"{fk.SCRIPT_LOOP.max_concurrent})")
        try:
            fk.await_ready(res)
            pf = HERE / f"_brief_{slug}_{label}.md"
            pf.write_text(brief, encoding="utf-8")
            rel = (HERE / "_runs").relative_to(REPO).as_posix()
            fk.dispatch(res, f"Read {_wsl(pf)} and do exactly what it says. "
                             f"Work only under {rel}/ — never touch projects/.")
            deadline = time.time() + self.timeout_s
            while time.time() < deadline:
                if want.exists() and want.stat().st_size > 2:
                    return RunResult(True, time.time() - t0, str(want.name))
                time.sleep(5)
            pane = (fk._f.capture_pane(res.session, 12) or "").strip().splitlines()[-6:]
            return RunResult(False, time.time() - t0,
                             f"timed out after {self.timeout_s:.0f}s; pane: " + " | ".join(pane))
        except fk.NotReady as e:
            return RunResult(False, time.time() - t0, str(e))
        finally:
            fk.release(res)


class ApiExecutor:
    """One completion. Everything the model may see is inlined; there is no second look."""

    name = "api"

    def __init__(self, model: Optional[str] = None, provider: Optional[str] = None,
                 reasoning: Optional[bool] = None):
        from nolan.config import load_config
        from nolan.llm import create_text_llm
        cfg = load_config()
        self.llm = create_text_llm(cfg, provider=provider, model=model, reasoning=reasoning)
        self.model = model or (cfg.gemini.model if (provider or cfg.llm.provider) == "gemini"
                               else cfg.llm.model)

    def run(self, *, brief: str, want: Path, slug: str, store, label: str,
            expect: str = "json") -> RunResult:
        import asyncio
        t0 = time.time()
        bundle, notes = ctx.inline_bundle(slug, store)
        if expect == "text":
            return self._text(brief, bundle, notes, want, t0)
        # The brief tells an AGENT to open paths and to write a file. Neither is available here,
        # so the instruction is restated: the context is already below, and the answer IS the reply.
        prompt = (
            f"{brief}\n\n"
            f"{'=' * 78}\n"
            f"# IMPORTANT — how this run differs\n"
            f"You are being called as a single API request, not as an agent with tools.\n"
            f"- You CANNOT open files. Every file the brief refers to is inlined below verbatim.\n"
            f"- You CANNOT write files. Do not describe writing one.\n"
            f"- Reply with the JSON object the brief specifies and NOTHING else — no preamble,\n"
            f"  no commentary, no code fence. Your entire reply must parse as that JSON.\n"
            f"{'=' * 78}\n"
            f"# THE FULL CONTEXT (inlined)\n{bundle}\n")
        try:
            reply = asyncio.run(self.llm.generate(prompt))
        except Exception as e:                                    # noqa: BLE001 — report, never mask
            return RunResult(False, time.time() - t0, f"{type(e).__name__}: {e}"[:200], notes)
        obj = _extract_json(reply)
        if obj is None:
            return RunResult(False, time.time() - t0,
                             f"reply did not contain JSON ({len(reply)} ch): {reply[:160]!r}",
                             notes)
        want.parent.mkdir(parents=True, exist_ok=True)
        want.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        notes.append(f"prompt: {len(prompt):,} ch (~{len(prompt) // 4:,} tok)")
        notes.append(f"reply: {len(reply):,} ch")
        return RunResult(True, time.time() - t0, str(want.name), notes)

    def _text(self, brief: str, bundle: str, notes: List[str], want: Path,
              t0: float) -> RunResult:
        """The revise pass returns a DRAFT, not a verdict — markdown, written verbatim."""
        import asyncio
        prompt = (
            f"{brief}\n\n"
            f"{'=' * 78}\n"
            f"# IMPORTANT — how this run differs\n"
            f"You are a single API request, not an agent with tools. You CANNOT open or write\n"
            f"files; everything is inlined below. Reply with the COMPLETE revised draft in\n"
            f"markdown and nothing else — no preamble, no commentary, no fence around it. Your\n"
            f"entire reply is written to the draft file verbatim.\n"
            f"{'=' * 78}\n"
            f"# THE FULL CONTEXT (inlined)\n{bundle}\n")
        try:
            reply = asyncio.run(self.llm.generate(prompt))
        except Exception as e:                                    # noqa: BLE001
            return RunResult(False, time.time() - t0, f"{type(e).__name__}: {e}"[:200], notes)
        body = reply.strip()
        if body.startswith("```"):                     # strip a fence it was asked not to add
            body = re.sub(r"^```[a-z]*\s*|\s*```$", "", body, flags=re.S).strip()
        if len(body) < 200:
            return RunResult(False, time.time() - t0,
                             f"reply too short to be a draft ({len(body)} ch): {body[:120]!r}",
                             notes)
        want.parent.mkdir(parents=True, exist_ok=True)
        want.write_text(body + "\n", encoding="utf-8")
        notes.append(f"prompt: {len(prompt):,} ch (~{len(prompt) // 4:,} tok)")
        notes.append(f"draft written: {len(body):,} ch")
        return RunResult(True, time.time() - t0, str(want.name), notes)


def _wsl(p: Path) -> str:
    s = str(p).replace("\\", "/")
    return f"/mnt/{s[0].lower()}{s[2:]}" if len(s) > 2 and s[1] == ":" else s
