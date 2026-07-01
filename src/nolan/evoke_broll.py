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


_SCORE_SYS = (
    "You are a documentary editor grading candidate b-roll shots (described by their CONTENT) for "
    "how well they work as EVOCATIVE b-roll under a line — mood over literal illustration. Reply STRICT JSON.")


def _library_score_prompt(line: str, emotion: str, period: str, locale: str, cands: List[dict]) -> str:
    ctx = ""
    if period or locale:
        ctx = (f"STORY PERIOD: {period or 'unspecified'}\nSTORY LOCALE: {locale or 'unspecified'}\n"
               "Pure landscape/nature/abstract is UNIVERSAL (fits any era/place); only man-made content "
               "carries a period or culture.\n")
    items = "\n".join(f'[{i}] {c.get("desc", "")[:180]}' for i, c in enumerate(cands))
    return (f'LINE: "{line}"\nTARGET EMOTION: {emotion}\n{ctx}\n'
            f"CANDIDATE SHOTS (by their content description):\n{items}\n\n"
            "Score EACH as evocative b-roll. JSON: {\"scores\": [{\"i\": <index>, "
            '"mood": <0-10 evokes the emotion>, "nonliteral": <0-10, 10=oblique>, '
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

    async def search(self, line: str, *, mode: str = "stock", period: str = "", locale: str = "",
                     literalness: float = 0.25, mood: Optional[str] = None,
                     sources: Optional[List[str]] = None, project: Optional[str] = None,
                     max_metaphors: int = 5, per_metaphor: int = 3) -> dict:
        line = (line or "").strip()
        if not line:
            raise ValueError("line is required")
        mode = "library" if mode == "library" else "stock"
        self._sem = asyncio.Semaphore(4)              # bind to the running loop
        gated = bool(period or locale)

        # 1. bridge
        self._progress(0.08, "Bridging metaphors…")
        br = _extract_json(await self.llm.generate(
            _bridge_prompt(line, period, locale, literalness, mood), _BRIDGE_SYS))
        emotion = br.get("target_emotion", "")
        metaphors = [m for m in br.get("visual_metaphors", []) if m][:max_metaphors]

        # 2. retrieve candidates from the chosen pool
        self._progress(0.22, f"Retrieving {mode} b-roll for {len(metaphors)} metaphors…")
        if mode == "library":
            cands = await self._retrieve_library(metaphors, per_metaphor, project)
        else:
            cands = await self._retrieve_stock(metaphors, per_metaphor, sources)
        pool_n = len(cands)
        if not cands:
            return {"status": "UNMATCHED", "mode": mode, "line": line, "emotion": emotion,
                    "metaphors": metaphors, "picks": [], "considered": [],
                    "reason": ("no library segments found" if mode == "library" else "no stock footage found") + " for these metaphors",
                    "counts": {"pool": 0, "kept": 0, "filtered": 0}}

        # 3. score (vision on stills for stock; text on descriptions for library) + period/locale gate
        if mode == "library":
            self._progress(0.45, f"Scoring {len(cands)} library segments…")
            await self._score_library(cands, emotion, line, period, locale)
        else:
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
        return {"status": status, "reason": reason, "mode": mode, "line": line, "emotion": emotion,
                "metaphors": metaphors, "picks": picked, "considered": considered,
                "counts": {"pool": pool_n, "kept": len(kept), "filtered": len(filtered)}}

    # ---- retrieval: stock (real footage) or library (indexed segments) ----
    async def _retrieve_stock(self, metaphors, per_metaphor, sources):
        pool: dict = {}
        for m in metaphors:
            hits = await asyncio.to_thread(self.stock.search_assets, m, "video", sources or None, per_metaphor)
            for h in hits:
                if h.url not in pool:
                    pool[h.url] = {"kind": "stock", "url": h.url, "source": h.source,
                                   "duration": round(h.duration) if h.duration else None,
                                   "poster": h.preview_image_url or h.thumbnail_url, "metaphor": m}
        return list(pool.values())[:10]

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

    # ---- library scoring: one batch text pass over the segments' descriptions ----
    async def _score_library(self, cands, emotion, line, period, locale):
        try:
            j = _extract_json(await self.llm.generate(
                _library_score_prompt(line, emotion, period, locale, cands), _SCORE_SYS))
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
