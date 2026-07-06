"""YouTube packaging (SOTA #6) — the deliverables around the video.

A finished essay still needs: thumbnail candidates, title options, a
description, chapter markers, subtitles, and credits. All of it now falls
out of artifacts the pipeline already owns:

  chapters     the plan's section anchors (narration-exact by construction)
  subtitles    the captions pass already wrote voiceover.srt — shipped as-is
  thumbnails   best frames pulled at the plan's high-energy media beats +
               one typographic card rendered from the hook via the block
               library (themed by the brief, like everything else)
  title/desc   LLM proposes from the hook + brief tone; deterministic
               fallback uses the script's own first sentence — never blocks
  credits      the SOTA #5 attribution manifest, regenerated fresh

Everything lands in projects/<slug>/package/ with a package.json inventory.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _fmt_ts(t: float) -> str:
    t = max(0, int(round(t)))
    return f"{t // 60:02d}:{t % 60:02d}"


def build_chapters(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for name, scenes in (plan.get("sections") or {}).items():
        if not isinstance(scenes, list) or not scenes:
            continue
        try:
            start = min(float(s.get("start_seconds") or 0) for s in scenes
                        if isinstance(s, dict))
        except ValueError:
            continue
        out.append({"t": start, "title": name})
    out.sort(key=lambda c: c["t"])
    if out:
        out[0]["t"] = 0.0                    # YouTube requires a 00:00 chapter
    return out


def _hook_sentence(script_text: str) -> str:
    body = re.sub(r"^#.*$", "", script_text, flags=re.M)
    body = re.sub(r"\*\*.*?\*\*", "", body).strip()
    m = re.search(r"[A-Z][^.!?]{20,180}[.!?]", body)
    return m.group(0).strip() if m else body[:120]


_TITLE_PROMPT = """You are titling a YouTube video essay. From the hook and tone
below, reply STRICT JSON:
{{"titles": ["3 options, each <=60 chars, curiosity-forward, no clickbait lies"],
  "description_opening": "2 sentences for the description, matching the essay's tone",
  "thumb_text": "3-5 WORDS for the thumbnail card, punchy"}}

TONE: {tone}
HOOK: {hook}
"""


async def build_package(project_path: Path, llm=None,
                        skip_thumb_render: bool = False) -> Dict[str, Any]:
    """Assemble package/ for a rendered project. Returns the inventory."""
    project_path = Path(project_path)
    plan = json.loads((project_path / "scene_plan.json").read_text(encoding="utf-8"))
    script = (project_path / "script.md").read_text(encoding="utf-8") \
        if (project_path / "script.md").exists() else ""
    brief = None
    try:
        from nolan.project_brief import load_brief
        brief = load_brief(project_path)
    except Exception:
        pass
    pkg = project_path / "package"
    pkg.mkdir(exist_ok=True)
    inventory: Dict[str, Any] = {"version": 1, "items": {}}

    # 1. chapters
    chapters = build_chapters(plan)
    ch_lines = [f"{_fmt_ts(c['t'])} {c['title']}" for c in chapters]
    (pkg / "chapters.txt").write_text("\n".join(ch_lines) + "\n", encoding="utf-8")
    inventory["items"]["chapters"] = "chapters.txt"

    # 2. subtitles (already produced by the captions pass — shipped, not rebuilt)
    srt = project_path / "assets" / "voiceover" / "voiceover.srt"
    if srt.exists():
        (pkg / "subtitles.srt").write_bytes(srt.read_bytes())
        inventory["items"]["subtitles"] = "subtitles.srt"
    else:
        inventory["items"]["subtitles"] = None    # honest gap, not silence

    # 3. credits (SOTA #5, regenerated fresh)
    from nolan.attribution import build_attribution
    manifest = build_attribution(project_path)
    (pkg / "CREDITS.md").write_bytes((project_path / "CREDITS.md").read_bytes())
    inventory["items"]["credits"] = "CREDITS.md"
    inventory["items"]["unverified_assets"] = manifest["counts"]["unverified"]

    # 4. title / description / thumb text (LLM proposes, fallback never blocks)
    hook = _hook_sentence(script)
    tone = (brief or {}).get("tone") or "neutral"
    titles, desc_open, thumb_text = [], "", ""
    if llm is not None:
        try:
            raw = await llm.generate(_TITLE_PROMPT.format(tone=tone, hook=hook))
            m = re.search(r"\{.*\}", raw, re.S)
            j = json.loads(m.group(0)) if m else {}
            titles = [str(t)[:70] for t in (j.get("titles") or [])][:3]
            desc_open = str(j.get("description_opening") or "")
            thumb_text = str(j.get("thumb_text") or "")
        except Exception as exc:
            logger.warning("packaging: title LLM failed (%s) — fallback", exc)
    if not titles:
        titles = [hook[:60]]
    if not thumb_text:
        thumb_text = " ".join(hook.split()[:5]).upper()
    description = (desc_open + "\n\n" if desc_open else "") + \
        "Chapters:\n" + "\n".join(ch_lines) + \
        "\n\nSources & credits: see pinned comment / CREDITS.md\n"
    (pkg / "title_options.txt").write_text("\n".join(titles) + "\n", encoding="utf-8")
    (pkg / "description.txt").write_text(description, encoding="utf-8")
    inventory["items"]["titles"] = titles
    inventory["items"]["description"] = "description.txt"

    # 5. thumbnails: best frames at the top-energy media beats…
    final = project_path / "output" / "final.mp4"
    frames = []
    if final.exists():
        scenes = [s for sc in (plan.get("sections") or {}).values()
                  if isinstance(sc, list) for s in sc if isinstance(s, dict)]
        media = [s for s in scenes
                 if s.get("matched_clip") or s.get("matched_asset")
                 or s.get("generated_asset")]
        media.sort(key=lambda s: float(s.get("energy") or 0), reverse=True)
        ff = _ffmpeg()
        for k, s in enumerate(media[:3]):
            t = float(s.get("start_seconds") or 0) + 1.0
            dest = pkg / f"thumb_frame_{k + 1}.png"
            r = subprocess.run([ff, "-y", "-v", "quiet", "-ss", f"{t:.2f}",
                                "-i", str(final), "-frames:v", "1", str(dest)],
                               capture_output=True)
            if r.returncode == 0 and dest.exists():
                frames.append(dest.name)
    # …and one typographic card from the hook (block library, brief-themed)
    if not skip_thumb_render:
        try:
            from nolan.layout_blocks import render_layout_block
            clip = render_layout_block(
                "kinetic_headline",
                {"text": thumb_text,
                 "accent_words": [thumb_text.split()[-1].lower()]},
                3.0, pkg / "_thumb_card.mp4", scene_id="thumb",
                theme=(brief or {}).get("theme"))
            if clip:
                dest = pkg / "thumb_card.png"
                subprocess.run([_ffmpeg(), "-y", "-v", "quiet", "-ss", "2.4",
                                "-i", str(clip), "-frames:v", "1", str(dest)],
                               capture_output=True)
                if dest.exists():
                    frames.append(dest.name)
                Path(clip).unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("packaging: thumb card render failed: %s", exc)
    inventory["items"]["thumbnails"] = frames

    (pkg / "package.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    return inventory
