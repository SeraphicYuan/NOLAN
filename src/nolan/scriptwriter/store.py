"""File-backed store for grounded script-writing projects.

A script project IS a normal NOLAN project (``projects/<slug>/`` with
``project.yaml`` + ``script.md``, consumed by the orchestrator Director). This
store adds a ``scriptgen/`` workspace that holds the grounding artifacts the
Director ignores:

    projects/<slug>/
    ├── project.yaml          # Director-ready meta (name, slug, description, …)
    ├── script.md             # FINAL voiceover (## beat headings + Total Duration)
    ├── source/ assets/ output/ .orchestrator/…   # standard project scaffold
    └── scriptgen/            # writing workspace (Director never reads it)
        ├── meta.json         # authoritative: subject, style_id, brief, sources[]
        ├── brief.md          # human-readable brief
        ├── sources/
        │   ├── sources.md    # human-readable manifest
        │   └── raw/S1-*.md   # fetched/pasted source text
        ├── facts.md          # grounded fact sheet ([S1] / [model: needs-check])
        ├── factcheck.md      # claim → supporting source quote / flag
        └── citations.md

Files (not a DB) keep everything human- and agent-readable, matching
``script_style.ScriptStyleStore``.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

DEFAULT_ROOT = Path("projects")

# Pipeline stages surfaced in the UI state machine (docs/SCRIPT_REVIEW_PROGRAM.md §3).
PIPELINE_STATES = ["new", "grounded", "angled", "drafted", "reviewed", "revised", "promoted"]


def _pipeline_state(m: Dict[str, Any]) -> str:
    """Derive a project's coarse pipeline stage from its artifact flags (see get())."""
    reviews = m.get("reviews") or []
    drafts = m.get("drafts") or []
    if m.get("has_script") and m.get("promoted_draft"):
        return "promoted"
    if reviews:
        # "revised" as soon as a NEW draft appears past the latest review (i.e. the revise
        # pass wrote draft-(N+1)) — don't wait on the revision-NN.md changelog, which the
        # agent writes last. The changelog existing is also sufficient (belt + suspenders).
        max_draft = max((_num(d.get("name")) for d in drafts), default=0)
        max_review = max((r.get("n", 0) for r in reviews), default=0)
        if max_draft > max_review or any(r.get("has_revision") for r in reviews):
            return "revised"
        return "reviewed"
    if drafts or m.get("has_script"):
        return "drafted"
    if m.get("has_angles"):
        return "angled"
    if m.get("has_facts"):
        return "grounded"
    return "new"


def _num(name: str) -> int:
    """First integer in a draft/review filename ('draft-02.md' → 2), else 0."""
    mt = re.search(r"(\d+)", str(name or ""))
    return int(mt.group(1)) if mt else 0


def slugify(text: str, fallback: str = "project") -> str:
    """URL/file-safe slug from arbitrary text."""
    s = (text or "").lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^\w\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or fallback


# Project subfolders mirrored from `nolan projects init` so the result is
# orchestrator-ready without depending on that CLI command.
_PROJECT_SUBDIRS = (
    "source", "assets", "output",
    ".orchestrator/instructions", ".orchestrator/feedback",
    ".orchestrator/history", ".orchestrator/modules",
)


