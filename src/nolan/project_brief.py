"""The Brief Compiler — style_guide.md (prose) → brief.json (validated tokens).

The style guide is prose for humans and script agents; render-side consumers
need DECISIONS. Until now nothing translated one into the other, so every
project rendered with the same default theme/voice/mood regardless of what
the guide said. This module compiles the guide into ``brief.json``:

  theme        picked DETERMINISTICALLY by the explainable selector in
               themes/ (selector.json reasoning table) from descriptors an
               LLM extracts from the guide — auditable signals recorded
  music_mood   feeds the soundtrack step's track selection
  voice_id     feeds the voiceover ladder (project.yaml still outranks)
  pacing       avg scene seconds min/max targets (retention-linter input)
  accent       optional hex override for the theme's accent token

Per the module contract every field passes a deterministic gate
(validate_brief): the theme must exist in themes/, the voice in the voice
library, numbers must be sane. The LLM only ever proposes; unknown values
fall back, never crash a render. Consumers read via load_brief().
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]
THEMES_DIR = REPO / "themes"
BRIEF_VERSION = 1
BRIEF_NAME = "brief.json"

TONES = ("dark", "light", "warm", "playful", "formal", "neutral")


# --- the explainable theme selector (themes/scripts/select_theme.py) -----------

def _selector_mod():
    p = THEMES_DIR / "scripts" / "select_theme.py"
    spec = importlib.util.spec_from_file_location("nolan_theme_selector", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def rank_themes(brief_text: str, tone: str = "", top: int = 3) -> List[Dict[str, Any]]:
    """[{id, score, why:[signals]}] — deterministic, auditable ranking."""
    sel_mod = _selector_mod()
    sel, themes = sel_mod.load()
    tokens = sel_mod.expand(sel_mod.tokenize(brief_text), sel.get("synonyms", {}))
    ranked = []
    for tid, theme in themes.items():
        meta = (sel.get("themes") or {}).get(tid, {})
        score, hits = sel_mod.score_theme(tid, meta, theme, tokens,
                                          brief_text, sel["weights"], tone or None)
        ranked.append({"id": tid, "score": round(score, 2), "why": hits})
    ranked.sort(key=lambda r: r["score"], reverse=True)
    if ranked and ranked[0]["score"] <= 0:                # nothing fired — fallback
        fb = (sel.get("fallback") or ["bold-signal"])[0]
        ranked.insert(0, {"id": fb, "score": 0.0,
                          "why": ["fallback: no selector signal fired"]})
    return ranked[:top]


# --- descriptor extraction (LLM proposes; deterministic fallback) ---------------

_EXTRACT_PROMPT = """Read this video style guide and extract render-side descriptors.
Reply STRICT JSON only:
{{"keywords": ["8-15 lowercase words for the video's SUBJECT MATTER and VISUAL
   AESTHETIC (from the Look section): e.g. 'tech', 'infrastructure',
   'industrial', 'data', 'cinematic'. NOT rhetoric-form words like 'essay'
   or 'editorial' unless the LOOK itself is print/editorial design."],
  "tone": "the VISUAL tone of the Look section: dark|light|warm|playful|formal|neutral",
  "music_mood": "2-4 words for music selection, e.g. 'tense pulsing electronic'",
  "accent_hex": "#rrggbb if the guide names ONE dominant accent color, else null",
  "grade": {{"grade": "none|warm|cool|noir|vivid — the Look's color cast",
             "bloom": <0..1 highlight bleed; industrial glow ~0.3, clean 0>,
             "grain": <0..1 film grain; documentary texture ~0.15, digital 0>,
             "vignette": <0..1 edge darkening; moody ~0.35, flat 0>}},
  "pacing": {{"avg_scene_s_min": <number>, "avg_scene_s_max": <number>}}}}

STYLE GUIDE:
{guide}
"""

GRADES = ("none", "warm", "cool", "noir", "vivid")   # mirrors Effects.tsx GRADE


def _look_section(guide: str) -> str:
    """The Look section's text (visual language), or '' if not sectioned."""
    m = re.search(r"^#+\s*Look\b(.*?)(?=^#+\s|\Z)", guide, re.M | re.S)
    return m.group(1).strip() if m else ""


def _extract_json(txt: str) -> Optional[dict]:
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


async def _extract_descriptors(guide: str, llm) -> Dict[str, Any]:
    """LLM structured extraction with a fully deterministic fallback."""
    out: Dict[str, Any] = {}
    if llm is not None:
        try:
            raw = await llm.generate(_EXTRACT_PROMPT.format(guide=guide[:12000]))
            out = _extract_json(raw) or {}
        except Exception as exc:
            logger.warning("brief: descriptor LLM failed (%s) — deterministic fallback", exc)
    kws = out.get("keywords")
    if not isinstance(kws, list) or not kws:
        out["keywords"] = []           # selector will tokenize the guide itself
    if out.get("tone") not in TONES:
        out["tone"] = ""
    if not isinstance(out.get("music_mood"), str):
        out["music_mood"] = ""
    hexv = out.get("accent_hex")
    if not (isinstance(hexv, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", hexv)):
        out["accent_hex"] = None
    pac = out.get("pacing") or {}
    try:
        lo = float(pac.get("avg_scene_s_min", 4.0))
        hi = float(pac.get("avg_scene_s_max", 8.0))
    except (TypeError, ValueError):
        lo, hi = 4.0, 8.0
    if not (0.5 <= lo <= hi <= 60):
        lo, hi = 4.0, 8.0
    out["pacing"] = {"avg_scene_s_min": lo, "avg_scene_s_max": hi}
    g = out.get("grade") if isinstance(out.get("grade"), dict) else {}
    grade = {"grade": g.get("grade") if g.get("grade") in GRADES else "none"}
    for k in ("bloom", "grain", "vignette"):
        try:
            grade[k] = round(min(1.0, max(0.0, float(g.get(k, 0.0)))), 2)
        except (TypeError, ValueError):
            grade[k] = 0.0
    out["grade"] = grade
    return out


# --- compile / validate / io ----------------------------------------------------

async def compile_brief(project_path: Path, *, llm=None,
                        style_guide: Optional[str] = None) -> Dict[str, Any]:
    """style_guide.md → validated brief dict (not yet saved)."""
    project_path = Path(project_path)
    guide = style_guide
    if guide is None:
        guide = (project_path / "style_guide.md").read_text(encoding="utf-8")
    desc = await _extract_descriptors(guide, llm)

    # theme: deterministic ranking over the LLM keywords + the guide's LOOK
    # section (the visual language). The Voice section is deliberately NOT
    # ranked — rhetoric words ('essay', 'editorial') describe how the script
    # argues, not how the video should look, and they drag literary themes
    # to the top of every ranking.
    look = _look_section(guide)
    brief_text = " ".join(str(k) for k in desc["keywords"]) + " " + (look or guide)[:4000]
    ranked = rank_themes(brief_text, tone=desc["tone"])

    voice_id = _default_voice(project_path)

    brief = {
        "version": BRIEF_VERSION,
        "theme": ranked[0]["id"],
        "theme_why": ranked[0]["why"][:12],
        "theme_alternatives": [{"id": r["id"], "score": r["score"]} for r in ranked[1:]],
        "accent": desc["accent_hex"],
        "tone": desc["tone"],
        "music_mood": desc["music_mood"],
        "voice_id": voice_id,
        "pacing": desc["pacing"],
        "grade": desc["grade"],
        "provenance": {"compiled_from": "style_guide.md",
                       "selector": "themes/selector.json",
                       "descriptors_via": "llm" if llm is not None else "deterministic"},
    }
    problems = validate_brief(brief)
    if problems:                     # gate: never save an invalid brief
        raise ValueError("brief failed validation: " + "; ".join(problems))
    return brief


def _default_voice(project_path: Path) -> Optional[str]:
    """Voice casting v1: respect an existing project choice, else the config
    default, else the first library voice. (Real casting — matching voice
    character to the guide's tone — is a later, separate decision.)"""
    try:
        import yaml
        meta = yaml.safe_load((project_path / "project.yaml")
                              .read_text(encoding="utf-8")) or {}
        if (meta.get("voice_id") or "").strip():
            return meta["voice_id"].strip()
    except Exception:
        pass
    try:
        from nolan.config import load_config
        v = (getattr(load_config().tts, "default_voice", "") or "").strip()
        if v:
            return v
    except Exception:
        pass
    try:
        from nolan.voice_library import VoiceLibrary
        voices = VoiceLibrary(Path("voices")).list()
        if voices:
            return voices[0].get("id")
    except Exception:
        pass
    return None


def validate_brief(brief: Dict[str, Any]) -> List[str]:
    """Deterministic gate: every field either checks out or is named."""
    problems: List[str] = []
    theme = brief.get("theme")
    if not theme or not (THEMES_DIR / str(theme) / "theme.json").exists():
        problems.append(f"theme {theme!r} not found in themes/")
    accent = brief.get("accent")
    if accent is not None and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(accent)):
        problems.append(f"accent {accent!r} is not #rrggbb")
    g = brief.get("grade")
    if g is not None:
        if not isinstance(g, dict) or g.get("grade") not in GRADES:
            problems.append(f"grade.grade must be one of {GRADES}")
        else:
            for k in ("bloom", "grain", "vignette"):
                v = g.get(k, 0.0)
                if not isinstance(v, (int, float)) or not 0.0 <= float(v) <= 1.0:
                    problems.append(f"grade.{k} must be 0..1")
    if brief.get("tone") not in ("",) + TONES:
        problems.append(f"tone {brief.get('tone')!r} not in {TONES}")
    vid = brief.get("voice_id")
    if vid:
        try:
            from nolan.voice_library import VoiceLibrary
            if not VoiceLibrary(Path("voices")).get(vid):
                problems.append(f"voice_id {vid!r} not in the voice library")
        except Exception:
            pass                     # library unavailable → don't block
    pac = brief.get("pacing") or {}
    try:
        lo, hi = float(pac["avg_scene_s_min"]), float(pac["avg_scene_s_max"])
        if not (0.5 <= lo <= hi <= 60):
            problems.append(f"pacing window {lo}-{hi}s out of range")
    except (KeyError, TypeError, ValueError):
        problems.append("pacing needs avg_scene_s_min/max numbers")
    return problems


def save_brief(project_path: Path, brief: Dict[str, Any]) -> Path:
    p = Path(project_path) / BRIEF_NAME
    p.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def resolve_render_look(meta: Dict[str, Any],
                        brief: Optional[Dict[str, Any]]):
    """(theme, accent) for a render. Explicit project.yaml `theme:` outranks
    the compiled brief (a human override is always final); accent only ever
    comes from the brief."""
    theme = (meta or {}).get("theme") or (brief or {}).get("theme") or "bold-signal"
    return theme, (brief or {}).get("accent")


def load_brief(project_path: Path) -> Optional[Dict[str, Any]]:
    """The project's brief, or None. Invalid briefs are reported and IGNORED
    (a consumer must never render with un-gated values)."""
    p = Path(project_path) / BRIEF_NAME
    if not p.exists():
        return None
    try:
        brief = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("brief.json unreadable (%s) — ignoring", exc)
        return None
    problems = validate_brief(brief)
    if problems:
        logger.warning("brief.json invalid (%s) — ignoring", "; ".join(problems))
        return None
    return brief
