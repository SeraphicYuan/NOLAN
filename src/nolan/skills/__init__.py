"""Skill registry — the catalog + linter for NOLAN's agent-facing skills.

NOLAN is a HYBRID pipeline: a deterministic engine that hands off to an agent at
judgment points (plan, author, invent, edit). A *skill* is the markdown doc the agent
reads at such a handoff. Prose can't be type-checked or unit-tested, so skills rot
silently. This module gives them the two things code already has and prose lacked:

  - a verifiable BINDING  — manifest frontmatter (`loaded_by`, `handoffs`, `documents`)
    plus `lint_skills()` that FAILS when the binding drifts (a load-site that no longer
    references the skill, a grammar doc that fell out of sync with the code it documents).
  - an IDENTITY + lineage — a stable `id`, `kind`, `uses`/`overrides` edges the rest of
    the system (and a future /skills UI) can query from a generated `skills/index.json`.

Skills live in two roots:
  - `skills/`         relocated pipeline/agent docs, consolidated here (this is the home).
  - `.claude/skills/` harness-invoked Claude Code skills — the runtime owns that path, so
                      they are cataloged IN PLACE, never moved (moving breaks invocation).

A skill = any `.md` whose YAML frontmatter carries an `id`. Untagged `.md` are ignored,
so migration is incremental and a half-migrated tree still lints clean.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]   # src/nolan/skills/__init__.py -> repo root
SKILL_ROOTS = [ROOT / "skills", ROOT / ".claude" / "skills"]
INDEX_PATH = ROOT / "skills" / "index.json"
INVOCATION_LOG = ROOT / ".nolan" / "skills" / "invocations.jsonl"   # runtime telemetry (gitignored)
FEEDBACK_LOG = ROOT / ".nolan" / "skills" / "feedback.jsonl"        # human gate corrections (gitignored)
SCHEMA_VERSION = 1

KINDS = {"contract", "craft", "grammar", "prompt", "methodology"}
# tier orders the router: primary = the dominant pipeline, then organ, then legacy.
TIERS = {"primary", "organ", "craft", "legacy"}
_ROUTER_BEGIN = "<!-- BEGIN AUTOGEN:skill-router (python -m nolan.skills --emit-router) -->"
_ROUTER_END = "<!-- END AUTOGEN:skill-router -->"
_ROUTER_FILE = ROOT / ".claude" / "skills" / "nolan" / "SKILL.md"
# manifest fields carried onto Skill (besides id); value = default
_FIELDS = {"name": "", "kind": "", "purpose": "", "status": "active", "version": 1,
           "tier": "", "description": "",
           "handoffs": list, "uses": list, "overrides": list, "loaded_by": list,
           "documents": None, "evals": list}

_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)


@dataclass
class Skill:
    id: str
    name: str = ""
    kind: str = ""
    purpose: str = ""
    status: str = "active"
    version: object = 1
    tier: str = ""                                  # router bucket: primary|organ|craft|legacy
    description: str = ""                            # harness routing text (Claude Code SKILL.md)
    handoffs: list = field(default_factory=list)   # [{process, stage, gate?}]
    uses: list = field(default_factory=list)       # skill ids this composes with
    overrides: list = field(default_factory=list)  # skill ids this supersedes
    loaded_by: list = field(default_factory=list)  # code paths that inject/cite it
    documents: object = None                        # grammar↔code sync target(s)
    evals: list = field(default_factory=list)       # eval ids that exercise it
    path: str = ""                                  # repo-relative .md path
    body: str = ""                                  # markdown after frontmatter

    def meta(self) -> dict:
        d = asdict(self)
        d.pop("body", None)
        return d


def _parse(text: str):
    """(frontmatter dict or None, body)."""
    m = _FM.match(text)
    if not m:
        return None, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None, text
    return (fm if isinstance(fm, dict) else None), m.group(2)


def load_skills(roots=None) -> list[Skill]:
    """Every `.md` under the skill roots whose frontmatter has an `id`."""
    out: list[Skill] = []
    seen_real: set[str] = set()   # dedup: one file symlinked into >1 root counts once (home wins)
    for root in (roots or SKILL_ROOTS):
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.md")):
            try:
                real = str(p.resolve())
            except OSError:
                continue                # broken symlink — skip, don't crash the catalog
            if real in seen_real:
                continue                # already cataloged at its home root
            try:
                fm, body = _parse(p.read_text(encoding="utf-8"))
            except OSError:
                continue
            if not fm or "id" not in fm:
                continue
            seen_real.add(real)
            kw = {k: fm.get(k, (d() if callable(d) else d)) for k, d in _FIELDS.items()}
            out.append(Skill(id=str(fm["id"]), body=body,
                             path=str(p.relative_to(ROOT)).replace("\\", "/"), **kw))
    return out


def get_skill(skill_id: str, skills=None) -> Skill | None:
    return next((s for s in (skills or load_skills()) if s.id == skill_id), None)


def skill_path(skill_id: str) -> str | None:
    """Repo-relative path of a skill — for CITE-style load-sites (an agent told to *read* the
    file) as opposed to handoff()'s INJECT (the body spliced into a prompt)."""
    s = get_skill(skill_id)
    return s.path if s else None