class ScriptProjectStore:
    """Manage script-writing projects and their ``scriptgen/`` workspace."""

    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = Path(root)

    # --- paths -----------------------------------------------------------------
    def project_dir(self, slug: str) -> Path:
        return self.root / slug

    def scriptgen_dir(self, slug: str) -> Path:
        return self.project_dir(slug) / "scriptgen"

    def meta_path(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "meta.json"

    def brief_path(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "brief.md"

    def sources_dir(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "sources"

    def sources_raw_dir(self, slug: str) -> Path:
        return self.sources_dir(slug) / "raw"

    def sources_manifest_path(self, slug: str) -> Path:
        return self.sources_dir(slug) / "sources.md"

    def facts_path(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "facts.md"

    def factcheck_path(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "factcheck.md"

    def citations_path(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "citations.md"

    def angles_path(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "angles.md"

    def beatmap_path(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "beatmap.md"

    def report_path(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "report.md"

    def drafts_dir(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "drafts"

    def reviews_dir(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / "reviews"

    # --- completion sentinels + provenance (hub-authored) ----------------------
    def runs_dir(self, slug: str) -> Path:
        return self.scriptgen_dir(slug) / ".runs"

    def done_path(self, slug: str, phase: str) -> Path:
        """The completion sentinel a dispatched agent writes as its LAST action."""
        return self.runs_dir(slug) / f"{phase}.done"

    def clear_done(self, slug: str, phase: str) -> None:
        self.done_path(slug, phase).unlink(missing_ok=True)

    def write_provenance(self, slug: str, phase: str, **fields) -> None:
        """Stamp a hub-authored provenance record for a phase run (not agent-self-reported)."""
        d = self.scriptgen_dir(slug) / ".prov"
        d.mkdir(parents=True, exist_ok=True)
        rec = {"phase": phase, **{k: v for k, v in fields.items() if v is not None}}
        (d / f"{phase}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False),
                                         encoding="utf-8")

    def review_path(self, slug: str, n: int) -> Path:
        return self.reviews_dir(slug) / f"review-{n:02d}.md"

    def review_findings_path(self, slug: str, n: int) -> Path:
        return self.reviews_dir(slug) / f"review-{n:02d}.findings.json"

    def review_approved_path(self, slug: str, n: int) -> Path:
        return self.reviews_dir(slug) / f"review-{n:02d}.approved.json"

    def revision_path(self, slug: str, n: int) -> Path:
        return self.reviews_dir(slug) / f"revision-{n:02d}.md"

    def script_path(self, slug: str) -> Path:
        return self.project_dir(slug) / "script.md"

    def project_yaml_path(self, slug: str) -> Path:
        return self.project_dir(slug) / "project.yaml"

    # --- meta io ---------------------------------------------------------------
    def exists(self, slug: str) -> bool:
        return self.meta_path(slug).exists()

    def _load_meta(self, slug: str) -> Dict[str, Any]:
        p = self.meta_path(slug)
        if not p.exists():
            raise FileNotFoundError(f"script project not found: {slug}")
        return json.loads(p.read_text(encoding="utf-8"))

    def _save_meta(self, meta: Dict[str, Any]) -> None:
        p = self.meta_path(meta["slug"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- crud ------------------------------------------------------------------
    def create(self, name: str, *, subject: str, style_id: str,
               angle: str = "", pivot: str = "", target_minutes: float = 8.0,
               description: str = "", mode: str = "semi",
               composite_spine: Optional[Dict[str, Any]] = None,
               review_archetype: str = "", ad_hoc_questions: Optional[List[str]] = None) -> str:
        """Scaffold a Director-ready project + scriptgen workspace; return slug.

        The optional ``composite_spine`` / ``review_archetype`` / ``ad_hoc_questions`` let the
        caller PRESET the spine, rubric, and producer questions at creation (else Auto/default)."""
        from nolan.scriptwriter.spine_structures import validate_composite_spine
        spine = composite_spine or {}
        if spine and (spine.get("structure") or "single") == "single":
            spine = {}
        ok, err = validate_composite_spine(spine)
        if not ok:
            raise ValueError(err)
        base = slugify(name or subject, "script")
        slug, n = base, 2
        while self.project_dir(slug).exists():
            slug = f"{base}-{n}"
            n += 1

        pdir = self.project_dir(slug)
        for sub in _PROJECT_SUBDIRS:
            (pdir / sub).mkdir(parents=True, exist_ok=True)
        self.sources_raw_dir(slug).mkdir(parents=True, exist_ok=True)

        display_name = name or subject
        # Director-ready project.yaml (same shape as `nolan projects init`).
        self.project_yaml_path(slug).write_text(
            yaml.safe_dump({
                "name": display_name,
                "slug": slug,
                "description": description or subject,
                "source_videos": ["source/"],
                "output_dir": "output/",
                "assets_dir": "assets/",
            }, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

        meta = {
            "slug": slug,
            "name": display_name,
            "subject": subject,
            "style_id": style_id,
            "angle": angle,
            "pivot": pivot,
            "target_minutes": float(target_minutes),
            "description": description or subject,
            "mode": mode if mode in ("auto", "semi") else "semi",
            "chosen_angle": angle.strip(),   # a create-time angle IS the chosen one (else auto-picks)
            "composite_spine": spine,        # {} single · {structure:auto} · preset composite
            "review_archetype": (review_archetype or "").strip(),   # "" = auto-infer
            "ad_hoc_questions": [q.strip() for q in (ad_hoc_questions or []) if q and q.strip()],
            "created_at": datetime.now().isoformat(),
            "status": "new",
            "sources": [],
        }
        self._save_meta(meta)
        self._write_brief(meta)
        self._write_sources_manifest(meta)
        # Placeholder so the project is Director-shaped before the agent writes.
        if not self.script_path(slug).exists():
            self.script_path(slug).write_text(
                "# Video Script\n\n**Total Duration:** _pending_\n\n---\n\n"
                "_Script not written yet. Run the writer to generate it._\n",
                encoding="utf-8")
        return slug

    def get(self, slug: str) -> Dict[str, Any]:
        m = self._load_meta(slug)
        m["source_count"] = len(m.get("sources", []))
        m["has_facts"] = self.facts_path(slug).exists()
        m["has_factcheck"] = self.factcheck_path(slug).exists()
        m["has_angles"] = self.angles_path(slug).exists()
        m["has_report"] = self.report_path(slug).exists()
        m["has_script"] = self._script_written(slug)
        m.setdefault("mode", "semi")
        m.setdefault("chosen_angle", "")
        m.setdefault("review_archetype", "")
        m.setdefault("ad_hoc_questions", [])
        m.setdefault("draft_session", "")
        m.setdefault("composite_spine", {})
        m["drafts"] = self.list_drafts(slug)
        m["reviews"] = self.list_reviews(slug)
        m["state"] = _pipeline_state(m)
        return m

    def list(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not self.root.exists():
            return out
        for d in sorted(self.root.iterdir()):
            if (d / "scriptgen" / "meta.json").exists():
                try:
                    out.append(self.get(d.name))
                except Exception:
                    continue
        out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return out

    def delete(self, slug: str) -> bool:
        d = self.project_dir(slug)
        if not d.exists():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True

    # --- sources ---------------------------------------------------------------
    def _next_source_id(self, meta: Dict[str, Any]) -> str:
        existing = {s["id"] for s in meta.get("sources", [])}
        n = 1
        while f"S{n}" in existing:
            n += 1
        return f"S{n}"

    def add_source(self, slug: str, *, kind: str, title: str = "",
                   url: Optional[str] = None, text: Optional[str] = None) -> Dict[str, Any]:
        """Add a source. ``kind`` ∈ {url, paste, file, reference}.

        If ``text`` is supplied (paste/file), it's saved to raw/ and marked
        ``fetched``. A bare ``url`` is recorded ``pending`` for the agent to
        fetch via WebFetch during the write step.
        """
        meta = self._load_meta(slug)
        sid = self._next_source_id(meta)
        entry: Dict[str, Any] = {
            "id": sid, "kind": kind, "title": title or url or kind,
            "url": url, "added_at": datetime.now().isoformat(),
        }
        if text:
            self.sources_raw_dir(slug).mkdir(parents=True, exist_ok=True)
            fname = f"{sid}-{slugify(title or url or 'source')[:40]}.md"
            (self.sources_raw_dir(slug) / fname).write_text(text, encoding="utf-8")
            entry["text_path"] = str(Path("sources") / "raw" / fname)
            entry["word_count"] = len(text.split())
            entry["status"] = "fetched"
        else:
            entry["status"] = "pending"  # agent will fetch the URL
        meta.setdefault("sources", []).append(entry)
        self._save_meta(meta)
        self._write_sources_manifest(meta)
        return entry

    def remove_source(self, slug: str, sid: str) -> bool:
        meta = self._load_meta(slug)
        sources = meta.get("sources", [])
        kept = [s for s in sources if s["id"] != sid]
        if len(kept) == len(sources):
            return False
        for s in sources:
            if s["id"] == sid and s.get("text_path"):
                (self.scriptgen_dir(slug) / s["text_path"]).unlink(missing_ok=True)
        meta["sources"] = kept
        self._save_meta(meta)
        self._write_sources_manifest(meta)
        return True

    def sources(self, slug: str) -> List[Dict[str, Any]]:
        return self._load_meta(slug).get("sources", [])

    # --- artifact access -------------------------------------------------------
    def read_script(self, slug: str) -> Optional[str]:
        p = self.script_path(slug)
        return p.read_text(encoding="utf-8") if p.exists() else None

    def _script_written(self, slug: str) -> bool:
        """True once script.md holds a REAL script — has ≥1 `## ` beat heading, not just a
        placeholder. (Checking beat headings is robust to any placeholder wording, unlike the
        old single-sentinel check which false-positived on e.g. '_pending_'.)"""
        p = self.script_path(slug)
        if not p.exists():
            return False
        txt = p.read_text(encoding="utf-8")
        if "Script not written yet" in txt:
            return False
        return bool(re.search(r"(?m)^##\s+\S", txt))

    def target_words(self, slug: str) -> int:
        return int(self._load_meta(slug).get("target_minutes", 8.0) * 150)

    def artifact_path(self, slug: str, name: str) -> Optional[Path]:
        return {
            "brief": self.brief_path(slug),
            "facts": self.facts_path(slug),
            "factcheck": self.factcheck_path(slug),
            "citations": self.citations_path(slug),
            "sources": self.sources_manifest_path(slug),
            "angles": self.angles_path(slug),
            "beatmap": self.beatmap_path(slug),
            "report": self.report_path(slug),
        }.get(name)

    # --- mode / chosen angle / drafts (v2 gated flow) --------------------------
    def set_mode(self, slug: str, mode: str) -> Dict[str, Any]:
        meta = self._load_meta(slug)
        meta["mode"] = mode if mode in ("auto", "semi") else "semi"
        self._save_meta(meta)
        return meta

    def set_chosen_angle(self, slug: str, angle: str) -> Dict[str, Any]:
        meta = self._load_meta(slug)
        meta["chosen_angle"] = (angle or "").strip()
        self._save_meta(meta)
        self._write_brief(meta)  # brief reflects the picked angle
        return meta

    def set_composite_spine(self, slug: str, structure: str,
                            threads: List[str], binding: str = "") -> Dict[str, Any]:
        """Set the project's composite spine (Phase 2). Validated against the structure registry;
        `structure='single'` (or empty) clears it back to the default single spine."""
        from nolan.scriptwriter.spine_structures import validate_composite_spine
        threads = [str(t).strip() for t in (threads or []) if str(t).strip()]
        spine = {} if (structure or "single") == "single" else {
            "structure": structure.strip(), "threads": threads, "binding": (binding or "").strip()}
        ok, err = validate_composite_spine(spine)
        if not ok:
            raise ValueError(err)
        meta = self._load_meta(slug)
        meta["composite_spine"] = spine
        self._save_meta(meta)
        return meta

    def set_target_minutes(self, slug: str, minutes) -> Dict[str, Any]:
        """Change the target length (drives target_words for the draft + the gate)."""
        try:
            m = float(minutes)
        except (TypeError, ValueError):
            raise ValueError("minutes must be a number")
        if not (0.5 <= m <= 60):
            raise ValueError("minutes must be between 0.5 and 60")
        meta = self._load_meta(slug)
        meta["target_minutes"] = m
        self._save_meta(meta)
        self._write_brief(meta)   # brief shows the target length
        return meta

    def set_style(self, slug: str, style_id: str) -> Dict[str, Any]:
        """Change the narrative style (voice guide) on an existing project."""
        meta = self._load_meta(slug)
        meta["style_id"] = (style_id or "").strip() or meta.get("style_id")
        self._save_meta(meta)
        self._write_brief(meta)  # brief shows the style
        return meta

    def set_review_archetype(self, slug: str, archetype: str) -> Dict[str, Any]:
        """Override the inferred review archetype (which typed rubric the critic uses)."""
        meta = self._load_meta(slug)
        meta["review_archetype"] = (archetype or "").strip()
        self._save_meta(meta)
        return meta

    def set_ad_hoc_questions(self, slug: str, questions: List[str]) -> Dict[str, Any]:
        """Producer-supplied questions appended to the rubric for this project's reviews."""
        meta = self._load_meta(slug)
        meta["ad_hoc_questions"] = [q.strip() for q in (questions or []) if q and q.strip()]
        self._save_meta(meta)
        return meta

    def set_draft_session(self, slug: str, session: str) -> Dict[str, Any]:
        """Record which fleet agent drafted, so review can be routed to a different one."""
        meta = self._load_meta(slug)
        meta["draft_session"] = (session or "").strip()
        self._save_meta(meta)
        return meta

    def list_drafts(self, slug: str) -> List[Dict[str, Any]]:
        d = self.drafts_dir(slug)
        if not d.exists():
            return []
        out = []
        for p in sorted(d.glob("*.md")):
            try:
                words = len(p.read_text(encoding="utf-8").split())
            except OSError:
                words = 0
            out.append({"name": p.name, "words": words,
                        "path": str(Path("scriptgen") / "drafts" / p.name)})
        return out

    def draft_path(self, slug: str, name: str) -> Optional[Path]:
        # constrain to the drafts dir (no traversal)
        safe = Path(name).name
        p = self.drafts_dir(slug) / safe
        return p if p.exists() else None

    @staticmethod
    def _draft_num(name: str) -> int:
        m = re.search(r"(\d+)", Path(name).stem)
        return int(m.group(1)) if m else 0

    def current_draft(self, slug: str) -> "tuple[int, Optional[Path]]":
        """(number, path) of the highest-numbered draft — the one review operates on.

        Falls back to seeding ``drafts/draft-01.md`` from a written ``script.md`` so the
        review loop always has a numbered base. ``(0, None)`` if nothing is written yet.
        """
        drafts = self.list_drafts(slug)
        if drafts:
            n, name = max((self._draft_num(d["name"]), d["name"]) for d in drafts)
            return n, self.drafts_dir(slug) / name
        if self._script_written(slug):
            self.drafts_dir(slug).mkdir(parents=True, exist_ok=True)
            seed = self.drafts_dir(slug) / "draft-01.md"
            seed.write_text(self.read_script(slug) or "", encoding="utf-8")
            return 1, seed
        return 0, None

    def next_draft_number(self, slug: str) -> int:
        n, _ = self.current_draft(slug)
        return n + 1 if n else 1

    def list_reviews(self, slug: str) -> List[Dict[str, Any]]:
        d = self.reviews_dir(slug)
        if not d.exists():
            return []
        # A review exists if its machine deliverable (findings.json) OR the prose review.md is
        # present — so unattended auto (which skips the prose write-up) still registers.
        ns = {self._draft_num(p.name) for p in d.glob("review-*.findings.json")}
        ns |= {self._draft_num(p.name) for p in d.glob("review-*.md")}
        out: List[Dict[str, Any]] = []
        for n in sorted(x for x in ns if x):
            out.append({
                "name": f"review-{n:02d}.md", "n": n,
                "has_findings": self.review_findings_path(slug, n).exists(),
                "has_md": self.review_path(slug, n).exists(),
                "has_approved": self.review_approved_path(slug, n).exists(),
                "has_revision": self.revision_path(slug, n).exists(),
            })
        return out

    def read_review(self, slug: str, n: int) -> Optional[str]:
        p = self.review_path(slug, n)
        return p.read_text(encoding="utf-8") if p.exists() else None

    def resolve_archetype(self, slug: str) -> str:
        """The review archetype for this project: the human override, else inferred."""
        from nolan.scriptwriter.rubrics import infer_archetype
        meta = self._load_meta(slug)
        return (meta.get("review_archetype") or "").strip() or infer_archetype(meta)

    def read_draft(self, slug: str, name: str) -> Optional[str]:
        p = self.draft_path(slug, name)
        return p.read_text(encoding="utf-8") if p else None

    def promote_draft(self, slug: str, name: str) -> bool:
        """Copy a draft to the Director-ready script.md (the winner of an A/B)."""
        p = self.draft_path(slug, name)
        if not p:
            return False
        self.script_path(slug).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        meta = self._load_meta(slug)
        meta["promoted_draft"] = Path(name).name
        self._save_meta(meta)
        return True

    def read_artifact(self, slug: str, name: str) -> Optional[str]:
        """Read a named scriptgen artifact (brief/facts/factcheck/citations/sources)."""
        p = self.artifact_path(slug, name)
        if p is None or not p.exists():
            return None
        return p.read_text(encoding="utf-8")

    def angle_candidates(self, slug: str) -> List[Dict[str, Any]]:
        """Parse angles.md into selectable cards: `### Angle N — <thesis>` / `**Angle N — …**`,
        marking the `**[CHOSEN]**` one. Best-effort; empty list if angles.md is absent/odd."""
        p = self.angles_path(slug)
        if not p.exists():
            return []
        out: List[Dict[str, Any]] = []
        cur: Optional[Dict[str, Any]] = None
        head_re = re.compile(r"^\s*(?:#{2,4}\s*|\*\*)\s*Angle\s*(\d+)\s*[—\-:]\s*(.+)$", re.I)
        for line in p.read_text(encoding="utf-8").splitlines():
            m = head_re.match(line)
            if m:
                if cur:
                    out.append(cur)
                chosen = "chosen" in line.lower()
                title = re.sub(r"\*+", "", m.group(2))
                title = re.sub(r"\[?\s*chosen\s*\]?", "", title, flags=re.I).strip(" —-*")
                cur = {"n": int(m.group(1)), "title": title, "chosen": chosen, "body": ""}
            elif cur is not None:
                cur["body"] += line + "\n"
        if cur:
            out.append(cur)
        for c in out:
            c["body"] = c["body"].strip()[:500]
        return out

    def read_source_text(self, slug: str, sid: str) -> Optional[str]:
        """Read the fetched/pasted raw text for one source, if present."""
        for s in self.sources(slug):
            if s["id"] == sid and s.get("text_path"):
                p = self.scriptgen_dir(slug) / s["text_path"]
                return p.read_text(encoding="utf-8") if p.exists() else None
        return None

    # --- human-readable views --------------------------------------------------
    def _write_brief(self, meta: Dict[str, Any]) -> None:
        slug = meta["slug"]
        lines = [
            f"# Script Brief — {meta['name']}", "",
            f"- **Subject:** {meta['subject']}",
            f"- **Style:** `{meta['style_id']}` (narrative voice guide)",
            f"- **Angle:** {meta.get('angle') or '_(none — writer chooses)_'}",
            f"- **Hidden-detail pivot:** {meta.get('pivot') or '_(none specified)_'}",
            f"- **Target length:** ~{meta.get('target_minutes', 8)} min "
            f"(~{int(meta.get('target_minutes', 8) * 150)} words)",
            "",
            "_Edit this brief freely before running the writer._",
        ]
        self.brief_path(slug).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_sources_manifest(self, meta: Dict[str, Any]) -> None:
        slug = meta["slug"]
        lines = [f"# Sources — {meta['name']}", ""]
        if not meta.get("sources"):
            lines.append("_No sources yet._")
        for s in meta.get("sources", []):
            loc = s.get("text_path") or s.get("url") or ""
            wc = s.get("word_count")
            size = ""
            if isinstance(wc, int):
                # flag large sources so grounding chunk-reads them (don't dump whole)
                size = f" · {wc:,} words" + ("  ⚠ LARGE — chunk-read" if wc > 8000 else "")
            lines.append(
                f"- **[{s['id']}]** ({s['kind']}, {s['status']}) "
                f"{s.get('title') or ''} — {loc}{size}".rstrip())
        self.sources_manifest_path(slug).parent.mkdir(parents=True, exist_ok=True)
        self.sources_manifest_path(slug).write_text("\n".join(lines) + "\n", encoding="utf-8")
