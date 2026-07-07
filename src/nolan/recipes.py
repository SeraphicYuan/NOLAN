"""Recipes — codified premium mini-sequences (quality program step 7).

Editors call them figures; motion designers call them sequence templates:
the document-reveal, the map-journey, the quote card that lands after its
context. A recipe is a MULTI-SCENE template with typed roles — the agent
picks WHICH recipe and fills its slots; the craft (which effect, how the
parts map) is baked here, deterministic, at whatever execution level the
camera-grammar/bench work has already earned.

- Registry: one JSON per recipe in ``recipes/`` (id, description,
  when_to_use, roles). A role either carries a ``motion`` template (effect +
  ``content_from`` mapping: ``{"slot": name}`` / ``{"scene": field}`` /
  literal) or no motion — the scene renders through the normal ladder
  (its own footage/still with the camera grammar).
- Authored field: ``scene.recipe = {"id", "key", "role", "slots"?}`` —
  ``key`` names the INSTANCE (two map-journeys in one video don't collide);
  consecutive scenes sharing a key form the sequence.
- Materialization: :func:`resolve_plan_recipes` builds motion_specs IN
  MEMORY (premium at plan load; the motion_design gate before hostability
  checks) — the plan keeps the authoring, exactly like the motif layer.
- Candidates: :func:`draft_recipe_candidates` turns a DECONSTRUCTED library
  video's beats into draft recipe files under ``recipes/_candidates/`` for
  human review — promotion = a human moves the file into ``recipes/``
  (proposal → gate → accept; agents get no side-door into the registry).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]
RECIPES_DIR = REPO / "recipes"
CANDIDATES_DIR = RECIPES_DIR / "_candidates"


def load_recipes() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not RECIPES_DIR.exists():
        return out
    for f in sorted(RECIPES_DIR.glob("*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("recipe %s unreadable: %s", f.name, exc)
            continue
        if isinstance(r, dict) and r.get("id"):
            out[str(r["id"])] = r
    return out


def get_recipe(recipe_id: str) -> Optional[Dict[str, Any]]:
    return load_recipes().get(str(recipe_id))


def validate_recipe(recipe: Dict[str, Any]) -> List[str]:
    """Registry-backed: every role's effect must exist and be hostable-class."""
    from nolan.motion.registry import BY_ID
    errors: List[str] = []
    rid = recipe.get("id") or "?"
    if not recipe.get("when_to_use"):
        errors.append(f"{rid}: missing when_to_use (agents can't pick it)")
    roles = recipe.get("roles") or []
    if not roles:
        errors.append(f"{rid}: no roles")
    seen = set()
    for r in roles:
        name = r.get("role")
        if not name:
            errors.append(f"{rid}: role without a name")
            continue
        if name in seen:
            errors.append(f"{rid}: duplicate role {name!r}")
        seen.add(name)
        m = r.get("motion")
        if m is not None:
            eff = m.get("effect")
            if eff not in BY_ID:
                errors.append(f"{rid}.{name}: unknown motion effect {eff!r}")
            if not isinstance(m.get("content_from"), dict):
                errors.append(f"{rid}.{name}: motion needs a content_from map")
    return errors


# ---------------------------------------------------------------------------
# Plan validation + materialization (mirrors the motif layer's contract)
# ---------------------------------------------------------------------------

def _iter_scenes(plan: Dict[str, Any]):
    for scenes in (plan.get("sections") or {}).values():
        if isinstance(scenes, list):
            for s in scenes:
                if isinstance(s, dict):
                    yield s


def validate_plan_recipes(plan: Dict[str, Any]) -> List[str]:
    recipes = load_recipes()
    errors: List[str] = []
    for s in _iter_scenes(plan):
        ref = s.get("recipe")
        if not ref:
            continue
        sid = s.get("id", "?")
        if not isinstance(ref, dict) or not (ref.get("id") and ref.get("role")):
            errors.append(f"{sid}: recipe reference must be {{id, key, role}}")
            continue
        recipe = recipes.get(str(ref["id"]))
        if recipe is None:
            errors.append(f"{sid}: unknown recipe {ref['id']!r} "
                          f"(known: {sorted(recipes)})")
            continue
        role = next((r for r in recipe.get("roles") or []
                     if r.get("role") == ref["role"]), None)
        if role is None:
            errors.append(f"{sid}: recipe {ref['id']!r} has no role "
                          f"{ref['role']!r}")
            continue
        m = role.get("motion")
        if m:
            slots = ref.get("slots") or {}
            for param, src in (m.get("content_from") or {}).items():
                if isinstance(src, dict) and "slot" in src \
                        and src["slot"] not in slots:
                    errors.append(f"{sid}: recipe {ref['id']!r} role "
                                  f"{ref['role']!r} missing slot "
                                  f"{src['slot']!r}")
    return errors


