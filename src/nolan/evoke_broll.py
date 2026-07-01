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
import io
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

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


def _vision_prompt(line: str, emotion: str, period: str, locale: str) -> str:
    base = (f'A still frame from a stock video, considered as EVOCATIVE b-roll under the line:\n'
            f'"{line}"\nTarget emotion: {emotion}\n')
    if period or locale:
        base += (f"STORY PERIOD: {period or 'unspecified'}\nSTORY LOCALE: {locale or 'unspecified'}\n"
                 "CRUCIAL: pure landscape/nature/natural-elements and pure abstract texture are UNIVERSAL — "
                 "they fit ANY era or place. Only man-made objects, people, clothing, architecture, "
                 "text/signage, technology or vehicles carry a period or culture.\n")
    return base + (
        "Judge the FRAME as mood b-roll (color, light, composition) — NOT literal illustration.\n"
        "Reply STRICT JSON only: {"
        '"mood": <0-10 how strongly its atmosphere EVOKES the emotion>, '
        '"nonliteral": <0-10, 10=oblique/evocative, 0=literally depicts the subject>, '
        '"universal": <true|false — true if pure nature/natural-element/abstract with NO era- or '
        'culture-specific man-made content>, '
        '"period_ok": <0-10 fit with the story period; 10 if universal or no period given>, '
        '"locale_ok": <0-10 fit with the story locale; 10 if universal or no locale given>, '
        '"flags": "<anachronism/wrong-locale markers e.g. \'modern car\',\'contemporary clothing\'; empty if none>", '
        '"why": "<=12 words"}')


def _accept_prompt(line: str, emotion: str, cands: List[dict]) -> str:
    items = "\n".join(
        f'[{i}] mood {c.get("mood")}/10, {"universal nature/abstract" if c.get("universal") else "man-made"} — {c.get("why")}'
        for i, c in enumerate(cands))
    return (f'LINE: "{line}"\nTARGET EMOTION: {emotion}\n\n'
            "These candidate shots already passed a period/locale screen. Each description is what the frame "
            f"ACTUALLY shows (from a vision model):\n{items}\n\n"
            "Choose ONLY shots a professional editor would genuinely cut under this line — the mood must be "
            "right, it must be evocative (not literal), and it must actually work on screen. Prefer varied "
            "evocations (avoid near-duplicates). If NONE clear that bar, pick nothing — abstaining is correct.\n"
            'JSON: {"pick": [<indices best-first, up to 5, ONLY genuine uses>], '
            '"unmatched_reason": "<one line: why nothing fit — only if pick is empty>"}')


class EvokeBrollSearch:
    """Stateless-ish evocative b-roll searcher over stock video (cheap tiers)."""

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

    # ---- per-candidate vision scoring (mood + period/locale gate) ----
    async def _score(self, cand: dict, emotion: str, line: str, period: str, locale: str) -> dict:
        from PIL import Image
        url = cand.get("poster")
        data = await asyncio.to_thread(self._dl._download_image, url) if url else None
        if not data:
            return {}
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            Image.open(io.BytesIO(data)).convert("RGB").save(tmp, "JPEG", quality=80)
            async with self._sem:
                j = _extract_json(await self.vision.describe_image(Path(tmp), _vision_prompt(line, emotion, period, locale)))
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
        if not gated or c.get("universal"):
            return False
        p, l = c.get("period_ok"), c.get("locale_ok")
        return (p is not None and p < 5) or (l is not None and l < 5)

    async def search(self, line: str, *, period: str = "", locale: str = "", literalness: float = 0.25,
                     mood: Optional[str] = None, max_metaphors: int = 5, per_metaphor: int = 3) -> dict:
        line = (line or "").strip()
        if not line:
            raise ValueError("line is required")
        self._sem = asyncio.Semaphore(4)              # bind to the running loop
        gated = bool(period or locale)

        # 1. bridge
        self._progress(0.08, "Bridging metaphors…")
        br = _extract_json(await self.llm.generate(
            _bridge_prompt(line, period, locale, literalness, mood), _BRIDGE_SYS))
        emotion = br.get("target_emotion", "")
        metaphors = [m for m in br.get("visual_metaphors", []) if m][:max_metaphors]

        # 2. retrieve stock video (cheap tiered fan-out)
        self._progress(0.22, f"Fetching stock video for {len(metaphors)} metaphors…")
        pool: dict = {}
        for m in metaphors:
            for h in await asyncio.to_thread(self.stock.search_assets, m, "video", None, per_metaphor):
                if h.url not in pool:
                    pool[h.url] = {
                        "url": h.url, "source": h.source,
                        "duration": round(h.duration) if h.duration else None,
                        "poster": h.preview_image_url or h.thumbnail_url, "metaphor": m}
        cands = list(pool.values())[:10]              # cap vision calls
        if not cands:
            return {"status": "UNMATCHED", "reason": "no stock footage found for these metaphors",
                    "line": line, "emotion": emotion, "metaphors": metaphors,
                    "picks": [], "considered": [], "counts": {"pool": 0, "kept": 0, "filtered": 0}}

        # 3. vision score + period/locale gate
        self._progress(0.45, f"Vision-scoring {len(cands)} clips…")
        scores = await asyncio.gather(*[self._score(c, emotion, line, period, locale) for c in cands])
        for c, s in zip(cands, scores):
            c.update(s)
        scored = [c for c in cands if c.get("mood") is not None]
        kept = [c for c in scored if not self._anachronistic(c, gated)]
        filtered = [c for c in scored if self._anachronistic(c, gated)]
        for c in filtered:
            c["reject"] = f"period/locale: {c.get('flags') or 'clash'}"

        # 4. listwise acceptance (or abstain)
        picked, status, reason, chosen = [], "UNMATCHED", "no period/locale-safe footage survived", set()
        if kept:
            self._progress(0.82, "Final cut decision…")
            kept.sort(key=lambda c: -((c.get("mood") or 0) + (c.get("nonliteral") or 0) * 0.3
                                      + (0.5 if c.get("universal") else 0)))
            res = _extract_json(await self.llm.generate(_accept_prompt(line, emotion, kept), _LISTWISE_SYS))
            order = [i for i in res.get("pick", []) if 0 <= i < len(kept)]
            chosen = set(order)
            if order:
                status, reason, picked = "MATCHED", "", [kept[i] for i in order]
            else:
                reason = res.get("unmatched_reason") or "nothing cleared the use-bar"
            for i, c in enumerate(kept):
                if i not in chosen:
                    c["reject"] = "below use-bar"

        considered = filtered + [c for i, c in enumerate(kept) if i not in chosen]
        self._progress(1.0, status)
        return {"status": status, "reason": reason, "line": line, "emotion": emotion,
                "metaphors": metaphors, "picks": picked, "considered": considered,
                "counts": {"pool": len(pool), "kept": len(kept), "filtered": len(filtered)}}
