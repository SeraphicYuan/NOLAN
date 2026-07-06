"""The taste feedback loop (SOTA #9) — NOLAN compounds instead of resetting.

Every human override is preference data. This module closes the loop:

  LEDGER    profiles/ledger.jsonl — (project, stage, context, pipeline
            proposed, human chose). Test projects are excluded at write time
            (project.yaml `test_project: true`), or learning self-poisons.
  RULES     profiles/taste.json — distilled preferences, scoped to the
            channel or a video type, each with evidence, confidence, status.
  DISTILL   `nolan retro <project>`: an LLM reads the ledger and PROPOSES
            rules; a deterministic gate rejects anything without >=3
            supporting events across >=2 projects (no superstition from one
            bad Tuesday). Proposals wait for human acceptance on /taste.
  APPLY     guidance_for(stage, video_type) — prompt-injectable text every
            authoring agent receives.

ANTI-LOCK-IN (the owner's explicit fear: early work is merely OK, and
hardened OK-rules would cage the system at a local maximum):
  - status tiers change the LANGUAGE agents see: `proposed` is invisible;
    `active` renders as "PREFER — deviate when you see a clearly better
    treatment, and say why"; only `locked` (an explicit human act) renders
    as ALWAYS/NEVER. Nothing the distiller mints can constrain absolutely.
  - a standing EXPERIMENT clause invites one flagged deviation per project;
    accepted experiments become counter-evidence.
  - rules carry provenance + confidence and are RETIRABLE; the distiller is
    instructed to propose retirement when later edits contradict a rule.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]
PROFILES = REPO / "profiles"
RULES_PATH = PROFILES / "taste.json"
LEDGER_PATH = PROFILES / "ledger.jsonl"

STAGES = ("style", "scenes", "slides", "motion", "tempo", "soundtrack",
          "editing", "packaging")
STATUSES = ("proposed", "active", "locked", "retired")
SOURCES = ("owner", "reference")

MIN_EVENTS = 3        # evidence threshold: events supporting a rule
MIN_PROJECTS = 2      # …across at least this many distinct projects


# --- rules store -----------------------------------------------------------------

def validate_rule(r: Dict[str, Any]) -> List[str]:
    problems = []
    if not r.get("id"):
        problems.append("rule needs an id")
    scope = str(r.get("scope", ""))
    if scope != "channel" and not scope.startswith("type:"):
        problems.append(f"scope {scope!r} must be 'channel' or 'type:<video-type>'")
    if r.get("stage") not in STAGES:
        problems.append(f"stage {r.get('stage')!r} not in {STAGES}")
    if not (r.get("rule") or "").strip():
        problems.append("rule text empty")
    if r.get("status") not in STATUSES:
        problems.append(f"status {r.get('status')!r} not in {STATUSES}")
    if r.get("source") not in SOURCES:
        problems.append(f"source {r.get('source')!r} not in {SOURCES}")
    c = r.get("confidence")
    if not isinstance(c, (int, float)) or not 0.0 <= float(c) <= 1.0:
        problems.append("confidence must be 0..1")
    if not isinstance(r.get("evidence"), list):
        problems.append("evidence must be a list")
    return problems


def load_rules() -> List[Dict[str, Any]]:
    if not RULES_PATH.exists():
        return []
    try:
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        rules = data.get("rules", [])
    except Exception as exc:
        logger.warning("taste.json unreadable (%s) — treating as empty", exc)
        return []
    ok = []
    for r in rules:
        problems = validate_rule(r)
        if problems:
            logger.warning("taste rule %s invalid (%s) — skipped",
                           r.get("id"), "; ".join(problems))
            continue
        ok.append(r)
    return ok


def save_rules(rules: List[Dict[str, Any]]) -> Path:
    for r in rules:
        problems = validate_rule(r)
        if problems:
            raise ValueError(f"rule {r.get('id')}: " + "; ".join(problems))
    PROFILES.mkdir(exist_ok=True)
    RULES_PATH.write_text(
        json.dumps({"version": 1, "rules": rules}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    return RULES_PATH


def upsert_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    rule.setdefault("id", f"r-{uuid.uuid4().hex[:8]}")
    rule.setdefault("status", "proposed")
    rule.setdefault("source", "owner")
    rule.setdefault("confidence", 0.5)
    rule.setdefault("evidence", [])
    rule["updated"] = time.strftime("%Y-%m-%d")
    rule.setdefault("created", rule["updated"])
    rules = load_rules()
    rules = [r for r in rules if r["id"] != rule["id"]] + [rule]
    save_rules(rules)
    return rule


def set_rule_status(rule_id: str, status: str) -> Dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"status {status!r} not in {STATUSES}")
    rules = load_rules()
    for r in rules:
        if r["id"] == rule_id:
            r["status"] = status
            r["updated"] = time.strftime("%Y-%m-%d")
            save_rules(rules)
            return r
    raise KeyError(f"no rule {rule_id}")


# --- ledger ----------------------------------------------------------------------

def _is_test_project(project_path: Optional[Path]) -> bool:
    if project_path is None:
        return False
    try:
        import yaml
        meta = yaml.safe_load((Path(project_path) / "project.yaml")
                              .read_text(encoding="utf-8")) or {}
        return meta.get("test_project", False) is True
    except Exception:
        return False


def record_taste_event(*, project: str, stage: str, context: str,
                       proposed: Any, chose: Any,
                       project_path: Optional[Path] = None) -> bool:
    """Append one override to the ledger. Returns False when excluded
    (test project) — learning from scratch projects would self-poison."""
    if _is_test_project(project_path):
        logger.info("taste ledger: %s is a test project — event excluded", project)
        return False
    if stage not in STAGES:
        stage = "scenes"
    PROFILES.mkdir(exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "project": project, "stage": stage, "context": str(context)[:400],
            "proposed": str(proposed)[:400], "chose": str(chose)[:400],
        }, ensure_ascii=False) + "\n")
    return True


def load_ledger() -> List[Dict[str, Any]]:
    if not LEDGER_PATH.exists():
        return []
    out = []
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


# --- apply: guidance for authoring prompts -----------------------------------------

_EXPERIMENT_CLAUSE = (
    "You may flag AT MOST ONE deliberate experiment that deviates from a "
    "PREFER rule when you believe a better treatment exists — mark it "
    "'[EXPERIMENT vs <rule-id>]' with one line of reasoning in your report. "
    "Accepted experiments become evidence that refines the rule.")


def guidance_for(stage: str, video_type: str = "") -> str:
    """Prompt-injectable taste guidance for one authoring stage.

    Locked rules are constraints (ALWAYS/NEVER — a human explicitly locked
    them). Active rules are PRIORS: prefer, but deviate with stated reason
    when something clearly better exists. Proposed/retired rules are
    invisible. Type-specific rules follow channel rules (more specific,
    listed later, presented as refinements)."""
    rules = [r for r in load_rules() if r["stage"] == stage
             and r["status"] in ("active", "locked")]
    channel = [r for r in rules if r["scope"] == "channel"]
    typed = [r for r in rules
             if video_type and r["scope"] == f"type:{video_type}"]
    if not channel and not typed:
        return ""
    lines = ["# Channel taste (learned from the owner's own edits)"]
    for group, label in ((channel, "Channel-wide"),
                         (typed, f"For {video_type} videos")):
        if not group:
            continue
        lines.append(f"## {label}")
        for r in sorted(group, key=lambda x: (x["status"] != "locked",
                                              -float(x["confidence"]))):
            if r["status"] == "locked":
                lines.append(f"- [LOCKED {r['id']}] {r['rule']}")
            else:
                lines.append(f"- [PREFER {r['id']}, confidence "
                             f"{float(r['confidence']):.1f}] {r['rule']} "
                             "(deviate when you see a clearly better "
                             "treatment — say why)")
    lines.append(_EXPERIMENT_CLAUSE)
    return "\n".join(lines)


# --- distill: ledger -> rule proposals ----------------------------------------------

_DISTILL_PROMPT = """You distill an editor's overrides into CANDIDATE taste rules.
Below is the override ledger: each line shows what the pipeline proposed and
what the human chose instead, with stage and context.

