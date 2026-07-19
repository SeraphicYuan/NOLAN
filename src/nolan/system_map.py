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
import re
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
             "+ timeline view (scenes/motion-badges/sfx/VO on a time axis); "
             "typed @[scope] mentions + registry-driven motion param editor"},
    {"id": "pool", "label": "Asset Pool", "path": "/pool",
     "role": "project media bin (derived): assets tagged in-video/selected/candidate/"
             "shortlisted/unused + shortlist. Source dropdown → HyperFrames comps: the "
             "acquisition pool as pre-selection candidates grouped by NEED, with provider + "
             "CLIP-relevance + VLM usable/flags curation badges (P4.2 contact sheet)"},
    {"id": "voices", "label": "Voices", "path": "/voices",
     "role": "voice library + TTS studio + project voiceover; 'All voiceovers' browses every "
             "existing VO (pipeline projects AND hybrid HyperFrames comps) with players"},
    {"id": "map", "label": "NOLAN Map", "path": "/map",
     "role": "this page — the introspected system catalog"},
    {"id": "themes", "label": "Themes", "path": "/themes",
     "role": "visual showcase of every theme (palette / type / mood) + its composition archetype rendered "
             "as a live specimen in the theme's own tokens; the QA surface for the composition module"},
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
     "consumed_by": "asset pool ('in-video' status) + iterate lane routing "
     "(its presence sends re-renders down the premium lane) + timeline dirty "
     "tint (v2 scene_stamps = edited-since-render)",
     "contract": "scene_id → media paths actually rendered + per-scene "
                 "authored-state stamps; nothing else may write it "
                 "(grep-enforced in test_asset_pool)"},
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
    "effects": {
        "authored_by": [("render-service/_lab_hyperframes/bridge/catalog.json", "treatments"),
                        ("src/nolan/templates/hf_scenes.html", "treatments")],
        "executed_by": [("render-service/_lab_hyperframes/bridge/compose.py", "_fx_overlays"),
                        ("src/nolan/effects/render.py", "def overlay_layers")],
    },
    "composition": {
        "authored_by": [("themes/highlighter-editorial/theme.json", "composition"),
                        ("src/nolan/hyperframes/bespoke.py", "composition")],
        "executed_by": [("src/nolan/composition.py", "def brief_section"),
                        ("src/nolan/hyperframes/bespoke.py", "composition_md"),
                        ("src/nolan/hyperframes/layout_lint.py", "def lint_frame_html")],
    },
    "sound": {
        "authored_by": [("src/nolan/audio_mix.py", "author_sfx_cues"),
                        ("src/nolan/audio_mix.py", "_scene_sfx_cues")],
        "executed_by": [("src/nolan/audio_mix.py", "_source_scene_sfx"),
                        ("src/nolan/audio_mix.py", "mix_from_spec"),
                        ("src/nolan/hyperframes/sound.py", "apply_scene_sfx")],
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
    "effects": [
        ("render-service/_lab_hyperframes/bridge/compose.py", "from nolan.effects.render",
         "compose executor emits ground.treatments (filter + overlays) from the ONE registry"),
        ("render-service/_lab_hyperframes/bridge/author.py", "from nolan.effects.registry",
         "author gate validates ground.treatments against the registry"),
        ("src/nolan/hyperframes/edit.py", "from nolan.effects",
         "edit page serves the registry-derived effects catalog to the Treatments control"),
    ],
    "composition": [
        ("src/nolan/hyperframes/bespoke.py", "_composition.resolve",
         "the bespoke brief resolves + injects the scene's archetype from the ONE registry"),
        ("themes/scripts/validate_themes.py", "ARCHETYPE_IDS",
         "theme validator checks every theme's composition.default/allowed against the registry"),
        ("src/nolan/hyperframes/layout_lint.py", "safe_areas",
         "the deterministic layout linter (gate v2) checks a composed frame's geometry against the "
         "registry's caption_keep_out_y / title_safe_inset / per-archetype zone"),
        ("skills/common/composition-craft.md", "centered-hero",
         "craft skill (registry-synced by tests/test_umbrella_skills.py)"),
    ],
    "sound": [
        ("src/nolan/audio_mix.py", "from nolan.sound",
         "the mix executor resolves a scene's cue-kind to a curated bank file "
         "from the ONE registry (nolan.sound.resolve), preferring it over a live "
         "web search — the same resolver the HyperFrames finish step uses"),
        ("skills/common/sound-craft.md", "whoosh",
         "craft skill (registry-synced by tests/test_sound.py)"),
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
    try:
        from nolan.effects.registry import REGISTRY as EFFECTS
        out["effects"] = [
            {"id": e.id, "purpose": e.purpose, "when_to_use": e.when_to_use,
             "family": e.family, "method": e.method,
             "duration_preserving": e.duration_preserving}
            for e in EFFECTS]
    except Exception as exc:
        out["effects"] = {"error": str(exc)}
    try:
        from nolan.composition import REGISTRY as COMPOSITION
        out["composition"] = [
            {"id": aid, "purpose": a["intent"], "when_to_use": a["when_to_use"],
             "balance": a["balance"], "density": a["density"], "serves_beats": a["serves_beats"]}
            for aid, a in COMPOSITION.items()]
    except Exception as exc:
        out["composition"] = {"error": str(exc)}
    try:
        from nolan.sound.registry import REGISTRY as SOUND
        out["sound"] = [
            {"id": c.id, "purpose": c.purpose, "when_to_use": c.when_to_use,
             "family": c.family, "authored_by": c.authored_by,
             "duration_preserving": c.duration_preserving}
            for c in SOUND]
    except Exception as exc:
        out["sound"] = {"error": str(exc)}
    return out


# ── HyperFrames map ─────────────────────────────────────────────────────────
# The integration target, introspected the same way NOLAN is: skills are read
# from disk (the real .agents/skills/ that .claude/skills/* symlink to), so a
# skill that stops existing is flagged MISSING instead of silently listed.
_SKILLS_ROOT = REPO / ".agents" / "skills"
_HF_DOMAIN = ["hyperframes-core", "hyperframes-animation", "hyperframes-keyframes",
              "hyperframes-creative", "hyperframes-cli", "hyperframes-registry",
              "media-use", "figma"]
_HF_WORKFLOWS = ["faceless-explainer", "product-launch-video", "website-to-video",
                 "embedded-captions", "talking-head-recut", "pr-to-video",
                 "motion-graphics", "music-to-video", "slideshow", "general-video",
                 "remotion-to-hyperframes"]
# The NOLAN default: the HYBRID compose-first pipeline (not the stock faceless steps). The launch form
# (/hyperframes → New essay) sets the theme + acquisition knobs; then:
_HF_PIPELINE = [
    {"name": "0 · brief", "purpose": "SOURCE.md — the script/topic; new-essay picks THEME (any of themes/) + acquisition knobs at launch"},
    {"name": "1 · needs", "purpose": "derive per-beat asset needs from the script (evocative vs concrete, image vs video)"},
    {"name": "2 · acquire", "purpose": "multi-source pool (src/nolan/acquire): fan out to library-CLIP + stock/archival/museum → over-fetch → score (CLIP relevance + fitness, per-need-type tier) → relevance floors → semantic dedup → GENERATE originals for thin/evocative beats"},
    {"name": "2.1 · cull + caption", "purpose": "VLM usability floor (judge.py) fused with captioning — drop watermark/off-topic/stock-graphic junk → capture/pool.json (+ /pool HyperFrames tab)"},
    {"name": "3 · storyboard + VO", "purpose": "STORYBOARD.md + the cloned voiceover bridged in (audio_meta.json, per-section word timings)"},
    {"name": "4 · compose-first", "purpose": "per beat: RESOLVE the composition archetype (themes/composition registry: scene-type → archetype, theme-allowed constrains, direction overrides) → pick a bridge/catalog.json template → author.py GATE (validate→build) → compose.py themed frame; bespoke raw (fleet agent, propose→gate→accept) only where no template fits"},
    {"name": "5 · sync", "purpose": "force-align the VO, place each scene + fire its highlight on the SPOKEN word; recompose changed frames"},
    {"name": "6 · render + QA", "purpose": "seek render → mp4; hf_qa (freeze/audio) + style-contract lint gates → fix + re-render"},
]


def _skill_meta(name: str) -> Optional[str]:
    """Description from a skill's SKILL.md frontmatter (inline or a YAML `>`/`|` folded
    block), truncated for the map; or None if the skill is absent."""
    p = _SKILLS_ROOT / name / "SKILL.md"
    if not p.exists():
        return None
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return None
    d = name
    for i, ln in enumerate(lines):
        m = re.match(r"^description:\s*(.*)$", ln)
        if not m:
            continue
        val = m.group(1).strip().strip('"').strip("'")
        if val in ("", ">", "|", ">-", "|-", ">+", "|+"):  # YAML block scalar → gather indented lines
            buf = []
            for nxt in lines[i + 1:]:
                if re.match(r"^\S", nxt):   # dedent / next key / '---' ends the block
                    break
                if nxt.strip():
                    buf.append(nxt.strip())
            val = " ".join(buf)
        d = val.strip() or name
        break
    return (d[:157] + "…") if len(d) > 158 else d


def _hyperframes() -> Dict[str, Any]:
    if not (_SKILLS_ROOT / "hyperframes").exists():
        return {"ok": False,
                "error": "HyperFrames skills not installed (.agents/skills/hyperframes missing)"}

    def entry(n):
        d = _skill_meta(n)
        return {"id": n, "purpose": d or "MISSING", "ok": d is not None}

    return {
        "ok": True,
        "router": "/hyperframes — routes a 'make me a…' intent to the right workflow",
        "substrate": "HTML + CSS + GSAP + SVG/d3, rendered frame-by-frame in headless "
                     "Chrome; --docker byte-reproducible",
        "determinism": "one paused GSAP timeline per composition; transform/opacity only; "
                       "no Date.now / Math.random / CSS transitions (seek-safe)",
        "authoring": "NOLAN default = COMPOSE-FIRST (hybrid): each beat resolves a composition ARCHETYPE (the "
                     "themes/composition registry — one shared layout vocabulary) then becomes a bridge/catalog.json "
                     "composer template, gated by author.py and built by compose.py in the chosen theme (themes/ "
                     "registry); bespoke raw (a fleet agent authors a custom scene, propose→gate→accept) / native-HF "
                     "only where no template fits. Visuals come from the multi-source acquisition pool. Then a Gate-B "
                     "edit loop (per-scene / batch / effect-from-clip) refines it. (Stock skill-routing still "
                     "available via the workflows below.)",
        "pipeline": _HF_PIPELINE,
        "domain_skills": [entry(n) for n in _HF_DOMAIN],
        "workflows": [entry(n) for n in _HF_WORKFLOWS],
    }


# ── Bridges — where NOLAN meets HyperFrames ─────────────────────────────────
# Each bridge is VERIFIED live (its wire file, optionally containing a token,
# must exist) so the tab can't lie. `stage`: "live" = committed integration
# surface (honesty-tested); "lab" = prototype/working-tree or a runtime dep
# (e.g. vendored, gitignored) that may be absent on a fresh checkout. More
# bridges land here as the NOLAN↔HyperFrames integration grows.
BRIDGES = [
    {"id": "composer", "label": "Scene composer", "stage": "live",
     "purpose": "NOLAN-style reusable templates stamped to HyperFrames frame HTML "
                "(build-time, one merged timeline)",
     "nolan": "module contract — catalog + accept gate + honesty test",
     "hf": "compositions/frames/<id>.html (a <template> sub-comp)",
     "wire": ("render-service/_lab_hyperframes/bridge/catalog.json", "scene_templates")},
    {"id": "gate", "label": "Compose gate", "stage": "live",
     "purpose": "validate an agent's scene spec against the catalog before build "
                "(draft → validate → accept)",
     "nolan": "deterministic accept gate",
     "hf": "the frame is emitted only if the spec validates",
     "wire": ("render-service/_lab_hyperframes/bridge/author.py", "validate_spec")},
    {"id": "compose-first-step5", "label": "Compose-first frame worker", "stage": "live",
     "purpose": "faceless Step-5: map each storyboard Scene → a template, author bespoke "
                "only where none fits",
     "nolan": "agent proposes; catalog + gate decide",
     "hf": "the same frame artifact as the stock frame-worker",
     "wire": (".agents/skills/faceless-explainer/sub-agents/compose-first-frame-worker.md",
              "compose-first")},
    {"id": "ia-images", "label": "Internet Archive images", "stage": "lab",
     "purpose": "NOLAN asset acquisition extended with archive.org stills → the pool → "
                "HyperFrames grounds / props",
     "nolan": "ImageSearchClient provider",
     "hf": "feeds the composer's media_ground / prop_cutout",
     "wire": ("src/nolan/image_search.py", "InternetArchiveImageProvider")},
    {"id": "geo-data", "label": "Geo data vendor", "stage": "lab",
     "purpose": "d3 + topojson + us-atlas / world-atlas backing the geo-map template",
     "nolan": "vendored (gitignored; re-fetch via curl)",
     "hf": "geo_map injects the <script>s at compose time",
     "wire": ("render-service/_lab_hyperframes/bridge/vendor", None)},
    {"id": "themed-composer", "label": "Themed composer (font-robust)", "stage": "live",
     "purpose": "NOLAN's tokens.css theme system drives the composer blocks (CSS-var injection), made "
                "font-robust by a deterministic fit-to-box primitive + a cross-theme layout audit — so "
                "ONE block survives any of the 26 themes' font metrics. A NOLAN-side seam; touches no HF files.",
     "nolan": "themes/<id>/tokens.css → _theme_vars injection + data-fit fit primitive + accept-gate audit",
     "hf": "same seek render (fit runs once on fonts.ready) + `hyperframes inspect` layout audit",
     "wire": ("render-service/_lab_hyperframes/bridge/compose.py", "_theme_vars")},
    {"id": "editing", "label": "Scene edit mode", "stage": "live",
     "purpose": "the /hyperframes page — human-in-the-loop editing OF the composer: patch/add/remove/"
                "retime a scene through the author.py gate, plan within-frame transitions, snapshot-"
                "preview + re-render a frame. Edit per scene, re-render per frame. TWO edit classes: direct UI "
                "patches, and agent edits which are PROPOSALS (comment→agent→gate→human accept→canonical, with "
                "provenance) surfaced in a review panel + activity feed. A NOLAN-side seam.",
     "nolan": "nolan.hyperframes edit engine (mirrors iterate's load→patch→gate→re-render) + propose/accept_proposal + /api/hf/* routes",
     "hf": "re-gates the frame's spec → recomposes compositions/frames/<id>.html → snapshot/render",
     "wire": ("src/nolan/hyperframes/edit.py", "apply_scene_edit")},
    {"id": "voiceover", "label": "Voiceover bridge", "stage": "live",
     "purpose": "NOLAN's cloned voiceover (voice_pipeline) → the faceless `audio_meta.json` shape, so "
                "`audio.mjs sync-durations` (frame dur = section dur; narration owns duration) + "
                "`assemble-index` (root voice track 10) run on the NOLAN voice — no second TTS pass. "
                "Replaces `audio.mjs generate`; wired into new_essay(voiceover=…).",
     "nolan": "voice_pipeline.synthesize_voiceover → bridge/vo_bridge.py translate (+ edit.attach_voiceover)",
     "hf": "<comp>/audio_meta.json + assets/voice/0N.wav → sync-durations + assemble-index + render",
     "wire": ("render-service/_lab_hyperframes/bridge/vo_bridge.py", "def translate")},
    {"id": "style-contract", "label": "Style contract + linter", "stage": "live",
     "purpose": "the editorial-instruction layer: a declarative contract (one preset + a few dials) "
                "dual-compiles to the author's brief AND a deterministic linter that scores the composed "
                "essay on measurable craft dimensions — 5 hard GATES (evidence coverage, motion footage, "
                "pacing variance, block concentration, adjacent repeats) + advisory rest. Draft → lint → "
                "revise. Tweak everything from one registry (dimensions.py); reference-derivable.",
     "nolan": "src/nolan/style_contract — StyleContract.compile_brief() + lint() over a normalized SceneView "
              "(python -m nolan.style_contract <comp> [--brief])",
     "hf": "scenes_from_hf(comp) reads compositions/frames/*.spec.json; gate failures steer re-authoring",
     "wire": ("src/nolan/style_contract/linter.py", "def lint")},
    {"id": "acquisition", "label": "Asset acquisition engine", "stage": "live",
     "purpose": "beat-driven, over-provisioned, MULTI-SOURCE pool. Per need: fan out to the saved image "
                "library (CLIP) + 25 stock/archival/museum providers → over-fetch → score (CLIP relevance + "
                "overlay fitness, per-need-type tier: concrete→literal, evocative→curated) → relevance floors "
                "(library + generic-stock) → avg-hash dedup → GENERATE originals for thin/evocative beats → "
                "VLM usability FLOOR (judge.py, fused with captioning: drop watermark/off-topic/stock-graphic). "
                "Tunable from acquire/config.py; pluggable sources.",
     "nolan": "src/nolan/acquire (engine + build_context + judge, injectable organs) driven by bridge/pool.py",
     "hf": "capture/pool.json + asset-descriptions.md → storyboard SELECTS asset_candidates; browse per-need on /pool (HyperFrames tab)",
     "wire": ("src/nolan/acquire/engine.py", "def acquire_pool")},
    {"id": "composition", "label": "Composition archetype", "stage": "live",
     "purpose": "the ONE shared layout vocabulary (8 archetypes: centered-hero / editorial-column / swiss-grid "
                "/ split-screen / full-bleed-overlay / focal-card / sidebar / framed) so every consumer speaks one "
                "dialect. resolve() is content-first (scene-type→archetype), the theme's composition.allowed "
                "CONSTRAINS, an explicit direction OVERRIDES (the A/B/C/D-proven lever — theme name alone doesn't "
                "steer layout). Injected into the bespoke brief + scene-plan schema + flow dispatch + render-gate "
                "VLM check; showcased on /themes. A NOLAN-side registry seam.",
     "nolan": "themes/composition/archetypes.json → nolan.composition.resolve/brief_section; theme.composition.default/allowed",
     "hf": "the resolved archetype steers where the composer/agent lays a scene out (grid + safe-areas)",
     "wire": ("src/nolan/composition.py", "def resolve")},
    {"id": "bespoke", "label": "Bespoke scene authoring", "stage": "live",
     "purpose": "select one scene or a batch on /hyperframes → 🎨 Bespoke → one fleet agent per scene authors a "
                "fully-CUSTOM raw GSAP scene from a rich brief (narration + word-timings + theme tokens + resolved "
                "composition archetype + continuity + the seek-safe raw contract). REUSES the propose→gate→accept "
                "pipeline: the agent's output is a PROPOSAL that passes author.py's gate (incl. the universal raw "
                "seek-lint) before a human accepts it as canonical. Round-robins nolan1-6.",
     "nolan": "src/nolan/hyperframes/bespoke.py (bespoke_task_brief + dispatch_bespoke) → propose_scene_edit",
     "hf": "accepted raw scene recomposes compositions/frames/<id>.html; provenance carried on the scene",
     "wire": ("src/nolan/hyperframes/bespoke.py", "def dispatch_bespoke")},
    {"id": "effect-clone", "label": "Effect-from-clip", "stage": "live",
     "purpose": "🎬 pick a Clips-page clip → analyze frames → a GSAP brief → an agent authors the motion, landing "
                "either as a per-scene raw {html,tl} (apply_effect) OR as a reusable block (apply_block). Tier-2 "
                "promotes the recurring 'subject + flanking label' shape to the `spotlight` composer block "
                "(bg-removed subject center/left/right + position-responsive label) in compose_extension.py, merged "
                "into compose.BLOCKS with catalog + style-contract parity.",
     "nolan": "src/nolan/hyperframes/effect.py (apply_effect raw / apply_block reusable) + compose_extension.EXT_BLOCKS",
     "hf": "raw lands in the scene's timeline; spotlight is a first-class catalog block any frame can use",
     "wire": ("render-service/_lab_hyperframes/bridge/compose_extension.py", "spotlight")},
]


def _bridges() -> List[Dict[str, Any]]:
    out = []
    for b in BRIDGES:
        wire_path, token = b["wire"]
        p = REPO / wire_path
        ok = p.exists()
        if ok and token and p.is_file():
            try:
                ok = token in p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                ok = False
        row = {k: v for k, v in b.items() if k != "wire"}
        row.update({"wire": wire_path, "ok": ok})
        if b["id"] == "composer" and ok:
            try:
                cat = json.loads((REPO / wire_path).read_text(encoding="utf-8"))
                row["templates"] = sorted(cat.get("scene_templates", {}).keys())
            except Exception:
                pass
        out.append(row)
    return out


# Bridge knowledge base — integration notes surfaced on the Bridge tab. Each doc is verified
# to exist on disk (the tab can't list a doc that isn't there — same honesty rule as bridges).
BRIDGE_KB = [
    {"id": "native-blocks-vs-composer",
     "title": "Native blocks vs the NOLAN composer",
     "purpose": "What a HyperFrames registry block is, what `hyperframes add` installs, and how "
                "native blocks differ from our compose.py block-functions (cinematic-zoom worked example).",
     "doc": "render-service/_lab_hyperframes/kb/native-blocks-vs-composer.md"},
    {"id": "theme-style-pipelines",
     "title": "Theme / style pipelines — NOLAN vs HyperFrames",
     "purpose": "How each system decides + applies a look: NOLAN binds style LATE via tokens "
                "(swap one file, blocks restyle); HyperFrames binds EARLY at authoring time (LLM writes "
                "on-theme CSS per scene). Why the composer is theme-locked today + the tokenization fix.",
     "doc": "render-service/_lab_hyperframes/kb/theme-style-pipelines.md"},
    {"id": "registry-conversion-map",
     "title": "Registry → composer conversion map (Phase 1)",
     "purpose": "Every catalog block/component (13 categories, 133 items) classified CONVERT / KEEP-native / "
                "SKIP. Phase 1 = ~6 theme-driven composer blocks that collapse ~60 native ones (lower_third, "
                "code, social_card, chart, geo-ext, flowchart); shaders/3D/canvas stay native.",
     "doc": "render-service/_lab_hyperframes/kb/registry-conversion-map.md"},
    {"id": "frame-vs-scene",
     "title": "Frame vs scene — the altitude the two systems split at",
     "purpose": "NOLAN edits/renders by SCENE (a shot = its own clip); the HF composer authors/renders by "
                "FRAME (a VO-anchored beat = one merged timeline = one clip) with its own `scenes` (shots) "
                "nested inside. HF `frame` ≈ NOLAN `section`, not a renamed scene. Why the edit mode is "
                "'edit per scene, re-render per frame'.",
     "doc": "render-service/_lab_hyperframes/kb/frame-vs-scene.md"},
    {"id": "asset-editing-in-the-composer",
     "title": "Editing assets & timing in the composer (not just the HTML)",
     "purpose": "The composer edit mode isn't graphics-only: a scene's `data` carries asset paths and its "
                "`start`/`dur` IS the time window, so change/add/plant-asset all map to data+timing patches "
                "(picker → resolve_inject → data field). The genuine gaps (graphic blocks have no asset, "
                "footage via root-video, cross-frame windows = assemble layer) + the two edit classes "
                "(direct UI vs comment→agent→gate).",
     "doc": "render-service/_lab_hyperframes/kb/asset-editing-in-the-composer.md"},
    {"id": "edit-mode-plan",
     "title": "Scene edit mode — design & build plan",
     "purpose": "The design record for the /hyperframes per-scene edit mode (the editing bridge): a "
                "parallel composer-native engine mirroring iterate's load→patch→gate→re-render pattern. "
                "5 build components, edit vocabulary, two edit classes, phasing (P1 direct edits, P2 "
                "comment→agent→gate), and parked assemble-layer items.",
     "doc": "render-service/_lab_hyperframes/kb/edit-mode-plan.md"},
    {"id": "composition-architecture",
     "title": "Composition module — architecture & wiring",
     "purpose": "Why layout/composition is a proper MODULE, not per-theme adhoc: an 'Every Layout'-grounded "
                "archetype registry each theme references, resolved content-first with theme constraint + "
                "direction override. Records the A/B/C/D finding (an explicit named instruction is what moves "
                "layout — theme name doesn't; the left-default is the CSS platform default, not set by NOLAN), "
                "the full pipeline wiring (bespoke brief, scene plan, flows, render-gate, /themes showcase), and "
                "the v2 deferrals (deterministic overlap/position linter, per-block catalog archetype, compose.py "
                "archetype-bias).",
     "doc": "docs/COMPOSITION_ARCHITECTURE.md"},
]


def _bridge_kb() -> List[Dict[str, Any]]:
    return [{"id": k["id"], "title": k["title"], "purpose": k["purpose"],
             "doc": k["doc"], "ok": (REPO / k["doc"]).exists()} for k in BRIDGE_KB]


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
        "hyperframes": _hyperframes(),
        "bridges": _bridges(),
        "bridge_kb": _bridge_kb(),
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