def _log_invocation(skill_id: str, version, ctx) -> None:
    """Append one handoff to the invocation log — makes lineage observable and is the substrate
    the Phase 3 feedback ledger ties human corrections back to (which skill version produced what)."""
    try:
        INVOCATION_LOG.parent.mkdir(parents=True, exist_ok=True)
        rec = {"skill": skill_id, "version": version, "at": time.time()}
        if ctx:
            rec["ctx"] = ctx
        with INVOCATION_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass   # telemetry must never break a render


def handoff(skill_id: str, ctx: dict | None = None, *, log: bool = True) -> str:
    """The deterministic→judgment seam. Resolve a skill and return its BODY (frontmatter stripped)
    for injection into an agent/LLM prompt, recording the invocation. Replaces scattered
    `(PROMPTS_DIR / "x.md").read_text()` load-sites so the binding is one call the linter tracks."""
    s = get_skill(skill_id)
    if s is None:
        raise KeyError(f"handoff: unknown skill '{skill_id}' (run `python -m nolan.skills` to list)")
    if log:
        _log_invocation(skill_id, s.version, ctx)
    return s.body.lstrip("\n")


# ─────────────────────────── feedback ledger (Phase 3) ───────────────────────────
# A skill is prose; the only "test" of a craft skill is whether its output gets corrected at a
# HITL gate. Logging every correction AGAINST THE SKILL VERSION that produced the artifact turns
# the gates NOLAN already has into a revision signal: corrections accumulate per (skill, version)
# and become the changelog for the next revision. Bumping a skill's `version` retires its open
# feedback (those corrections were about the prior version).
def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def record_feedback(skill_id: str, note: str, *, ctx: dict | None = None) -> dict:
    """Record one human correction against the skill version that produced the artifact."""
    s = get_skill(skill_id)
    rec = {"skill": skill_id, "version": (s.version if s else None),
           "note": (note or "").strip(), "at": time.time()}
    if ctx:
        rec["ctx"] = ctx
    try:
        FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with FEEDBACK_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass   # a logging failure must never break an edit
    return rec


def skill_feedback(skill_id: str) -> list[dict]:
    return [r for r in _read_jsonl(FEEDBACK_LOG) if r.get("skill") == skill_id]


def skill_health(skill_id: str) -> dict:
    """Per-skill signal: invocations + feedback (total, and 'open' = recorded against the CURRENT
    version, i.e. not yet addressed by a revision). High open-feedback = a revision candidate."""
    s = get_skill(skill_id)
    cur = s.version if s else None
    inv = [r for r in _read_jsonl(INVOCATION_LOG) if r.get("skill") == skill_id]
    fb = skill_feedback(skill_id)
    open_fb = [r for r in fb if r.get("version") == cur]
    return {"skill": skill_id, "version": cur, "status": (s.status if s else None),
            "invocations": len(inv), "feedback_total": len(fb), "feedback_open": len(open_fb),
            "last_feedback_at": max((r.get("at", 0) for r in fb), default=None)}