def _map_content(content_from: Dict[str, Any], slots: Dict[str, Any],
                 scene: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for param, src in content_from.items():
        if isinstance(src, dict) and "slot" in src:
            if src["slot"] in slots:
                out[param] = slots[src["slot"]]
        elif isinstance(src, dict) and "scene" in src:
            v = scene.get(src["scene"])
            if v is not None:
                out[param] = v
        else:
            out[param] = src                      # literal
    return out


def resolve_plan_recipes(plan: Dict[str, Any]) -> int:
    """Materialize recipe roles into per-scene motion_specs, IN MEMORY.

    Only roles that carry a ``motion`` template produce a spec; motionless
    roles leave the scene to the normal ladder. An explicit motion_spec on
    the scene wins (explicit beats derived). Returns scenes materialized.
    """
    from nolan.motion.registry import BY_ID
    recipes = load_recipes()
    if not recipes:
        return 0
    done = 0
    for s in _iter_scenes(plan):
        ref = s.get("recipe")
        if not (isinstance(ref, dict) and str(ref.get("id")) in recipes):
            continue
        if s.get("motion_spec"):
            continue
        recipe = recipes[str(ref["id"])]
        role = next((r for r in recipe.get("roles") or []
                     if r.get("role") == ref.get("role")), None)
        m = (role or {}).get("motion")
        if not m:
            continue
        spec = BY_ID.get(m["effect"])
        s["motion_spec"] = {
            "effect": m["effect"],
            "backend": getattr(spec, "backend", "remotion"),
            "target": getattr(spec, "target", None),
            "content": _map_content(m.get("content_from") or {},
                                    ref.get("slots") or {}, s),
            "_from_recipe": f"{ref['id']}:{ref.get('key', '')}",
        }
        done += 1
    return done


def recipes_catalog() -> str:
    """Prompt section for the motion designer — generated from the registry
    (wiring pitfall #5: never a hand list)."""
    recipes = load_recipes()
    if not recipes:
        return ""
    lines = ["\n# Recipe catalog (multi-scene figures — assign consecutive "
             "scenes recipe {id, key, role, slots}; craft is baked, you pick "
             "and fill)"]
    for rid, r in recipes.items():
        roles = " → ".join(x.get("role", "?") for x in r.get("roles") or [])
        lines.append(f"- {rid} [{roles}]: {r.get('when_to_use', '')}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Deconstruct → recipe candidates (the flywheel's intake)
# ---------------------------------------------------------------------------

def draft_recipe_candidates(slug: str, min_shots: int = 3,
                            out_dir: Optional[Path] = None) -> List[Path]:
    """Draft recipe candidates from a deconstructed library video's beats.

    Each beat whose shots show a clear treatment sequence becomes ONE draft
    file under ``recipes/_candidates/`` — description carries what the beat
    said/shown so a human can judge; roles are a SKELETON (asset-type
    sequence) to be authored into real motion mappings on promotion. Drafts
    are never auto-registered: promotion = human moves the file up.
    """
    from nolan.deconstruct.store import DeconstructionStore

    st = DeconstructionStore()
    ex = st.read_extract(slug)
    if not ex:
        raise ValueError(f"no deconstruction extract for {slug!r}")
    shots = ex.get("shots") or []
    out_dir = Path(out_dir) if out_dir else CANDIDATES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for beat in ex.get("beats") or []:
        i0, i1 = beat.get("first_shot"), beat.get("last_shot")
        if i0 is None or i1 is None or (i1 - i0 + 1) < min_shots:
            continue
        seq = [sh for sh in shots
               if i0 <= (sh.get("shot_index") or -1) <= i1]
        if len(seq) < min_shots:
            continue
        # compress the treatment sequence: consecutive same asset_type folds
        pattern, roles = [], []
        for sh in seq:
            t = sh.get("asset_type") or "footage"
            hint = sh.get("treatment_hint") or sh.get("camera_motion") or ""
            if pattern and pattern[-1][0] == t:
                pattern[-1][1] += 1
            else:
                pattern.append([t, 1, hint])
        if len(pattern) < 2:
            continue                              # one texture = not a figure
        for j, (t, n, hint) in enumerate(pattern):
            roles.append({"role": f"{t}-{j + 1}", "count": n,
                          "treatment_hint": hint, "motion": None,
                          "note": "AUTHOR ME: map to a real effect or leave "
                                  "motionless (normal ladder) on promotion"})
        title = beat.get("title") or f"beat-{i0}"
        cid = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or f"beat-{i0}"
        draft = {
            "id": f"CANDIDATE--{cid}",
            "status": "candidate",
            "source": {"deconstruction": slug, "beat": title,
                       "t0": beat.get("t0"), "t1": beat.get("t1"),
                       "function": beat.get("function")},
            "description": (beat.get("shown") or "")[:400],
            "when_to_use": f"(draft) beats functioning as "
                           f"{beat.get('function') or '?'} — review the "
                           f"source span and author the roles",
            "roles": roles,
        }
        p = out_dir / f"{slug[:40]}__{cid[:40]}.json"
        p.write_text(json.dumps(draft, indent=2, ensure_ascii=False),
                     encoding="utf-8")
        written.append(p)
    return written