Reply STRICT JSON: {{"proposals": [{{
  "scope": "channel" or "type:<video-type>",
  "stage": one of {stages},
  "rule": "<one imperative sentence an authoring agent can follow>",
  "why": "<the pattern you saw>",
  "event_idx": [<indices of the ledger lines supporting this rule>]}}],
  "retirements": [{{"rule_id": "<id>", "why": "<contradicting pattern>"}}]}}

Rules of distillation:
- Only PATTERNS (same kind of override repeated), never one-off fixes.
- Separate CORRECTIONS (the pipeline was wrong/buggy) from PREFERENCES
  (the pipeline was fine, the human likes different) — only preferences
  become rules.
- Check EXISTING RULES below for contradictions with recent events; propose
  retirement when the human now edits against a rule.

EXISTING RULES:
{existing}

LEDGER (idx: stage | context | proposed -> chose):
{ledger}
"""


async def distill(llm, video_type_by_project: Optional[Dict[str, str]] = None
                  ) -> Dict[str, Any]:
    """Run the distiller. Returns {proposed: [...], rejected: [...], retirements: [...]}.

    The LLM proposes; the DETERMINISTIC gate disposes: a proposal without
    >={min_e} supporting events across >={min_p} projects is rejected and
    listed (never silently dropped).
    """
    events = load_ledger()
    if not events:
        return {"proposed": [], "rejected": [], "retirements": [],
                "note": "ledger empty — ship videos and override freely first"}
    existing = [{"id": r["id"], "stage": r["stage"], "scope": r["scope"],
                 "rule": r["rule"], "status": r["status"]}
                for r in load_rules() if r["status"] in ("active", "locked")]
    ledger_txt = "\n".join(
        f"{i}: {e['stage']} | {e['context'][:90]} | "
        f"{e['proposed'][:70]} -> {e['chose'][:70]}"
        for i, e in enumerate(events))
    raw = await llm.generate(_DISTILL_PROMPT.format(
        stages=list(STAGES), existing=json.dumps(existing, ensure_ascii=False),
        ledger=ledger_txt[:14000]))
    m = re.search(r"\{.*\}", raw, re.S)
    j = json.loads(m.group(0)) if m else {}

    proposed, rejected = [], []
    for p in j.get("proposals", []):
        idxs = [i for i in (p.get("event_idx") or [])
                if isinstance(i, int) and 0 <= i < len(events)]
        projects = {events[i]["project"] for i in idxs}
        if len(idxs) < MIN_EVENTS or len(projects) < MIN_PROJECTS:
            rejected.append({**p, "reason":
                             f"evidence gate: {len(idxs)} event(s) across "
                             f"{len(projects)} project(s) — needs "
                             f">={MIN_EVENTS} across >={MIN_PROJECTS}"})
            continue
        rule = upsert_rule({
            "scope": p.get("scope", "channel"),
            "stage": p.get("stage", "scenes"),
            "rule": str(p.get("rule", "")).strip(),
            "why": str(p.get("why", "")).strip(),
            "evidence": [{"project": events[i]["project"],
                          "context": events[i]["context"][:120],
                          "proposed": events[i]["proposed"][:80],
                          "chose": events[i]["chose"][:80]} for i in idxs],
            "confidence": round(min(0.9, 0.4 + 0.1 * len(idxs)), 2),
            "status": "proposed", "source": "owner",
        })
        proposed.append(rule)
    return {"proposed": proposed, "rejected": rejected,
            "retirements": j.get("retirements", [])}
