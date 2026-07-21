"""Script gate — the deterministic quality door for a drafted/revised script.

The script umbrella's answer to NOLAN's propose→gate→accept contract (CLAUDE.md:
"an agent's output is a PROPOSAL artifact that passes a deterministic gate before
becoming canonical"). Every other umbrella has one — asset_gate, layout_lint,
render_gate — the script side did not. This is it.

It runs automatically after any ``draft`` / ``revise`` phase and can be run by hand
(``nolan scriptgen gate <slug>``). It **measures and reports loudly; it never silently
fixes or enforces** — a producer can still promote a draft over a warning (human
override, per the invariant "failures are loud, no silent caps"), but the flag is
visible.

Every check is named in :data:`SCRIPT_GATE_CHECKS`; ``tests/test_script_review.py``
pins that ``gate_text`` returns exactly those checks (docs claim, tests enforce).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Every door this gate opens. The honesty test asserts a run reports each of these.
SCRIPT_GATE_CHECKS = ("format", "word-count", "beat-grounding", "needs-check", "beat-continuity")

_PASS, _WARN, _FAIL = "pass", "warn", "fail"
_MARKS = {_PASS: "✓", _WARN: "▲", _FAIL: "✗"}


@dataclass
class GateCheck:
    id: str
    level: str          # pass | warn | fail
    message: str


@dataclass
class GateReport:
    checks: List[GateCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """No hard failures. Warnings do not block (human override)."""
        return all(c.level != _FAIL for c in self.checks)

    @property
    def failures(self) -> List[GateCheck]:
        return [c for c in self.checks if c.level == _FAIL]

    @property
    def warnings(self) -> List[GateCheck]:
        return [c for c in self.checks if c.level == _WARN]

    def summary(self) -> str:
        head = "GATE OK" if self.ok else "GATE FAILED"
        lines = [f"{head} — {len(self.failures)} fail, {len(self.warnings)} warn"]
        for c in self.checks:
            lines.append(f"  {_MARKS.get(c.level, '?')} [{c.id}] {c.message}")
        return "\n".join(lines)


def gate_text(draft_text: str, *, facts_md: str = "", beatmap_md: str = "",
              factcheck_md: str = "", target_words: int = 0,
              prev_draft_text: Optional[str] = None) -> GateReport:
    """Pure, testable gate over the raw text of a draft. Returns one check per door."""
    from nolan.script_context import _parse_script_beats, _attach_facts, _attach_beatmap

    beats = _parse_script_beats(draft_text or "")
    checks: List[GateCheck] = []

    # --- format ------------------------------------------------------------
    fmt_problems = []
    if "# Video Script" not in (draft_text or ""):
        fmt_problems.append("missing `# Video Script` header")
    if "**Total Duration:**" not in (draft_text or ""):
        fmt_problems.append("missing `**Total Duration:**`")
    if len(beats) < 2:
        fmt_problems.append(f"only {len(beats)} `## ` beat heading(s) (need ≥2)")
    if fmt_problems and (len(beats) < 2 or "# Video Script" not in (draft_text or "")):
        checks.append(GateCheck("format", _FAIL, "; ".join(fmt_problems)))
    elif fmt_problems:
        checks.append(GateCheck("format", _WARN, "; ".join(fmt_problems)))
    else:
        checks.append(GateCheck("format", _PASS, f"Director-ready shape, {len(beats)} beats"))

    # --- word-count (measure; never hard-fail — length is a producer call) --
    actual = sum(len(b.narration.split()) for b in beats) or len((draft_text or "").split())
    if target_words > 0:
        ratio = actual / target_words
        mins = actual / 150.0
        msg = (f"{actual} words vs target {target_words} "
               f"({ratio*100:.0f}% · ≈{int(mins)}:{int((mins*60) % 60):02d})")
        checks.append(GateCheck("word-count", _PASS if 0.88 <= ratio <= 1.12 else _WARN, msg))
    else:
        checks.append(GateCheck("word-count", _WARN, f"{actual} words (no target set)"))

    # --- beat-grounding: every beat should trace to ≥1 source --------------
    # The authoritative per-beat source map is the beatmap's `covers:[S#]`; facts.md is
    # a secondary signal and is often grouped by beat-FUNCTION (hook/context/…), not by
    # the script's beat TITLES — so we can't always map it per-beat. Prefer beatmap covers,
    # fall back to a corpus-level facts signal rather than crying "ungrounded" falsely.
    has_facts = bool((facts_md or "").strip())
    has_beatmap = bool((beatmap_md or "").strip())
    if not has_facts and not has_beatmap:
        checks.append(GateCheck("beat-grounding", _WARN,
                                "no facts.md / beatmap.md to check grounding against"))
    else:
        if has_beatmap:
            _attach_beatmap(beats, beatmap_md)   # fills .covers (source ids per beat)
        if has_facts:
            _attach_facts(beats, facts_md)        # fills .facts (only if title-grouped)
        grounded = [b for b in beats if b.covers or b.facts]
        # Only make per-beat claims when the beatmap↔script mapping is CONFIDENT (≥80% of
        # beats matched). Below that the title-matching is too fuzzy to trust — an unmatched
        # beat is far more likely a mapping miss than a real grounding gap — so defer to the
        # corpus signal instead of crying wolf. (Was ≥50%, which false-warned on drafts whose
        # beatmap titles were only partly re-worded from the script's.)
        # threshold = ceil(0.8 * beats) so 10/13 (77%) defers to corpus, 11/13 does not
        if beats and len(grounded) >= max(2, (len(beats) * 4 + 4) // 5):
            ungrounded = [b.title for b in beats if not (b.covers or b.facts)]
            if ungrounded:
                shown = ", ".join(ungrounded[:5]) + ("…" if len(ungrounded) > 5 else "")
                checks.append(GateCheck("beat-grounding", _WARN,
                                        f"{len(ungrounded)}/{len(beats)} beats trace to no "
                                        f"source: {shown}"))
            else:
                checks.append(GateCheck("beat-grounding", _PASS,
                                        f"all {len(beats)} beats trace to a source"))
        else:
            # neither artifact maps per-beat — report the corpus-level grounding signal
            n_src = sum(1 for ln in (facts_md or "").splitlines()
                        if ln.lstrip().startswith("- ") and "[S" in ln)
            if n_src >= len(beats):
                checks.append(GateCheck("beat-grounding", _PASS,
                                        f"facts.md present ({n_src} source-backed facts); "
                                        "not per-beat mappable (function-grouped)"))
            else:
                checks.append(GateCheck("beat-grounding", _WARN,
                                        f"grounding thin: {n_src} source-backed facts for "
                                        f"{len(beats)} beats"))

    # --- needs-check: an unverified tag must never leak into the narration --
    leaked = "[needs-check]" in (draft_text or "")
    n_flags = len(re.findall(r"\[needs-check\]", (factcheck_md or "") + (facts_md or "")))
    if leaked:
        checks.append(GateCheck("needs-check", _FAIL,
                                "a `[needs-check]` tag leaked into the script prose — soften or cut"))
    elif n_flags:
        checks.append(GateCheck("needs-check", _WARN,
                                f"{n_flags} `[needs-check]` claim(s) in grounding — confirm each is "
                                "hedged or cut in the script"))
    else:
        checks.append(GateCheck("needs-check", _PASS, "no unverified-claim leakage"))

    # --- beat-continuity: a revision must not silently drop a beat ----------
    if prev_draft_text is None:
        checks.append(GateCheck("beat-continuity", _PASS, "n/a (no prior draft)"))
    else:
        def _titles(text):
            return {re.sub(r"[^a-z0-9 ]", "", b.title.lower()).strip()
                    for b in _parse_script_beats(text) if b.title.strip()}
        dropped = _titles(prev_draft_text) - _titles(draft_text)
        if dropped:
            checks.append(GateCheck("beat-continuity", _WARN,
                                    f"{len(dropped)} beat(s) present before are gone now: "
                                    + ", ".join(sorted(dropped)[:5])))
        else:
            checks.append(GateCheck("beat-continuity", _PASS, "no beats silently dropped"))

    return GateReport(checks)


def run_gate(slug: str, store=None, draft_name: Optional[str] = None) -> GateReport:
    """Gate a project's current (or named) draft, pulling context from its store."""
    from nolan.scriptwriter.store import ScriptProjectStore

    store = store or ScriptProjectStore(Path("projects"))
    if draft_name:
        draft_text = store.read_draft(slug, draft_name) or ""
        num = _draft_num(draft_name)
    else:
        num, path = store.current_draft(slug)
        draft_text = path.read_text(encoding="utf-8") if path else ""

    prev_text = None
    if num and num > 1:
        prev = store.draft_path(slug, f"draft-{num - 1:02d}.md")
        if prev:
            prev_text = prev.read_text(encoding="utf-8")

    return gate_text(
        draft_text,
        facts_md=store.read_artifact(slug, "facts") or "",
        beatmap_md=store.read_artifact(slug, "beatmap") or "",
        factcheck_md=store.read_artifact(slug, "factcheck") or "",
        target_words=store.target_words(slug),
        prev_draft_text=prev_text,
    )