def health_report() -> list[dict]:
    """Every skill with any feedback, worst (most open corrections) first — the revision queue."""
    rows = [skill_health(s.id) for s in load_skills()]
    rows = [r for r in rows if r["feedback_total"]]
    return sorted(rows, key=lambda r: (-r["feedback_open"], -r["feedback_total"]))


# ─────────────────────────────── UI data (the /skills page) ───────────────────────────────
def ui_index() -> list[dict]:
    """List rows for the /skills page: meta + domain + a compact health summary, grouped-sortable."""
    skills = load_skills()
    inv = _read_jsonl(INVOCATION_LOG)
    fb = _read_jsonl(FEEDBACK_LOG)
    inv_n, fb_open, fb_tot = {}, {}, {}
    cur = {s.id: s.version for s in skills}
    for r in inv:
        inv_n[r.get("skill")] = inv_n.get(r.get("skill"), 0) + 1
    for r in fb:
        k = r.get("skill")
        fb_tot[k] = fb_tot.get(k, 0) + 1
        if r.get("version") == cur.get(k):
            fb_open[k] = fb_open.get(k, 0) + 1
    rows = []
    for s in skills:
        rows.append({**s.meta(), "domain": s.id.split(".")[0],
                     "n_uses": len(s.uses), "n_loaded_by": len(s.loaded_by),
                     "health": {"invocations": inv_n.get(s.id, 0),
                                "feedback_open": fb_open.get(s.id, 0),
                                "feedback_total": fb_tot.get(s.id, 0)}})
    return sorted(rows, key=lambda r: (r["domain"], r["id"]))


def ui_detail(skill_id: str) -> dict | None:
    """Full detail for one skill: meta + body + forward AND reverse lineage + health + feedback."""
    skills = load_skills()
    s = get_skill(skill_id, skills)
    if s is None:
        return None
    used_by = [x.id for x in skills if skill_id in x.uses]
    overridden_by = [x.id for x in skills if skill_id in x.overrides]
    fb = sorted(skill_feedback(skill_id), key=lambda r: r.get("at", 0), reverse=True)[:25]
    return {**s.meta(), "body": s.body, "last_amended": _last_amended(s.path),
            "lineage": {"uses": s.uses, "used_by": used_by, "overrides": s.overrides,
                        "overridden_by": overridden_by, "loaded_by": s.loaded_by,
                        "handoffs": s.handoffs},
            "health": skill_health(skill_id), "feedback": fb}


def ui_graph() -> dict:
    """Lineage graph: nodes (by domain/kind) + uses/overrides edges, for the overview view."""
    skills = load_skills()
    ids = {s.id for s in skills}
    nodes = [{"id": s.id, "kind": s.kind, "domain": s.id.split(".")[0], "status": s.status}
             for s in skills]
    edges = []
    for s in skills:
        for u in s.uses:
            if u in ids:
                edges.append({"from": s.id, "to": u, "type": "uses"})
        for o in s.overrides:
            if o in ids:
                edges.append({"from": s.id, "to": o, "type": "overrides"})
    return {"nodes": nodes, "edges": edges}


def _tier_of(tier: str, skill_id: str) -> str:
    """Resolve a skill's router tier: explicit `tier:` wins, else infer from domain."""
    if tier in TIERS:
        return tier
    dom = skill_id.split(".")[0]
    if dom in ("explainer", "art", "flow", "orchestrator"):
        return "legacy"
    if dom == "common":
        return "craft"
    if dom == "pipeline":
        return "primary"
    return ""


