"""Evocative (tonal) b-roll search — stock mode.

Given a narration line (+ optional story period/locale + literalness), find EVOCATIVE stock
b-roll — footage that carries the EMOTION of the line, not a literal illustration of its words:

  1. bridge   — an LLM turns the line into timeless visual METAPHORS (+ the target emotion and
                the literal subjects to avoid), steered toward universal nature/abstract imagery.
  2. retrieve — the cheap stock-video tiers (Pexels/Pixabay/…, tiered fan-out) fetch real clips.
  3. gate     — a vision pass scores each clip's preview still for mood-evocation + non-literal-
                ness, and (if a period/locale is given) flags anachronism/wrong-locale; pure
                nature/abstract is treated as UNIVERSAL and exempt.
  4. accept   — a listwise "would a pro editor cut this?" pass returns the picks, or UNMATCHED
                when nothing clears the bar (precision over coverage — a wrong shot hurts more
                than a gap).

Pure retrieval/ranking over public stock APIs + the same OpenRouter vision model used for
ingest. No expensive/paid tiers. See docs + the /broll hub page.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

# generated stills land here and are served by the hub at GEN_URL (mounted in hub.py)
GEN_DIR = Path("projects/_library/_broll_generated")
GEN_URL = "/broll-gen"

from .config import load_config
from .llm import create_text_llm
from .vision import VisionConfig, create_vision_provider
from .image_search import ImageSearchClient, ImageScorer


def _extract_json(txt: str):
    txt = (txt or "").strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
    a, b = txt.find("{"), txt.rfind("}")
    if a == -1:
        a, b = txt.find("["), txt.rfind("]")
    return json.loads(txt[a:b + 1])


def _vision_config(config) -> VisionConfig:
    """Same OpenRouter vision model ingest uses (qwen/qwen3.7-plus), reasoning off for speed."""
    model = config.vision.model
    if "/" not in model:
        model = "qwen/qwen3.7-plus"
    return VisionConfig(
        provider="openrouter", model=model, host=config.vision.host, port=config.vision.port,
        timeout=config.vision.timeout, api_key=config.vision.openrouter_api_key,
        base_url=config.vision.base_url, reasoning_enabled=False,
    )


_BRIDGE_SYS = (
    "You are a documentary film EDITOR choosing EVOCATIVE b-roll — footage that carries the "
    "EMOTION and SUBTEXT of a line, NOT a literal illustration of its words. Reply STRICT JSON.")

_LISTWISE_SYS = (
    "You are a senior video-essay editor making the FINAL cut decision for one narration beat. "
    "You would rather leave the beat UNMATCHED than cut b-roll that is off-mood, too literal, or "
    "a reach. Precision over coverage — a wrong shot hurts more than a gap. Reply STRICT JSON.")


def _bridge_prompt(line: str, period: str, locale: str, literalness: float, mood: Optional[str]) -> str:
    lit = ("Stay ABSTRACT/oblique — avoid the literal subjects." if literalness <= 0.35
           else "Semi-literal is OK if it also carries the mood." if literalness <= 0.7
           else "Fairly literal is OK, but still prioritise mood.")
    ctx = ""
    if period or locale:
        ctx = (f"STORY PERIOD: {period or 'unspecified'}\nSTORY LOCALE: {locale or 'unspecified'}\n"
               "Prefer TIMELESS, UNIVERSAL imagery — landscape, nature and natural elements (sea, sky, "
               "fire, storm, dust, stone, rain, mist, light) and abstract texture — which fit ANY era/place. "
               "AVOID modern/industrial/urban objects, vehicles, technology, contemporary people or clothing, "
               "and culture-specific artifacts that would clash with the story's period and locale.\n")
    steer = f"Editor's mood steer (override): {mood}\n" if mood else ""
    return (f'LINE: "{line}"\n{steer}{ctx}Literalness = {literalness:.2f}. {lit}\n\n'
            'Return JSON: {"subtext": "the real emotional meaning (1 sentence)", '
            '"target_emotion": "2-4 words", '
            '"visual_metaphors": ["5-7 SHORT visual search phrases that EVOKE the emotion WITHOUT depicting '
            'the literal subject — describe mood/light/space/motion"], '
            '"avoid_literal": ["literal subjects a naive search would return that we should NOT show"]}')


_CONCEPTUAL_BRIDGE_SYS = (
    "You are a video-essay editor who visualizes ABSTRACT ideas through CONCEPTUAL METAPHOR — you find a "
    "concrete domain whose MECHANIC is structurally the same as the idea (strategy→chess, cascade/collapse→"
    "dominoes, fragile balance→Jenga, opposing forces→tug-of-war, systems→clockwork, emergent order→a "
    "murmuration). Reply STRICT JSON.")

# Per-operator phrasing so the vision/library/accept prompts read correctly for each pairing style.
# The score fields stay `mood` (primary fit) + `nonliteral` (secondary axis); only the wording changes.
_OP = {
    "tonal": {
        "noun": "emotion",
        "judge": "Judge the FRAME as mood b-roll (color, light, composition) — NOT literal illustration.",
        "match": "how strongly its atmosphere EVOKES the emotion",
        "match_lib": "evokes the emotion",
        "axis2": "10=oblique/evocative, 0=literally depicts the subject",
        "accept": "the mood must be right, it must be evocative (not literal), and it must actually work on screen",
    },
    "conceptual": {
        "noun": "concept",
        "judge": "Judge the FRAME as a visual METAPHOR for the concept — does its subject/action mirror the concept's mechanic and read at a glance?",
        "match": "how clearly it reads as an apt visual metaphor for the concept",
        "match_lib": "reads as an apt visual metaphor for the concept",
        "axis2": "10=fresh/surprising, 0=tired cliché",
        "accept": "it must clearly and aptly convey the concept as a metaphor, read at a glance, and not be a tired cliché",
    },
    "ironic": {
        "noun": "counterpoint",
        "judge": "Judge the FRAME as IRONIC COUNTERPOINT — does it CONTRADICT/undercut the line (expose the gap between what's said and what's real), not illustrate it?",
        "match": "how sharply it ironically undercuts the line",
        "match_lib": "ironically undercuts the line",
        "axis2": "10=pointed but not heavy-handed, 0=on-the-nose or unrelated",
        "accept": "it must clearly UNDERCUT the line (show the opposite / the cost / the hollow reality), land as deliberate irony, and not merely illustrate the words",
    },
    "trait": {
        "noun": "trait",
        "judge": "Judge the FRAME as embodying the TRAIT through an exemplary activity — does the action read as a person of that quality?",
        "match": "how well it embodies the trait via a telling activity",
        "match_lib": "embodies the trait via a telling activity",
        "axis2": "10=fresh/telling activity, 0=generic or on-the-nose",
        "accept": "it must show an activity that EMBODIES the trait (a person of that quality doing the thing), read clearly, and not be a tired cliché",
    },
    "relational": {   # one SIDE of a dialectical pair — scored as a clear, striking depiction of that side
        "noun": "side",
        "judge": "Judge the FRAME for how clearly and strikingly it DEPICTS THIS SIDE of the juxtaposition.",
        "match": "how clearly/strikingly it depicts this side",
        "match_lib": "depicts this side",
        "axis2": "10=striking/cinematic, 0=weak or generic",
        "accept": "it must clearly and strikingly depict this side of the pair and read at a glance",
    },
    "scale": {   # the tangible REFERENT a big number counts up over (a stadium crowd, a city grid, grains of sand)
        "noun": "referent",
        "judge": "Judge the FRAME as a TANGIBLE REFERENT for a big NUMBER — a countable mass, a vast space, "
                 "or a human-scale object that makes the quantity graspable. It must have a calm, uncluttered "
                 "area a large count-up number can sit over legibly.",
        "match": "how well it makes a big quantity tangible/graspable",
        "match_lib": "makes a big quantity tangible/graspable",
        "axis2": "10=clean, has room for a big number overlay, 0=busy/cluttered",
        "accept": "it must give the number a tangible sense of scale AND have calm negative space for a large "
                  "count-up overlay to read clearly",
    },
    "literal": {   # plain keyword search — the frame should literally SHOW the subject (no bridge)
        "noun": "subject",
        "judge": "Judge whether the FRAME literally and clearly SHOWS the subject described in the line "
                 "(the actual thing named), as a straightforward depiction.",
        "match": "how clearly it literally shows the described subject",
        "match_lib": "literally shows the described subject",
        "axis2": "10=clear, direct depiction, 0=only tangential",
        "accept": "it must clearly and literally show the subject named in the line, in good quality, "
                  "free of watermarks/overlaid text",
    },
    "knowledge": {   # the SPECIFIC real, era-correct asset the model names from its own knowledge
        "noun": "subject",
        "judge": "Judge the FRAME as a faithful, high-quality depiction of the SPECIFIC named subject "
                 "(a particular artwork / artifact / place). Reward the real thing, cleanly shown.",
        "match": "how well it IS the specific named subject, clearly and cleanly shown",
        "match_lib": "is the specific named subject, cleanly shown",
        "axis2": "10=the genuine work/subject in good quality, 0=generic or wrong subject",
        "accept": "it must actually be the specific named subject (right work/artifact/place), be good "
                  "quality, and be free of watermarks/overlaid text",
    },
}


_SCALE_BRIDGE_SYS = (
    "You are a data-driven video-essay editor (in the vein of Vox / Neil Halloran) who makes a big ABSTRACT "
    "NUMBER hit home by counting it up over a TANGIBLE REFERENT — footage whose scale makes the quantity "
    "graspable (a packed stadium, a city grid from above, coins stacking, grains of sand). Reply STRICT JSON.")


def _scale_bridge_prompt(line: str, period: str, locale: str, literalness: float) -> str:
    ctx = ""
    if period or locale:
        ctx = (f"STORY PERIOD: {period or 'unspecified'}\nSTORY LOCALE: {locale or 'unspecified'}\n"
               "CRUCIAL: the referent footage must be period/locale-plausible or TIMELESS. Timeless referents "
               "are natural/elemental: grains of sand, drops of the sea, stars in the night sky, blades of "
               "grass, a swarm, falling leaves, a vast mountain range. For man-made mass, use only "
               "period-plausible imagery (an army of soldiers, a harbor of wooden ships, a marching column). "
               "NEVER pick modern-scale clichés (packed stadium, parking lot, city skyline, freeway) unless "
               "the period is explicitly modern.\n")
    return (f'LINE: "{line}"\n{ctx}'
            "Find the one QUANTITY in this line worth dramatizing (a count, size, duration, sum, distance). "
            "If the line only implies it ('a vast fleet', 'countless dead'), DERIVE a defensible round number. "
            "Then choose a TANGIBLE REFERENT whose footage makes that number feel real, and give concrete "
            "visual SEARCH PHRASES of that referent. Prefer a referent with calm negative space for the number.\n"
            'Return JSON: {"quantity": {"value": <number, digits only, no commas>, '
            '"prefix": "<e.g. $ or empty>", "suffix": "<e.g. B, %, years, or empty>", '
            '"caption": "<what the number counts, <=6 words>", "display": "<human-readable, e.g. 40,320>"}, '
            '"referent": {"label": "<the tangible referent, 2-4 words>", '
            '"visual_metaphors": ["4-6 SHORT search phrases of the referent footage in action"]}, '
            '"why": "<why this referent makes the number tangible, 1 sentence>", '
            '"avoid_literal": ["the literal subject we should NOT just show"]}')


_RELATIONAL_BRIDGE_SYS = (
    "You are a montage editor in the tradition of Eisenstein/Kuleshov — you make meaning by COLLIDING two "
    "shots: shot A + shot B create a third idea neither holds alone. Reply STRICT JSON.")


def _relational_bridge_prompt(line: str, period: str, locale: str, literalness: float) -> str:
    ctx = ""
    if period or locale:
        ctx = (f"STORY PERIOD: {period or 'unspecified'}\nSTORY LOCALE: {locale or 'unspecified'}\n"
               "Keep both sides' imagery period/locale-plausible.\n")
    return (f'LINE: "{line}"\n{ctx}'
            "Find the DIALECTICAL PAIR: two contrasting/opposing elements whose juxtaposition creates a THIRD "
            "meaning (the synthesis). For EACH side give a short label + concrete visual SEARCH PHRASES.\n"
            'Return JSON: {"synthesis": "the third idea the collision creates (1 sentence)", '
            '"sides": [{"label": "side A (2-4 words)", "visual_metaphors": ["3-5 search phrases for side A"]}, '
            '{"label": "side B (2-4 words)", "visual_metaphors": ["3-5 search phrases for side B"]}]}')


_TRAIT_BRIDGE_SYS = (
    "You are a video-essay editor who conveys a PERSON'S QUALITY through an EMBODYING ACTIVITY — the "
    "archetypal thing someone of that trait does (discipline→pre-dawn training, patience→fly-fishing / "
    "watchmaking, precision→surgery / calligraphy, obsession→repeated practice). Reply STRICT JSON.")


def _trait_bridge_prompt(line: str, period: str, locale: str, literalness: float) -> str:
    ctx = ""
    if period or locale:
        ctx = (f"STORY PERIOD: {period or 'unspecified'}\nSTORY LOCALE: {locale or 'unspecified'}\n"
               "Keep the activities period/locale-plausible.\n")
    return (f'LINE: "{line}"\n{ctx}'
            "Identify the character TRAIT/quality in this line. Choose 1-3 archetypal ACTIVITIES a person of "
            "that trait would do (that visibly embody it). Give concrete visual SEARCH PHRASES of those activities.\n"
            'Return JSON: {"trait": "the quality (2-4 words)", '
            '"activities": [{"activity": "e.g. pre-dawn training", "why": "why it embodies the trait"}], '
            '"visual_metaphors": ["5-7 SHORT search phrases of the embodying activity in action"], '
            '"avoid_literal": ["the literal person/label we should NOT just show"]}')


_IRONIC_BRIDGE_SYS = (
    "You are a video-essay editor in the vein of Adam Curtis — you cut IRONIC COUNTERPOINT: footage that "
    "CONTRADICTS the narration to expose the gap between what is said and what is real. Reply STRICT JSON.")


def _ironic_bridge_prompt(line: str, period: str, locale: str, literalness: float) -> str:
    ctx = ""
    if period or locale:
        ctx = (f"STORY PERIOD: {period or 'unspecified'}\nSTORY LOCALE: {locale or 'unspecified'}\n"
               "Keep the counterpoint imagery period/locale-plausible or timeless.\n")
    return (f'LINE (the narration / surface claim): "{line}"\n{ctx}'
            "Identify the line's SURFACE MESSAGE and the IRONIC TRUTH that undercuts it (the cost, the "
            "opposite, the hollow reality). Give concrete visual SEARCH PHRASES of footage that CONTRADICTS "
            "the line for pointed irony — NOT footage that illustrates it.\n"
            'Return JSON: {"surface": "what the line claims (few words)", '
            '"irony": "the undercutting truth (1 sentence)", '
            '"visual_metaphors": ["5-7 SHORT search phrases of the CONTRADICTING imagery"], '
            '"avoid_literal": ["the on-message imagery that would just illustrate the line"]}')


def _conceptual_bridge_prompt(line: str, period: str, locale: str, literalness: float) -> str:
    ctx = ""
    if period or locale:
        ctx = (f"STORY PERIOD: {period or 'unspecified'}\nSTORY LOCALE: {locale or 'unspecified'}\n"
               "Prefer carrier domains that are period/locale-plausible or timeless; avoid anachronistic "
               "or wrong-culture ones.\n")
    fresh = "Prefer FRESH, non-obvious domains." if literalness <= 0.5 else "Familiar, clear domains are fine."
    return (f'LINE: "{line}"\n{ctx}{fresh}\n'
            "Identify the abstract CONCEPT in this line and its underlying MECHANIC (how it works, structurally). "
            "Choose 1-3 concrete CARRIER DOMAINS whose mechanic is ISOMORPHIC (same structure), vivid and filmable. "
            "Give concrete visual SEARCH PHRASES of those domains IN ACTION.\n"
            'Return JSON: {"concept": "the abstract idea (2-5 words)", '
            '"mechanic": "the structural mechanic (1 sentence)", '
            '"domains": [{"domain": "e.g. chess", "why": "why its mechanic is isomorphic"}], '
            '"visual_metaphors": ["5-7 SHORT concrete search phrases of the carrier domain(s) in action, e.g. '
            "'gloved hand moving a chess knight', 'dominoes toppling in a chain'\"], "
            '"avoid_literal": ["the line\'s literal subject we should NOT show"]}')


def _vision_prompt(line: str, goal: str, period: str, locale: str, operator: str = "tonal") -> str:
    op = _OP.get(operator, _OP["tonal"])
    base = (f'A still frame from a stock video, considered as b-roll under the line:\n'
            f'"{line}"\nTarget {op["noun"]}: {goal}\n')
    if period or locale:
        base += (f"STORY PERIOD: {period or 'unspecified'}\nSTORY LOCALE: {locale or 'unspecified'}\n"
                 "CRUCIAL: pure landscape/nature/natural-elements and pure abstract texture are UNIVERSAL — "
                 "they fit ANY era or place. Only man-made objects, people, clothing, architecture, "
                 "text/signage, technology or vehicles carry a period or culture.\n")
    return base + (
        f"{op['judge']}\n"
        "Reply STRICT JSON only: {"
        f'"mood": <0-10 {op["match"]}>, '
        f'"nonliteral": <0-10, {op["axis2"]}>, '
        '"universal": <true|false — true if pure nature/natural-element/abstract with NO era- or '
        'culture-specific man-made content>, '
        '"period_ok": <0-10 fit with the story period; 10 if universal or no period given>, '
        '"locale_ok": <0-10 fit with the story locale; 10 if universal or no locale given>, '
        '"flags": "<disqualifiers: anachronism/wrong-locale e.g. \'modern car\'; OR \'watermark\' / '
        '\'heavy overlaid text\' / \'stock-photo graphic\' for unusable stills; empty if none>", '
        '"why": "<=12 words"}')


def _accept_prompt(line: str, goal: str, cands: List[dict], operator: str = "tonal") -> str:
    op = _OP.get(operator, _OP["tonal"])
    items = "\n".join(
        f'[{i}] mood {c.get("mood")}/10, {"universal nature/abstract" if c.get("universal") else "man-made"} — {c.get("why")}'
        for i, c in enumerate(cands))
    return (f'LINE: "{line}"\nTARGET {op["noun"].upper()}: {goal}\n\n'
            "These candidate shots already passed a period/locale screen. Each description is what the frame "
            f"ACTUALLY shows (from a vision model):\n{items}\n\n"
            f"Choose ONLY shots a professional editor would genuinely cut under this line — {op['accept']}. "
            "Prefer varied options (avoid near-duplicates). If NONE clear that bar, pick nothing — abstaining is correct.\n"
            'JSON: {"pick": [<indices best-first, up to 5, ONLY genuine uses>], '
            '"unmatched_reason": "<one line: why nothing fit — only if pick is empty>"}')


_SCORE_SYS = (
    "You are a documentary editor grading candidate b-roll shots (described by their CONTENT) for how well "
    "they work as b-roll under a line. Reply STRICT JSON.")


def _library_score_prompt(line: str, goal: str, period: str, locale: str, cands: List[dict],
                          operator: str = "tonal") -> str:
    op = _OP.get(operator, _OP["tonal"])
    ctx = ""
    if period or locale:
        ctx = (f"STORY PERIOD: {period or 'unspecified'}\nSTORY LOCALE: {locale or 'unspecified'}\n"
               "Pure landscape/nature/abstract is UNIVERSAL (fits any era/place); only man-made content "
               "carries a period or culture.\n")
    items = "\n".join(f'[{i}] {c.get("desc", "")[:180]}' for i, c in enumerate(cands))
    return (f'LINE: "{line}"\nTARGET {op["noun"].upper()}: {goal}\n{ctx}\n'
            f"CANDIDATE SHOTS (by their content description):\n{items}\n\n"
            "Score EACH. JSON: {\"scores\": [{\"i\": <index>, "
            f'"mood": <0-10 {op["match_lib"]}>, "nonliteral": <0-10, {op["axis2"]}>, '
            '"universal": <true|false>, "period_ok": <0-10; 10 if universal or no period given>, '
            '"locale_ok": <0-10; 10 if universal or no locale given>, '
            '"flags": "<anachronism/wrong-locale markers; empty if none>", "why": "<=12 words"}]}')


def available_video_providers(config) -> List[dict]:
    """List the stock-VIDEO providers currently available (for the UI pool control)."""
    from .image_search import ImageSearchClient, _DEFER_LAST
    src = config.image_sources
    client = ImageSearchClient(pexels_api_key=src.pexels_api_key, pixabay_api_key=src.pixabay_api_key,
                               smithsonian_api_key=src.smithsonian_api_key, keys=src.provider_keys())
    keyless = {"archive", "nasa_video", "coverr_video"}
    out = []
    for name in client.video_providers():
        out.append({"name": name, "keyless": name in keyless,
                    "deferred": name in _DEFER_LAST, "default": True})
    return out


class EvokeBrollSearch:
    """Evocative b-roll searcher over stock video (cheap tiers) OR the indexed library."""

    def __init__(self, config=None, progress: Optional[Callable[[float, str], None]] = None):
        self.config = config or load_config()
        self.llm = create_text_llm(self.config)
        self.vision = create_vision_provider(_vision_config(self.config))
        src = self.config.image_sources
        self.stock = ImageSearchClient(
            pexels_api_key=src.pexels_api_key, pixabay_api_key=src.pixabay_api_key,
            smithsonian_api_key=src.smithsonian_api_key, keys=src.provider_keys())
        self._dl = ImageScorer()                      # reuse its browser-headed _download_image
        self._progress = progress or (lambda f, m: None)
        self._sem = None                              # created lazily inside search() (running loop)
        self._vs = None                               # VectorSearch (library mode), lazy
        self._index = None

    # ---- per-candidate vision scoring (fit + period/locale gate) ----
    async def _score(self, cand: dict, goal: str, line: str, period: str, locale: str, operator: str = "tonal") -> dict:
        from PIL import Image
        url = cand.get("local") or cand.get("poster")     # generated stills have a local path
        data = await asyncio.to_thread(self._dl._download_image, url) if url else None
        if not data:
            return {}
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            Image.open(io.BytesIO(data)).convert("RGB").save(tmp, "JPEG", quality=80)
            async with self._sem:
                j = _extract_json(await self.vision.describe_image(Path(tmp), _vision_prompt(line, goal, period, locale, operator)))
            return {"mood": j.get("mood"), "nonliteral": j.get("nonliteral"),
                    "universal": bool(j.get("universal")), "period_ok": j.get("period_ok"),
                    "locale_ok": j.get("locale_ok"), "flags": j.get("flags", ""), "why": j.get("why", "")}
        except Exception:
            return {}
        finally:
            if tmp and os.path.exists(tmp):
                try: os.unlink(tmp)
                except Exception: pass

    @staticmethod
    def _anachronistic(c: dict, gated: bool) -> bool:
        flags = (c.get("flags") or "").lower()
        # unusable stills (watermark / overlaid text / stock-photo graphic) are always out
        if any(w in flags for w in ("watermark", "overlaid text", "heavy text", "text overlay", "stock-photo graphic")):
            return True
        if not gated or c.get("universal"):
            return False
        p, l = c.get("period_ok"), c.get("locale_ok")
        return (p is not None and p < 5) or (l is not None and l < 5)

    async def _select(self, line, metaphors, goal, operator, *, mode, period, locale, sources, media,
                      project, gen_style, per_metaphor, gated, max_picks=5) -> dict:
        """One retrieve → score → period/locale gate → listwise-accept → motion pass.
        Returns {picks, considered, pool, kept, filtered, reason}. Shared by the normal path and
        each side of the relational operator."""
        from .motion_select import recommend_motions
        if not metaphors:
            return {"picks": [], "considered": [], "pool": 0, "kept": 0, "filtered": 0, "reason": "no metaphors"}
        if mode == "library":
            cands = await self._retrieve_library(metaphors, per_metaphor, project)
        elif mode == "generate":
            cands = await self._retrieve_generate(metaphors, gen_style)
        else:
            cands = await self._retrieve_stock(metaphors, per_metaphor, sources, media)
        pool_n = len(cands)
        if not cands:
            return {"picks": [], "considered": [], "pool": 0, "kept": 0, "filtered": 0, "reason": "no footage found"}

        if mode == "library":
            await self._score_library(cands, goal, line, period, locale, operator)
        else:
            scores = await asyncio.gather(*[self._score(c, goal, line, period, locale, operator) for c in cands])
            for c, s in zip(cands, scores):
                c.update(s)
        scored = [c for c in cands if c.get("mood") is not None]
        kept = [c for c in scored if not self._anachronistic(c, gated)]
        filtered = [c for c in scored if self._anachronistic(c, gated)]
        for c in filtered:
            c["reject"] = f"gated: {c.get('flags') or 'period/locale clash'}"

        picked, chosen, reason = [], set(), ""
        if kept:
            kept.sort(key=lambda c: -((c.get("mood") or 0) + (c.get("nonliteral") or 0) * 0.3
                                      + (0.5 if c.get("universal") else 0)))
            res = _extract_json(await self.llm.generate(_accept_prompt(line, goal, kept, operator), _LISTWISE_SYS))
            order = [i for i in res.get("pick", []) if 0 <= i < len(kept)][:max_picks]
            chosen = set(order)
            if order:
                picked = [kept[i] for i in order]
            else:
                reason = res.get("unmatched_reason") or "nothing cleared the use-bar"
            for i, c in enumerate(kept):
                if i not in chosen:
                    c["reject"] = "below use-bar"
        else:
            reason = "no period/locale-safe footage survived"

        if picked:
            await recommend_motions(self.llm, line, goal, operator, picked)
        considered = filtered + [c for i, c in enumerate(kept) if i not in chosen]
        return {"picks": picked, "considered": considered, "pool": pool_n,
                "kept": len(kept), "filtered": len(filtered), "reason": reason}

    async def search(self, line: str, *, operator: str = "tonal", mode: str = "stock",
                     period: str = "", locale: str = "", literalness: float = 0.25,
                     mood: Optional[str] = None, sources: Optional[List[str]] = None,
                     project: Optional[str] = None, media: Optional[List[str]] = None,
                     gen_style: str = "Fooocus Cinematic", beat: Optional[int] = None,
                     max_metaphors: int = 5, per_metaphor: int = 3) -> dict:
        line = (line or "").strip()
        if not line:
            raise ValueError("line is required")
        # L3 — agentic auto-pairing: a planner picks the operator from whole-script context,
        # runs it, and retries with a fallback if it comes back UNMATCHED.
        if operator == "auto":
            return await self._auto_pair(
                line, mode=mode, period=period, locale=locale, literalness=literalness, mood=mood,
                sources=sources, project=project, media=media, gen_style=gen_style, beat=beat,
                max_metaphors=max_metaphors, per_metaphor=per_metaphor)
        operator = operator if operator in _OP else "tonal"
        mode = mode if mode in ("stock", "library", "generate") else "stock"
        media = [m for m in (media or ["video", "image"]) if m in ("video", "image")] or ["video", "image"]
        self._sem = asyncio.Semaphore(4)              # bind to the running loop

        # ScriptContext: when a project is given, load whole-script context so the bridge (and the
        # knowledge operator) reason with the full script, not one line in isolation.
        ctx, cblock = None, ""
        if project:
            try:
                from .script_context import ScriptContext
                ctx = ScriptContext.load(project)
                if ctx.beats:
                    if beat is None:                      # auto-locate the beat from the line (for /scenes
                        b = ctx.find_beat(line)           # super-search, which passes narration but no index)
                        if b is not None:
                            beat = b.idx
                    if beat is not None:
                        cblock = ctx.beat_context(beat)
            except Exception:
                ctx = None
        pre = (cblock + "\n\n") if cblock else ""     # prepended to every bridge prompt
        gated = bool(period or locale)

        # 1. bridge (operator-specific): produce a `goal` string + concrete visual search phrases
        self._progress(0.08, "Bridging…")
        if operator == "relational":
            br = _extract_json(await self.llm.generate(
                pre + _relational_bridge_prompt(line, period, locale, literalness), _RELATIONAL_BRIDGE_SYS))
            goal = br.get("synthesis", "")
            metaphors = [m for s in br.get("sides", []) for m in s.get("visual_metaphors", []) if m][:8]
        elif operator == "conceptual":
            br = _extract_json(await self.llm.generate(
                pre + _conceptual_bridge_prompt(line, period, locale, literalness), _CONCEPTUAL_BRIDGE_SYS))
            doms = ", ".join(d.get("domain", "") for d in br.get("domains", []) if d.get("domain"))
            goal = (br.get("concept", "") + (f" — via {doms}" if doms else "")).strip()
        elif operator == "ironic":
            br = _extract_json(await self.llm.generate(
                pre + _ironic_bridge_prompt(line, period, locale, literalness), _IRONIC_BRIDGE_SYS))
            goal = (br.get("irony", "") or br.get("surface", "")).strip()
        elif operator == "trait":
            br = _extract_json(await self.llm.generate(
                pre + _trait_bridge_prompt(line, period, locale, literalness), _TRAIT_BRIDGE_SYS))
            acts = ", ".join(a.get("activity", "") for a in br.get("activities", []) if a.get("activity"))
            goal = (br.get("trait", "") + (f" — via {acts}" if acts else "")).strip()
        elif operator == "scale":
            br = _extract_json(await self.llm.generate(
                pre + _scale_bridge_prompt(line, period, locale, literalness), _SCALE_BRIDGE_SYS))
            ref = br.get("referent", {}) or {}
            goal = (ref.get("label", "") or "").strip()
            metaphors = [m for m in ref.get("visual_metaphors", []) if m][:max_metaphors]
        elif operator == "literal":
            # plain keyword search — no LLM bridge; the line itself is the query (+ a keyword variant)
            br = {"literal": line}
            goal = line[:80]
            kw = " ".join(w for w in re.findall(r"[A-Za-z0-9']+", line) if len(w) > 3)[:80]
            metaphors = [line] + ([kw] if kw and kw.lower() != line.lower() else [])
            metaphors = metaphors[:max_metaphors]
        elif operator == "knowledge":
            if ctx is None:
                self._progress(1.0, "UNMATCHED")
                return {"status": "UNMATCHED", "operator": operator, "mode": mode, "line": line,
                        "emotion": "", "goal": "", "goal_label": _OP[operator]["noun"], "bridge": {},
                        "metaphors": [], "picks": [], "considered": [],
                        "reason": "the knowledge operator needs a project context — pick a project",
                        "counts": {"pool": 0, "kept": 0, "filtered": 0}}
            from .knowledge_query import expand_queries
            kq = await asyncio.to_thread(expand_queries, ctx, (beat if beat is not None else 0),
                                         llm=self.llm, kind="any", n=max_metaphors)
            br = kq.to_dict()
            goal = f"{ctx.subject or 'the topic'} — specific real assets"
            metaphors = kq.all_queries()[:max_metaphors]
            if not period:
                period = kq.period
            if not locale:
                locale = kq.locale
            gated = bool(period or locale)
        else:
            br = _extract_json(await self.llm.generate(
                pre + _bridge_prompt(line, period, locale, literalness, mood), _BRIDGE_SYS))
            goal = br.get("target_emotion", "")
        if operator not in ("relational", "scale", "knowledge", "literal"):
            metaphors = [m for m in br.get("visual_metaphors", []) if m][:max_metaphors]

        _kw = dict(mode=mode, period=period, locale=locale, sources=sources, media=media,
                   project=project, gen_style=gen_style, per_metaphor=per_metaphor, gated=gated)

        # --- relational: two sub-selections (side A + side B) that collide ---
        if operator == "relational":
            sides = br.get("sides", [])[:2]
            if len(sides) < 2:
                self._progress(1.0, "UNMATCHED")
                return {"status": "UNMATCHED", "operator": operator, "mode": mode, "line": line,
                        "emotion": goal, "goal": goal, "goal_label": "synthesis", "synthesis": goal, "bridge": br,
                        "metaphors": metaphors, "picks": [], "considered": [], "sides": [],
                        "reason": "could not find a dialectical pair", "counts": {"pool": 0, "kept": 0, "filtered": 0}}
            self._progress(0.25, f"Side A: {sides[0].get('label', '')}…")
            a = await self._select(line, [m for m in sides[0].get("visual_metaphors", []) if m][:5],
                                   sides[0].get("label", ""), operator, max_picks=2, **_kw)
            self._progress(0.6, f"Side B: {sides[1].get('label', '')}…")
            b = await self._select(line, [m for m in sides[1].get("visual_metaphors", []) if m][:5],
                                   sides[1].get("label", ""), operator, max_picks=2, **_kw)
            status = "MATCHED" if (a["picks"] and b["picks"]) else "UNMATCHED"
            reason = "" if status == "MATCHED" else f"couldn't complete the pair (side A: {len(a['picks'])}, side B: {len(b['picks'])})"
            self._progress(1.0, status)
            return {"status": status, "reason": reason, "operator": operator, "mode": mode, "line": line,
                    "emotion": goal, "goal": goal, "goal_label": "synthesis", "synthesis": goal, "bridge": br,
                    "presentation": "split-screen",
                    "sides": [{"label": sides[0].get("label", ""), "picks": a["picks"], "considered": a["considered"]},
                              {"label": sides[1].get("label", ""), "picks": b["picks"], "considered": b["considered"]}],
                    "metaphors": metaphors, "picks": a["picks"] + b["picks"],
                    "considered": a["considered"] + b["considered"],
                    "counts": {"pool": a["pool"] + b["pool"], "kept": a["kept"] + b["kept"], "filtered": a["filtered"] + b["filtered"]}}

        # --- scale: validate we actually have a number to count up (else abstain) ---
        quantity = None
        if operator == "scale":
            q = br.get("quantity", {}) or {}
            try:
                val = float(q.get("value"))
            except (TypeError, ValueError):
                val = None
            if val is None or not goal:
                self._progress(1.0, "UNMATCHED")
                return {"status": "UNMATCHED", "operator": operator, "mode": mode, "line": line,
                        "emotion": goal, "goal": goal, "goal_label": _OP[operator]["noun"], "bridge": br,
                        "metaphors": metaphors, "picks": [], "considered": [], "quantity": None,
                        "presentation": "stat-over",
                        "reason": "no quantifiable scale in the line",
                        "counts": {"pool": 0, "kept": 0, "filtered": 0}}
            decimals = 0 if val == int(val) else len(str(val).split(".")[-1])
            quantity = {"value": val, "prefix": q.get("prefix", "") or "", "suffix": q.get("suffix", "") or "",
                        "caption": q.get("caption", "") or "", "display": q.get("display", "") or "",
                        "decimals": min(decimals, 2)}

        # --- normal operators: one selection ---
        self._progress(0.3, f"Retrieving + scoring {mode} b-roll…")
        sel = await self._select(line, metaphors, goal, operator, max_picks=5, **_kw)
        status = "MATCHED" if sel["picks"] else "UNMATCHED"
        reason = "" if sel["picks"] else sel["reason"]
        if sel["pool"] == 0:
            reason = {"library": "no library segments found", "generate": "generation produced nothing"}.get(mode, "no stock footage found") + " for these metaphors"
        self._progress(1.0, status)
        out = {"status": status, "reason": reason, "operator": operator, "mode": mode, "line": line,
               "emotion": goal, "goal": goal, "goal_label": _OP[operator]["noun"], "bridge": br,
               "metaphors": metaphors, "picks": sel["picks"], "considered": sel["considered"],
               "counts": {"pool": sel["pool"], "kept": sel["kept"], "filtered": sel["filtered"]}}
        if operator == "scale":
            out["quantity"] = quantity
            out["presentation"] = "stat-over"
        return out

    # ---- L3: agentic auto-pairing (planner → run → retry) ----
    async def _auto_plan(self, ctx, beat: int, line: str) -> dict:
        """LLM planner: given whole-script context, pick the pairing operator (+ a fallback)."""
        bc = ctx.beat_context(beat) if (ctx and ctx.beats) else ""
        prompt = (
            f"{ctx.brief(max_chars=1400)}\n\n{bc}\n\n"
            f'THIS BEAT LINE: "{line}"\n\n'
            "Decide the best b-roll PAIRING approach for THIS beat, plus a fallback:\n"
            "- literal: the beat names a concrete, common subject best shown plainly (a keyword search).\n"
            "- knowledge: the beat names/implies a SPECIFIC real thing (a titled artwork, an artifact, "
            "a place, a named person/event) — source the actual thing.\n"
            "- tonal: mood/atmosphere with no concrete subject — evocative footage that carries the feeling.\n"
            "- conceptual: an abstract idea whose mechanic maps to a filmable domain (strategy→chess).\n"
            "- ironic: the image should CONTRADICT the words, for critique/irony.\n"
            "- trait: a person's quality shown via an embodying activity.\n"
            "- relational: the beat is built on a CONTRAST/pair of two things (rendered split-screen).\n"
            "- scale: the beat hinges on a big NUMBER worth dramatizing (count-up).\n"
            'Reply STRICT JSON: {"primary": "<operator>", "fallback": "<operator>", "why": "<=20 words"}')
        sys = ("You are the lead editor of a video essay deciding HOW to source b-roll for one beat. "
               "You know the whole script. Pick the approach that will land best. Reply STRICT JSON.")
        try:
            j = _extract_json(await self.llm.generate(prompt, sys))
        except Exception:
            j = {}
        if not isinstance(j, dict):
            j = {}
        prim = j.get("primary") if j.get("primary") in _OP else "knowledge"
        fb = j.get("fallback") if j.get("fallback") in _OP else "tonal"
        if fb == prim:
            fb = "tonal" if prim != "tonal" else "conceptual"
        return {"primary": prim, "fallback": fb, "why": (j.get("why") or "")[:160]}

    async def _auto_judge(self, ctx, beat: int, line: str, operator: str, picks: list) -> dict:
        """Meta-judge: does this MATCHED set genuinely serve THIS beat (subject/mood/rhythm), or is
        it accepted-but-weak filler? Returns {score 0-10, verdict accept|reject, why}."""
        if not picks:
            return {"score": 0, "verdict": "reject", "why": "no picks"}
        items = "\n".join(
            f"[{i}] {p.get('kind')} from {p.get('source')} — {(p.get('why') or '')[:90]}"
            for i, p in enumerate(picks[:5]))
        bc = ctx.beat_context(beat) if (ctx and ctx.beats) else ""
        prompt = (f"{bc}\n\nBEAT LINE: \"{line}\"\nPAIRING APPROACH USED: {operator}\n\n"
                  f"The pipeline accepted these b-roll picks:\n{items}\n\n"
                  "As a demanding lead editor, judge whether these are a GENUINELY STRONG pairing for "
                  "THIS beat — right subject/mood, and right for the beat's pacing (drive vs breathe) — "
                  "not generic filler that merely passed a gate. Score 0-10 and accept or reject.\n"
                  'STRICT JSON: {"score": <0-10>, "verdict": "accept|reject", "why": "<=15 words"}')
        sys = "You are a demanding lead editor doing a final quality check on b-roll picks. Reply STRICT JSON."
        try:
            j = _extract_json(await self.llm.generate(prompt, sys))
        except Exception:
            j = {}
        if not isinstance(j, dict):
            j = {}
        try:
            score = max(0.0, min(10.0, float(j.get("score"))))
        except (TypeError, ValueError):
            score = 6.0
        verdict = "reject" if (str(j.get("verdict")).lower() == "reject" or score < 5) else "accept"
        return {"score": round(score, 1), "verdict": verdict, "why": (j.get("why") or "")[:120]}

    async def _auto_pair(self, line: str, *, mode, period, locale, literalness, mood, sources,
                         project, media, gen_style, beat, max_metaphors, per_metaphor) -> dict:
        """Pick an operator from context, run it, META-JUDGE the picks, and fall back if the result
        is UNMATCHED *or* judged weak. Returns the accepted result, else the highest-judged one."""
        ctx = None
        if project:
            try:
                from .script_context import ScriptContext
                ctx = ScriptContext.load(project)
            except Exception:
                ctx = None
        if ctx is None:
            self._progress(1.0, "UNMATCHED")
            return {"status": "UNMATCHED", "operator": "auto", "mode": mode, "line": line,
                    "emotion": "", "goal": "", "goal_label": "auto", "bridge": {}, "metaphors": [],
                    "picks": [], "considered": [], "reason": "auto needs a project context — pick a project",
                    "counts": {"pool": 0, "kept": 0, "filtered": 0}}

        self._progress(0.04, "Planning the pairing approach…")
        plan = await self._auto_plan(ctx, beat if beat is not None else 0, line)
        order, tried, matched = [plan["primary"], plan["fallback"]], [], []
        for i, op in enumerate(order):
            self._progress(0.08 + 0.35 * i, f"Trying {op}…")
            res = await self.search(line, operator=op, mode=mode, period=period, locale=locale,
                                    literalness=literalness, mood=mood, sources=sources, project=project,
                                    media=media, gen_style=gen_style, beat=beat,
                                    max_metaphors=max_metaphors, per_metaphor=per_metaphor)
            step = {"operator": op, "status": res.get("status"), "picks": len(res.get("picks") or [])}
            if res.get("status") == "MATCHED":
                self._progress(0.24 + 0.35 * i, f"Judging {op} picks…")
                jm = await self._auto_judge(ctx, beat if beat is not None else 0, line, op, res.get("picks") or [])
                res["auto_judgment"] = jm
                step["judge"] = jm["score"]
                step["verdict"] = jm["verdict"]
                matched.append((op, res, jm))
                tried.append(step)
                if jm["verdict"] == "accept":
                    res["auto"] = {"chosen": op, "primary": plan["primary"], "fallback": plan["fallback"],
                                   "why": plan["why"], "tried": tried, "judge": jm}
                    self._progress(1.0, f"MATCHED via {op} (judge {jm['score']})")
                    return res
                continue                          # judged weak → try the fallback
            tried.append(step)

        # none accepted: return the highest-judged MATCHED result (best effort), else UNMATCHED
        if matched:
            op, res, jm = max(matched, key=lambda x: x[2]["score"])
            res["auto"] = {"chosen": op, "primary": plan["primary"], "fallback": plan["fallback"],
                           "why": plan["why"], "tried": tried, "judge": jm,
                           "note": "judge accepted none; returning the strongest"}
            res["operator"] = "auto"
            self._progress(1.0, f"MATCHED via {op} (best-effort, judge {jm['score']})")
            return res
        last = {"status": "UNMATCHED", "operator": "auto", "mode": mode, "line": line,
                "emotion": "", "goal": "", "goal_label": "auto", "bridge": {}, "metaphors": [],
                "picks": [], "considered": [],
                "reason": f"neither {plan['primary']} nor {plan['fallback']} found a fit",
                "counts": {"pool": 0, "kept": 0, "filtered": 0},
                "auto": {"chosen": None, "primary": plan["primary"], "fallback": plan["fallback"],
                         "why": plan["why"], "tried": tried}}
        self._progress(1.0, "UNMATCHED")
        return last

    # ---- retrieval: stock (real footage) or library (indexed segments) ----
    async def _retrieve_stock(self, metaphors, per_metaphor, sources, media=("video", "image")):
        pool: dict = {}
        for m in metaphors:
            for mt in media:
                # video-provider selection applies to video only; images use the image fan-out
                srcs = (sources or None) if mt == "video" else None
                hits = await asyncio.to_thread(self.stock.search_assets, m, mt, srcs, per_metaphor)
                for h in hits:
                    if h.url in pool:
                        continue
                    if mt == "image":
                        pool[h.url] = {"kind": "image", "url": h.url, "source": h.source,
                                       "duration": None, "poster": h.thumbnail_url or h.url, "metaphor": m}
                    else:
                        pool[h.url] = {"kind": "stock", "url": h.url, "source": h.source,
                                       "duration": round(h.duration) if h.duration else None,
                                       "poster": h.preview_image_url or h.thumbnail_url, "metaphor": m}
        return list(pool.values())[:12]

    async def _retrieve_library(self, metaphors, per_metaphor, project):
        vs = self._vector()
        pid = self._index.resolve_project(project) if (project and self._index) else None
        pool: dict = {}
        for m in metaphors:
            hits = await asyncio.to_thread(vs.search, m, per_metaphor, "segments", pid)
            for r in hits:
                key = (r.video_path, round(r.timestamp_start, 1))
                if key in pool:
                    continue
                from urllib.parse import quote
                start, end = int(r.timestamp_start), int(r.timestamp_end or r.timestamp_start + 5)
                pool[key] = {"kind": "library", "source": "library",
                             "video_name": Path(r.video_path).name,
                             "url": f"/library/video/{quote(r.video_path, safe='')}#t={start},{end}",
                             "duration": (end - start) or None, "ts_start": start, "ts_end": end,
                             "desc": r.description or "", "metaphor": m}
        return list(pool.values())[:10]

    # ---- generation: Krea-2 (ComfyUI) makes a still per metaphor when found footage misses ----
    async def _retrieve_generate(self, metaphors, style):
        from nolan.workflow_registry import get_registry
        GEN_DIR.mkdir(parents=True, exist_ok=True)
        client, _ = get_registry().build_client("krea2-style-select", self.config, style=f",{style}")
        cands = []
        for m in metaphors[:5]:
            out = GEN_DIR / f"{hashlib.md5((m + '|' + style).encode()).hexdigest()[:12]}.png"
            try:
                if not out.exists():
                    await client.generate(f"{m}, cinematic, highly detailed", out, timeout=200)
            except Exception:
                continue
            cands.append({"kind": "image", "source": "krea2 (generated)",
                          "url": f"{GEN_URL}/{out.name}", "poster": f"{GEN_URL}/{out.name}",
                          "local": str(out.resolve()), "duration": None, "metaphor": m})
        return cands

    # ---- library scoring: one batch text pass over the segments' descriptions ----
    async def _score_library(self, cands, goal, line, period, locale, operator="tonal"):
        try:
            j = _extract_json(await self.llm.generate(
                _library_score_prompt(line, goal, period, locale, cands, operator), _SCORE_SYS))
            by_i = {s.get("i"): s for s in j.get("scores", [])}
        except Exception:
            by_i = {}
        for i, c in enumerate(cands):
            s = by_i.get(i)
            if s:
                c.update({"mood": s.get("mood"), "nonliteral": s.get("nonliteral"),
                          "universal": bool(s.get("universal")), "period_ok": s.get("period_ok"),
                          "locale_ok": s.get("locale_ok"), "flags": s.get("flags", ""), "why": s.get("why", "")})

    def _vector(self):
        if self._vs is None:
            from .indexer import VideoIndex
            from .vector_search import VectorSearch
            db = Path(self.config.indexing.database).expanduser()
            self._index = VideoIndex(db)
            self._vs = VectorSearch(db.parent / "vectors", index=self._index)
        return self._vs