def _draft_num(name: str) -> int:
    m = re.search(r"(\d+)", Path(name).stem)
    return int(m.group(1)) if m else 0


def verify_revision(store, slug: str, review_n: int) -> dict:
    """Heuristic check that a revise actually TOUCHED the findings it approved — closing the
    propose→gate→accept loop on the revise half (which the agent otherwise self-reports).

    For each approved finding carrying a usable quote, checks whether that exact quote CHANGED
    between draft-N and draft-(N+1). A cut/replace fix should change it; an *add* fix legitimately
    may not — so ``untouched`` is a SIGNAL to double-check, not a verdict. Findings without a
    usable quote are 'unverifiable'.
    """
    import json
    ap = store.review_approved_path(slug, review_n)
    findings = []
    if ap.exists():
        try:
            findings = json.loads(ap.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            findings = []
    prev = store.draft_path(slug, f"draft-{review_n:02d}.md")
    nxt = store.draft_path(slug, f"draft-{review_n + 1:02d}.md")
    prev_t = prev.read_text(encoding="utf-8") if prev else ""
    new_t = nxt.read_text(encoding="utf-8") if nxt else ""
    rows = []
    for f in findings:
        q = (f.get("quote") or "").strip()
        changed = None
        if q and len(q) >= 12:
            changed = bool(q in prev_t and q not in new_t)   # flagged text is gone/changed
        rows.append({"id": f.get("id"), "dim": f.get("dim"),
                     "severity": f.get("severity"), "changed": changed})
    checkable = [r for r in rows if r["changed"] is not None]
    changed = [r for r in checkable if r["changed"]]
    untouched = [r for r in checkable if not r["changed"]]
    return {
        "approved": len(findings),
        "new_draft_exists": bool(new_t),
        "checkable": len(checkable),
        "changed": len(changed),
        "untouched": len(untouched),
        "untouched_ids": [r["id"] for r in untouched],
        "rows": rows,
    }