def _last_amended(rel_path: str):
    """ISO timestamp a skill was last edited. Filesystem mtime (follows the symlink to the
    real home file) — instant, and reflects UNCOMMITTED edits (git log is ~1s/file on drvfs)."""
    import datetime
    try:
        ts = (ROOT / rel_path).stat().st_mtime   # stat follows symlinks -> real file
        return datetime.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
    except OSError:
        return None


def ui_tree() -> dict:
    """Hierarchy + per-skill stats for the /map Skills tab: tier → domain → skills, each with
    kind/version/last-amended/binding status, plus coverage stats. Bodies load on click via
    ui_detail(). One place, honesty-fed by the same catalog the linter reads."""
    rows = ui_index()
    for r in rows:
        r["tier"] = _tier_of(r.get("tier") or "", r["id"])
        r["last_amended"] = _last_amended(r["path"])
        # "bound" = has a real code binding (injected by code OR documents a registry/module)
        r["bound"] = bool(r.get("loaded_by")) or bool(r.get("documents"))
    tier_labels = {"primary": "Primary pipeline", "organ": "Organs", "craft": "Craft (umbrellas)",
                   "legacy": "Legacy flows", "": "Other"}
    order = ["primary", "organ", "craft", "legacy", ""]
    tiers = []
    for tkey in order:
        trows = [r for r in rows if r["tier"] == tkey]
        if not trows:
            continue
        domains = {}
        for r in sorted(trows, key=lambda r: r["id"]):
            domains.setdefault(r["domain"], []).append(r)
        tiers.append({"tier": tkey, "label": tier_labels.get(tkey, tkey), "count": len(trows),
                      "domains": [{"domain": d, "skills": s} for d, s in sorted(domains.items())]})
    per_tier = {t["tier"]: t["count"] for t in tiers}
    unbound = [r["id"] for r in rows if not r["bound"] and r["tier"] in ("primary", "organ")]
    return {"count": len(rows), "tiers": tiers,
            "stats": {"total": len(rows), "per_tier": per_tier, "unbound": unbound}}


def build_index(write: bool = True) -> dict:
    """Generate the catalog the UI/linter read. Deterministic (no timestamp) so the
    checked-in artifact only changes when a skill changes."""
    skills = load_skills()
    idx = {"schema_version": SCHEMA_VERSION, "count": len(skills),
           "skills": [s.meta() for s in sorted(skills, key=lambda s: s.id)]}
    if write:
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        INDEX_PATH.write_text(json.dumps(idx, indent=2) + "\n", encoding="utf-8")
    return idx


# ─────────────────────────────────── linter ───────────────────────────────────
# An issue = (severity, code, skill_id, detail). 'error' fails CI; 'warn' is advisory.
def _block_names_in_library() -> set[str]:
    lib = ROOT / "render-service" / "remotion-lib" / "src" / "blocks" / "library"
    if not lib.exists():
        return set()
    return {p.stem for p in lib.glob("*.tsx") if p.stem[:1].isupper()}


def _flow_palette(flow_id: str) -> list[str]:
    reg = ROOT / "web-video-lab" / "flows" / "registry.json"
    if not reg.exists():
        return []
    t = next((t for t in json.loads(reg.read_text(encoding="utf-8")).get("types", [])
              if t["id"] == flow_id), None)
    return (t or {}).get("palette", [])


