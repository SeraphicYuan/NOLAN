"""The Live NOLAN Map — an introspected system catalog, not a drawing.

Everything on the map is read from the code's own registries AT REQUEST TIME
(PIPELINE_STEPS + step docstrings, module docstrings, the skills index, the
motion/workflow registries, the blocks library, live service pings), so the
map cannot rot the way hand-drawn architecture diagrams do. Anything declared
here that stops existing is *flagged* on the map instead of silently lying.

Taxonomy (the altitude is fixed — components, never functions):
  SPINE     the ordered, artifact-producing Director steps
  ORGANS    engines the steps call (no UI of their own)
  LABS      human exploration tools that FEED pipeline artifacts
  SKILLS    agent-facing procedures (typed registry in skills/index.json)
  SURFACES  hub pages
  ARTIFACTS the contract files that flow through the spine
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]

# Modules are LISTED here but described by their own docstrings (first line),
# so purposes live with the code. A listed module that fails to import is
# shown as MISSING — the map's honesty guarantee.
ORGAN_MODULES = [
    "nolan.asset_engine", "nolan.voice_pipeline", "nolan.audio_mix",
    "nolan.layout_blocks", "nolan.premium_render", "nolan.motion",
    "nolan.editing",
    "nolan.render_dispatch", "nolan.clip_matcher", "nolan.external_assets",
    "nolan.art_sourcing", "nolan.evoke_broll", "nolan.imagelib",
    "nolan.image_search", "nolan.captions", "nolan.aligner",
    "nolan.scenes", "nolan.whisper", "nolan.tts", "nolan.comfyui",
    "nolan.workflow_registry", "nolan.deconstruct", "nolan.visual_facts",
    "nolan.script_style", "nolan.tempo_plan", "nolan.voiceover",
    "nolan.knowledge_query", "nolan.flows",
    "nolan.style_packs", "nolan.recipes", "nolan.exemplars",
]

LABS = [
    {"id": "script-styles", "label": "Script Styles", "path": "/script-styles",
     "imports": "a channel's writing voice", "feeds": "style guide → match_and_adapt_style"},
    {"id": "video-styles", "label": "Video Styles", "path": "/video-styles",
     "imports": "a video's visual language", "feeds": "style templates → match_and_adapt_style"},
    {"id": "deconstruct", "label": "Deconstruct", "path": "/deconstruct",
     "imports": "a video's structure/tempo/pairing", "feeds": "reference → tempo blend, clone mode"},
    {"id": "clips", "label": "Clips", "path": "/clips",
     "imports": "a clip's motion vocabulary", "feeds": "effect analysis → motion library (promotion)"},
    {"id": "broll", "label": "Evocative B-roll", "path": "/broll",
     "imports": "operator-driven asset pairing", "feeds": "picks → scene attach; bridge → asset engine"},
    {"id": "library", "label": "Library / Ingest", "path": "/library",
     "imports": "source footage + analysis", "feeds": "indexed segments → clip search"},
    {"id": "images", "label": "Picture Library", "path": "/images",
     "imports": "curated stills (CLIP+BGE)", "feeds": "library tier of the asset engine"},
    {"id": "extract", "label": "Extract Assets", "path": "/extract",
     "imports": "hi-def images from URLs", "feeds": "picture library"},
]

SURFACES = [
    {"id": "studio", "label": "Project Dashboard", "path": "/studio",
     "role": "the spine's cockpit: pipeline chips, run controls, artifacts, final player"},
    {"id": "agents", "label": "Agents", "path": "/agents",
     "role": "checkpoints, plans, runlogs, feedback/refine for agent-driven steps"},
    {"id": "scenes", "label": "Scenes", "path": "/scenes",
     "role": "the scene-plan editor: edit/comment → invalidate → re-render; "
             "+ timeline view (scenes/motion-badges/sfx/VO on a time axis)"},
    {"id": "pool", "label": "Asset Pool", "path": "/pool",
     "role": "the project media bin (derived): every asset tagged in-video/"
             "selected/candidate/shortlisted/unused; shortlist with scene hint"},
    {"id": "voices", "label": "Voices", "path": "/voices",
     "role": "voice library + TTS studio + project voiceover"},
    {"id": "map", "label": "NOLAN Map", "path": "/map",
     "role": "this page — the introspected system catalog"},
    {"id": "taste", "label": "Taste", "path": "/taste",
     "role": "learned channel preferences: review distiller proposals, "
             "amend/lock/retire rules (priors, not laws)"},
    {"id": "skills-page", "label": "Skills", "path": "/skills",
     "role": "the agent-facing skills registry"},
    {"id": "publish", "label": "Publish", "path": "/publish", "role": "delivery"},
    {"id": "settings", "label": "Settings", "path": "/settings", "role": "configuration"},
]

ARTIFACTS = [
    {"name": "script.md", "produced_by": "scriptwriter agents (v3)",
     "consumed_by": "script_to_scenes, voiceover", "contract": "## sections = beats"},
    {"name": "style_guide.md", "produced_by": "match_and_adapt_style",
     "consumed_by": "script_to_scenes, generate_assets (style suffix)",
     "contract": "voice + visual language for the project"},
    {"name": "brief.json", "produced_by": "match_and_adapt_style (brief compiler)",
     "consumed_by": "render (theme+accent), soundtrack (music_mood), voiceover (voice)",
     "contract": "the guide COMPILED to validated tokens — theme via the "
                 "explainable selector, gated by nolan.brief.validate_brief"},
    {"name": "scene_plan.json", "produced_by": "script_to_scenes (+ every step mutates)",
     "consumed_by": "everything downstream",
     "contract": "LOSSLESS schema v2 — unknown keys survive (Scene.extra / ScenePlan.meta)"},
    {"name": "assets/voiceover/ (+_work/sec_*.wav)", "produced_by": "voiceover step",
     "consumed_by": "align_narration, premium mode, soundtrack",
     "contract": "per-section wavs = THE beat anchors; narration owns duration"},
    {"name": "soundtrack.json", "produced_by": "soundtrack step (authoring)",
     "consumed_by": "render step (mix_from_spec)",
     "contract": "track + alternatives + gain/duck + sfx events — human-editable"},
    {"name": "shortlist.json", "produced_by": "human curation (library/select pages, "
     "/api/shortlist, /api/pool/shortlist)",
     "consumed_by": "asset engine TIER 0 (selects pool; scene_hint items are "
     "near-pins for that scene) + /scenes picker + asset pool view",
     "contract": "items carry ready-to-POST payloads; notes become scene.human_note "
                 "directives when the tier-0 matcher picks them"},
    {"name": "output/final.mp4", "produced_by": "render step",
     "consumed_by": "you", "contract": "|video − narration| < 1s, honest failures"},
    {"name": "output/render_manifest.json", "produced_by": "render step ONLY "
     "(premium_render, after a successful concat)",
     "consumed_by": "asset pool (/api/pool + /pool page) — the sole source of "
     "'in-video' status",
     "contract": "scene_id → media paths actually rendered; nothing else may "
                 "write it (grep-enforced in test_asset_pool)"},
    {"name": "profiles/taste.json (+ledger.jsonl)",
     "produced_by": "taste distiller (`nolan retro`) + /taste edits",
     "consumed_by": "authoring prompts via nolan.taste.guidance_for "
                    "(scenes/slides/motion stages)",
     "contract": "rules are TIERED PRIORS — active=prefer-with-deviation, "
                 "locked=constraint (human act only), evidence attached, "
                 "retirable; test projects excluded from the ledger"},
]


def _first_doc_line(mod) -> str:
    doc = (getattr(mod, "__doc__", "") or "").strip()
    return doc.splitlines()[0].strip() if doc else ""


def _spine() -> List[Dict[str, Any]]:
    from nolan.orchestrator.director import PIPELINE_STEPS, Director
    steps = []
    for name in PIPELINE_STEPS:
        fn = getattr(Director, f"_run_{name}_step", None)
        doc = (fn.__doc__ or "").strip().splitlines()[0] if fn and fn.__doc__ else ""
        steps.append({"name": name, "purpose": doc})
    return steps


def _organs() -> List[Dict[str, Any]]:
    out = []
    for name in ORGAN_MODULES:
        try:
            mod = importlib.import_module(name)
            out.append({"module": name, "purpose": _first_doc_line(mod), "ok": True})
        except Exception as exc:
            out.append({"module": name, "purpose": f"MISSING: {exc}", "ok": False})
    return out


def _skills() -> Dict[str, Any]:
    try:
        idx = json.loads((REPO / "skills" / "index.json").read_text(encoding="utf-8"))
        return {"count": idx.get("count", len(idx.get("skills", []))),
                "skills": [{"id": s.get("id"), "kind": s.get("kind"),
                            "purpose": s.get("purpose"), "status": s.get("status"),
                            "version": s.get("version"),
                            "handoffs": s.get("handoffs", [])}
                           for s in idx.get("skills", [])]}
    except Exception as exc:
        return {"count": 0, "skills": [], "error": str(exc)}


# The umbrella-level consumer manifest (WIRING_CHECKLIST pitfall #2:
# capable-but-unauthored). Every umbrella names its AUTHORING surface and its
# EXECUTOR, each as (repo-relative file, token that must appear in it) —
# grep-verified by tests/test_umbrella_wiring.py. A new umbrella added to
# _umbrellas() without both wires fails the suite on day one; a refactor
# that moves either wire fails until the manifest is updated to the truth.
UMBRELLA_WIRING: Dict[str, Dict[str, Any]] = {
    "editing": {
        "authored_by": [("src/nolan/tempo_plan.py", "transition"),
                        ("src/nolan/templates/scenes.html", "field-${scene.id}-shots")],
        "executed_by": [("src/nolan/premium_render.py", "transitionIn"),
                        ("src/nolan/premium_render.py", "_expand_shots")],
    },
    "motion": {
        "authored_by": [("src/nolan/orchestrator/director.py", "_run_motion_design_step")],
        "executed_by": [("src/nolan/motion/executor.py", "chapter_step_for_spec"),
                        ("src/nolan/motion/executor.py", "def render")],
    },
    "pairing": {
        "authored_by": [("src/nolan/asset_engine.py", "_bridge_probes"),
                        ("src/nolan/webui/routes/scenes.py", "super-search")],
        "executed_by": [("src/nolan/evoke_broll.py", "OPERATORS")],
    },
    "blocks": {
        "authored_by": [("src/nolan/orchestrator/director.py", "_run_slide_designer_step")],
        "executed_by": [("src/nolan/layout_blocks.py", "ADAPTERS")],
    },
    "themes": {
        "authored_by": [("src/nolan/project_brief.py", "rank_themes")],
        "executed_by": [("render-service/remotion-lib/stage.mjs", "_active-theme")],
    },
}


# CATALOG CONSUMPTION (WIRING_CHECKLIST pitfall #5, extended from existence
# to CONSUMPTION): an umbrella's catalog must REACH every decision point that
# chooses from it — injected into the prompt, imported as the vocabulary, or
# loaded via an honesty-tested skill. Each entry is (repo-relative file,
# token that must appear in it, role); grep-verified by
# tests/test_catalog_consumers.py. History: motion was injected, but the
# editing/pairing catalogs reached NO spine step — tempo kept a private
# transition tuple synced by comment, and the evoke planner's operator menu
# was hand-written prose that duplicated when_to_use.
CATALOG_CONSUMERS: Dict[str, List[tuple]] = {
    "motion": [
        ("src/nolan/orchestrator/director.py", "_hostable_motion_catalog()",
         "motion_design prompt injects the hostable-effects catalog JSON"),
        ("skills/orchestrator/motion-designer.md", "catalog",
         "agent skill (registry-synced by tests/test_umbrella_skills.py)"),
    ],
    "editing": [
        ("src/nolan/tempo_plan.py", "from nolan.editing import TRANSITIONS",
         "tempo authors transitions from the ONE registry vocabulary"),
        ("skills/common/editing-craft.md", "j-cut",
         "craft skill (registry-synced by tests/test_umbrella_skills.py)"),
    ],
    "pairing": [
        ("src/nolan/evoke_broll.py", "operator_menu()",
         "L3 planner menu GENERATED from OPERATORS (never a hand list)"),
        ("skills/common/pairing-craft.md", "when-to-use",
         "craft skill (registry-synced by tests/test_umbrella_skills.py)"),
    ],
    "blocks": [
        ("skills/orchestrator/slide-designer.md", "nolan capabilities -u blocks",
         "slide designer told to read the machine catalog"),
        ("skills/orchestrator/script-to-scenes.md", "nolan capabilities",
         "scene design told the downstream vocabulary is machine-readable"),
    ],
    "themes": [
        ("src/nolan/project_brief.py", "rank_themes",
         "brief compiler ranks the theme registry (Look-based selector)"),
    ],
    # style packs: cross-umbrella curation (quality program step 6) — every
    # pack field must reach a decision point or it's curation rot
    "packs": [
        ("src/nolan/project_brief.py", "pack_for",
         "brief compiler resolves the pack (theme promotion, grade/pacing fills)"),
        ("src/nolan/orchestrator/director.py", "_sp_motion_guidance",
         "motion_design prompt carries the pack's preferred/avoid effects"),
        ("src/nolan/orchestrator/director.py", "_sp_slides_guidance",
         "slide_designer prompt carries the pack's preferred templates"),
        ("src/nolan/retention.py", "_pack_format",
         "retention linter enforces the pack's format (show bible) rules"),
        ("src/nolan/orchestrator/director.py", "_sp_tempo_hint",
         "tempo prompt carries the pack's transition bias"),
    ],
    # recipes: multi-scene figures (quality program step 7)
    "recipes": [
        ("src/nolan/orchestrator/director.py", "_recipes_catalog",
         "motion_design prompt carries the recipe catalog (generated)"),
        ("src/nolan/premium_render.py", "resolve_plan_recipes",
         "premium materializes recipe roles at plan load"),
        ("src/nolan/orchestrator/director.py", "validate_plan_recipes",
         "motion_design gate validates recipe references"),
    ],
}


def _umbrellas() -> Dict[str, Any]:
    """The capability registries, umbrella by umbrella (module contract).

    This is the machine-readable catalog agents consume (also via
    `nolan capabilities`): every entry carries when_to_use — the craft
    guidance for PICKING a capability, not just its existence. Only
    code-backed registries appear here; nothing is hand-listed.
    """
    out: Dict[str, Any] = {}
    try:
        from nolan.editing import REGISTRY as EDITING
        out["editing"] = [
            {"id": t.id, "purpose": t.purpose, "when_to_use": t.when_to_use,
             "scope": t.scope, "authored_by": t.authored_by,
             "duration_preserving": t.duration_preserving}
            for t in EDITING]
    except Exception as exc:
        out["editing"] = {"error": str(exc)}
    try:
        from nolan.motion.registry import REGISTRY as MOTION
        out["motion"] = [
            {"id": e.id, "purpose": e.purpose, "when_to_use": e.when_to_use,
             "backend": e.backend, "category": e.category,
             **({"provenance": e.provenance} if e.provenance else {})}
            for e in MOTION]
    except Exception as exc:
        out["motion"] = {"error": str(exc)}
    try:
        from nolan.evoke_broll import OPERATORS
        out["pairing"] = [{"id": k, **v} for k, v in OPERATORS.items()]
    except Exception as exc:
        out["pairing"] = {"error": str(exc)}
    try:
        from nolan.layout_blocks import ADAPTERS, TEMPLATES
        out["blocks"] = [
            {"id": t, **TEMPLATES.get(t, {"purpose": "", "when_to_use": ""})}
            for t in sorted(ADAPTERS)]
    except Exception as exc:
        out["blocks"] = {"error": str(exc)}
    try:
        out["themes"] = sorted(p.name for p in (REPO / "themes").iterdir()
                               if p.is_dir())
    except Exception as exc:
        out["themes"] = {"error": str(exc)}
    return out


def _ping(url: str, timeout: float = 1.5) -> bool:
    try:
        import httpx
        return httpx.get(url, timeout=timeout).status_code < 500
    except Exception:
        return False


def _count(fn, label: str):
    try:
        return fn()
    except Exception as exc:
        logger.debug("map count %s failed: %s", label, exc)
        return None


def _health(ping: bool = True) -> Dict[str, Any]:
    from nolan.motion.registry import REGISTRY as MOTION

    h: Dict[str, Any] = {
        "motion_effects": len(MOTION),
        "themes": _count(lambda: sum(1 for p in (REPO / "themes").iterdir()
                                     if p.is_dir()), "themes"),
        "music_tracks": _count(lambda: sum(
            1 for p in (REPO / "projects/_library/music").iterdir()
            if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}), "music"),
        "remotion_blocks": _count(lambda: sum(
            1 for p in (REPO / "render-service/remotion-lib/src/blocks/library").glob("*.tsx")),
            "blocks"),
        "workflows": _count(lambda: len(
            importlib.import_module("nolan.workflow_registry").get_registry().list()),
            "workflows"),
    }
    if ping:
        h["render_service"] = _ping("http://127.0.0.1:3010/health")
        h["comfyui"] = _ping("http://127.0.0.1:8080/system_stats")
    return h


def build_map(app=None, ping: bool = True) -> Dict[str, Any]:
    """The full catalog. `app` (a FastAPI instance) verifies surface/lab paths."""
    known_paths = set()
    if app is not None:
        known_paths = {getattr(r, "path", "") for r in app.routes}

    def verify(entries):
        out = []
        for e in entries:
            e = dict(e)
            e["ok"] = (e["path"] in known_paths) if known_paths else None
            out.append(e)
        return out

    return {
        "generated": "live",           # built at request time, by construction
        "spine": _spine(),
        "organs": _organs(),
        "labs": verify(LABS),
        "skills": _skills(),
        "surfaces": verify(SURFACES),
        "artifacts": ARTIFACTS,
        "umbrellas": _umbrellas(),
        "health": _health(ping=ping),
        "wiring": {
            "manifest": "docs/UI_WIRING.md",
            "audited": "2026-07-05",
            "verdicts": {"broken": 0, "dead": 0,
                         "advisory": ["video_styles guide (reference-only)",
                                      "broll lab picks (no persistence control)"]},
        },
        "policy": {
            "routing": ("deterministic where correctness is computable (timing, "
                        "mixing, gates, matching) · LLM-API for cheap structured "
                        "judgment (bridging, scoring, describing) · agent+skill "
                        "for open-ended synthesis and taste (script voice, scene "
                        "design, effect design, refinement)"),
            "agent_contract": ("agent output is a PROPOSAL artifact that passes a "
                               "deterministic gate before becoming canonical "
                               "(draft → validate → accept)"),
        },
    }