def _lint_documents(s: Skill) -> list[tuple]:
    """Grammar↔code staleness. The `documents` field names what the doc must stay in sync
    with — a precise invariant, not a vibe:
      - `palette: <flow>`  → the catalog must document every block in that flow's palette
        (registry.json). This is scoped, so art-only blocks don't false-positive on the
        explainer catalog.
      - `blocks: <path>`   → a master catalog must mention every block the library ships.
    A block is "documented" if the doc body mentions it AND the library actually has it
    (so the catalog can't drift by inventing blocks either)."""
    issues = []
    docs = s.documents or {}
    if not isinstance(docs, dict):
        return issues
    # generic code binding: `dag`/`module` name the source file the skill documents.
    # A dangling target is a broken binding — an error, not a vibe. (Heading/step
    # COVERAGE for these is enforced per-skill in tests/test_organ_skills.py.)
    for key in ("dag", "module"):
        if key in docs and not (ROOT / docs[key]).exists():
            issues.append(("error", "documents-missing", s.id, f"documents.{key} -> {docs[key]} (no such file)"))
    library = _block_names_in_library()
    mentioned = set(re.findall(r"\b[A-Z][A-Za-z0-9]+\b", s.body))
    if "palette" in docs:
        flow_id = docs["palette"]
        for b in sorted(_flow_palette(flow_id)):
            if b not in mentioned:
                issues.append(("warn", "grammar-stale", s.id, f"{flow_id} palette block not documented: {b}"))
            elif library and b not in library:
                issues.append(("warn", "grammar-ghost", s.id, f"{flow_id} palette block missing from library: {b}"))
    if "blocks" in docs:
        for missing in sorted(library - mentioned):
            issues.append(("warn", "grammar-stale", s.id, f"library block not in catalog: {missing}"))
    return issues


def _lint_malformed(roots=None) -> list[tuple]:
    """A `.md` under the home root (`skills/`) that opens with a `---` frontmatter fence but
    yields no usable `id` is almost always a botched manifest — a bad YAML value silently drops
    it from the catalog, then it resurfaces only as a confusing dangling reference elsewhere.
    Surface it directly. (`.claude/skills/` is exempt — plain SKILL.md there needn't be tagged.)"""
    issues = []
    home = ROOT / "skills"
    for p in sorted(home.rglob("*.md")):
        # Vendored harness skills (Claude Code SKILL.md / HF FRAME presets) are symlinked INTO
        # skills/ but live under .agents/skills or .claude/skills — they are cataloged in place
        # and legitimately carry no `id:`. Exempt anything that resolves outside skills/.
        try:
            real = p.resolve()
            if not str(real).replace("\\", "/").startswith(str(home.resolve()).replace("\\", "/")):
                continue
        except OSError:
            continue
        head = p.read_text(encoding="utf-8")[:3]
        if head != "---":
            continue
        fm, _ = _parse(p.read_text(encoding="utf-8"))
        if fm and "id" in fm:
            continue
        # A Claude-Code SKILL.md (has `name:`+`description:`) is a valid harness skill, not a
        # NOLAN registry manifest — exempt (same rule as `.claude/skills`). Only a fenced doc
        # that is NEITHER a registry skill NOR a harness skill is a botched manifest.
        if fm and fm.get("name") and fm.get("description"):
            continue
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        issues.append(("error", "malformed-manifest", rel,
                       "has a --- frontmatter fence but no valid id (YAML parse failed?)"))
    return issues


def lint_skills() -> list[tuple]:
    skills = load_skills()
    issues: list[tuple] = _lint_malformed()
    seen: dict[str, str] = {}
    for s in skills:
        if s.id in seen:
            issues.append(("error", "dup-id", s.id, f"also at {seen[s.id]}"))
        seen[s.id] = s.path
        if s.kind not in KINDS:
            issues.append(("error", "bad-kind", s.id, f"{s.kind!r} not in {sorted(KINDS)}"))
        if not s.purpose:
            issues.append(("warn", "no-purpose", s.id, "missing one-line purpose"))
    ids = set(seen)
    for s in skills:
        for u in s.uses:
            if u not in ids:
                issues.append(("error", "dangling-uses", s.id, u))
        for o in s.overrides:
            if o not in ids:
                issues.append(("error", "dangling-override", s.id, o))
        for lb in s.loaded_by:
            p = ROOT / lb
            if not p.exists():
                issues.append(("error", "missing-loaded-by", s.id, lb))
                continue
            txt = p.read_text(encoding="utf-8", errors="ignore")
            stem = Path(s.path).stem
            if s.id not in txt and Path(s.path).name not in txt and stem not in txt:
                issues.append(("warn", "dead-binding", s.id,
                               f"{lb} no longer references this skill (id/filename)"))
        issues += _lint_documents(s)
    return issues


# ─────────────────────────── router (auto-generated) ───────────────────────────
# The `nolan` orientation skill's registry table is GENERATED from the catalog, not
# hand-maintained — a hand-kept table is a rot vector (the whole point of this system).
# `--emit-router` rewrites the marked region; a freshness test (test_organ_skills.py)
# fails CI if the checked-in region drifts from what the catalog would emit.
_TIER_ORDER = ["primary", "organ", "craft", "legacy", ""]
_TIER_LABEL = {"primary": "Primary pipeline (start here)", "organ": "Organs",
               "craft": "Craft (umbrella judgment)", "legacy": "Legacy flows", "": "Other"}


def _skill_tier(s: Skill) -> str:
    return _tier_of(s.tier, s.id)


def render_router() -> str:
    """The auto-generated skill-registry region for the `nolan` router skill."""
    skills = load_skills()
    by_tier: dict[str, list[Skill]] = {}
    for s in skills:
        by_tier.setdefault(_skill_tier(s), []).append(s)
    lines = [_ROUTER_BEGIN,
             "## Skill registry — auto-generated, do not edit by hand",
             "",
             f"_{len(skills)} skills. Regenerate: `python -m nolan.skills --emit-router`. "
             "Load the skill for the subsystem you are ABOUT to touch — not preemptively._",
             ""]
    for tier in _TIER_ORDER:
        group = sorted(by_tier.get(tier, []), key=lambda s: s.id)
        if not group:
            continue
        lines.append(f"### {_TIER_LABEL.get(tier, tier)}")
        lines.append("")
        lines.append("| skill | kind | what it's for |")
        lines.append("|---|---|---|")
        for s in group:
            purpose = " ".join((s.purpose or s.description or "").split())
            if len(purpose) > 140:
                purpose = purpose[:137] + "…"
            lines.append(f"| `{s.id}` | {s.kind} | {purpose} |")
        lines.append("")
    lines.append(_ROUTER_END)
    return "\n".join(lines)


def emit_router(write: bool = True) -> str:
    """Replace the marked region in the `nolan` SKILL.md with a freshly rendered router.
    Returns the full new file text. Idempotent."""
    region = render_router()
    text = _ROUTER_FILE.read_text(encoding="utf-8")
    if _ROUTER_BEGIN in text and _ROUTER_END in text:
        pre = text.split(_ROUTER_BEGIN)[0]
        post = text.split(_ROUTER_END, 1)[1]
        new = pre + region + post
    else:
        # first run: append the region at the end (author moves it where it belongs once).
        new = text.rstrip() + "\n\n" + region + "\n"
    if write and new != text:
        _ROUTER_FILE.write_text(new, encoding="utf-8")
    return new


def router_is_fresh() -> bool:
    """True iff the checked-in router region matches what the catalog would emit."""
    if not _ROUTER_FILE.exists():
        return True
    return emit_router(write=False) == _ROUTER_FILE.read_text(encoding="utf-8")


def _cli() -> int:
    import sys
    if "--emit-router" in sys.argv:
        emit_router(write=True)
        print(f"router: regenerated {_ROUTER_FILE.relative_to(ROOT)}")
    idx = build_index(write=True)
    issues = lint_skills()
    errs = [i for i in issues if i[0] == "error"]
    warns = [i for i in issues if i[0] == "warn"]
    print(f"skills: {idx['count']} cataloged -> {INDEX_PATH.relative_to(ROOT)}")
    for sev, code, sid, detail in errs + warns:
        mark = "ERROR" if sev == "error" else "warn "
        print(f"  [{mark}] {code:18} {sid:28} {detail}")
    print(f"lint: {len(errs)} error(s), {len(warns)} warning(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(_cli())
