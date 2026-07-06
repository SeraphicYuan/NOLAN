"""Attribution manifest + named-asset identity check (SOTA #5).

Copyright strikes are the new-creator unknown-unknown: every asset a video
ships must be able to answer "where is this from and may we use it?" This
walks the plan and builds the answer — honestly, which means assets WITHOUT
license metadata are listed as unverified rather than omitted.

  build_attribution(project)  → attribution.json + CREDITS.md
      per asset: kind, source, license, source_url, title, scene ids.
      Generated images carry their prompt + generator; library clips carry
      their source video; unknown-provenance assets go to a "VERIFY BEFORE
      PUBLISH" section at the top (loud, never buried).

  verify_named_assets(project) → identity report for knowledge-operator art
      A scene whose query NAMES a specific work ("Prima Porta Augustus") gets
      a vision cross-check that the matched image IS that work (the
      Nydia≠Bernini failure class). Vision proposes; the report records —
      a human confirms before publish.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _scenes(plan: Dict[str, Any]):
    for scenes in (plan.get("sections") or {}).values():
        if isinstance(scenes, list):
            for s in scenes:
                if isinstance(s, dict):
                    yield s


def collect_assets(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One entry per distinct asset, with every scene that uses it."""
    by_key: Dict[str, Dict[str, Any]] = {}

    def add(key, entry, sid):
        e = by_key.setdefault(key, {**entry, "scenes": []})
        if sid not in e["scenes"]:
            e["scenes"].append(sid)

    for s in _scenes(plan):
        sid = s.get("id", "?")
        mc = s.get("matched_clip")
        if isinstance(mc, dict) and (mc.get("video_path") or mc.get("external_url")):
            if mc.get("external"):
                add(mc.get("source_url") or mc.get("external_url"),
                    {"kind": "stock video", "path": mc.get("video_path"),
                     "source": mc.get("source"), "license": mc.get("license"),
                     "source_url": mc.get("source_url"),
                     "title": mc.get("title")}, sid)
            else:
                add(str(mc.get("video_path")),
                    {"kind": "library clip", "path": mc.get("video_path"),
                     "source": "own library",
                     "license": "verify source video rights",
                     "source_url": None, "title": Path(str(mc.get("video_path"))).name},
                    sid)
        lic = s.get("asset_license") if isinstance(s.get("asset_license"), dict) else None
        if s.get("matched_asset"):
            if lic:
                add(lic.get("source_url") or s["matched_asset"],
                    {"kind": "stock image", "path": s["matched_asset"],
                     "source": lic.get("source"), "license": lic.get("license"),
                     "source_url": lic.get("source_url"),
                     "title": lic.get("title")}, sid)
            else:
                add(s["matched_asset"],
                    {"kind": "image", "path": s["matched_asset"],
                     "source": None, "license": None, "source_url": None,
                     "title": Path(s["matched_asset"]).name}, sid)
        if s.get("generated_asset"):
            add(f"generated:{s['generated_asset']}",
                {"kind": "generated image", "path": s["generated_asset"],
                 "source": "ComfyUI (project-generated)",
                 "license": "generated for this project",
                 "source_url": None,
                 "title": (s.get("comfyui_prompt") or "")[:80]}, sid)
        for shot in (s.get("shots") or []):
            if isinstance(shot, dict) and shot.get("src"):
                add(str(shot["src"]),
                    {"kind": "shot still", "path": shot["src"],
                     "source": None, "license": None, "source_url": None,
                     "title": Path(str(shot["src"])).name}, sid)
    # tray images
    for s in _scenes(plan):
        for a in (s.get("assets") or []):
            if isinstance(a, dict) and a.get("src") and a.get("kind") == "image":
                add(str(a["src"]),
                    {"kind": "tray image", "path": a["src"], "source": None,
                     "license": None, "source_url": None,
                     "title": Path(str(a["src"])).name}, s.get("id", "?"))
    return list(by_key.values())


def build_attribution(project_path: Path) -> Dict[str, Any]:
    """Write attribution.json + CREDITS.md; return the manifest."""
    from nolan.asset_gate import scan_files

    project_path = Path(project_path)
    plan = json.loads((project_path / "scene_plan.json").read_text(encoding="utf-8"))
    assets = collect_assets(plan)
    unverified = [a for a in assets if not a.get("license")]

    # Watermark scan (asset_gate banner heuristic) — catches files that
    # predate the acquisition gate. Generated assets are exempt.
    def _abs(a):
        p = Path(str(a["path"]))
        return p if p.is_absolute() else project_path / p
    scan_targets = {str(_abs(a)): a for a in assets
                    if a.get("kind") not in ("generated",)
                    and _abs(a).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")}
    suspects = scan_files(scan_targets.keys())
    suspect_assets = []
    for s in suspects:
        a = scan_targets.get(s["path"])
        if a is not None:
            a["watermark_suspect"] = s["reasons"]
            suspect_assets.append(a)

    manifest = {"version": 1, "assets": assets,
                "counts": {"total": len(assets),
                           "unverified": len(unverified),
                           "watermark_suspects": len(suspect_assets)}}
    (project_path / "attribution.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# Credits & licenses", ""]
    if suspect_assets:
        lines += [f"## 🚫 WATERMARK SUSPECTS — replace before publish "
                  f"({len(suspect_assets)})", ""]
        for a in suspect_assets:
            lines.append(f"- **{a['kind']}** `{a['path']}` — "
                         f"{'; '.join(a['watermark_suspect'])} "
                         f"(scenes: {', '.join(a['scenes'])})")
        lines.append("")
    if unverified:
        lines += [f"## ⚠ VERIFY BEFORE PUBLISH ({len(unverified)})", ""]
        for a in unverified:
            lines.append(f"- **{a['kind']}** `{a['path']}` — no license metadata "
                         f"(scenes: {', '.join(a['scenes'])})")
        lines.append("")
    lines += ["## Attributed assets", ""]
    for a in assets:
        if not a.get("license"):
            continue
        src = f" — {a['source']}" if a.get("source") else ""
        url = f" ({a['source_url']})" if a.get("source_url") else ""
        lines.append(f"- **{a['kind']}**: {a.get('title') or a['path']}{src} · "
                     f"{a['license']}{url} · scenes {', '.join(a['scenes'])}")
    (project_path / "CREDITS.md").write_text("\n".join(lines) + "\n",
                                             encoding="utf-8")
    return manifest


# --- identity verification (knowledge-operator art) ------------------------------

_NAMED_HINTS = ("painting", "statue", "sculpture", "portrait", "fresco",
                "engraving", "woodcut", "manuscript")


def named_asset_scenes(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Scenes whose query NAMES a specific work (heuristic: art types or
    capitalized multiword titles in the query) and that carry a still."""
    out = []
    for s in _scenes(plan):
        q = (s.get("search_query") or "").strip()
        if not q or not s.get("matched_asset"):
            continue
        if ((s.get("visual_type") or "") == "archival-art"
                or any(h in q.lower() for h in _NAMED_HINTS)):
            out.append(s)
    return out


async def verify_named_assets(project_path: Path, llm_vision=None) -> List[Dict[str, Any]]:
    """[{scene, query, verdict, reason}] — vision cross-check per named asset."""
    project_path = Path(project_path)
    plan = json.loads((project_path / "scene_plan.json").read_text(encoding="utf-8"))
    targets = named_asset_scenes(plan)
    if not targets:
        return []
    if llm_vision is None:
        try:
            from nolan.config import load_config
            from nolan.llm import GeminiClient, create_text_llm  # noqa: F401
            cfg = load_config()
            from nolan.llm import GeminiClient as _G
            llm_vision = _G(cfg.gemini.api_key)
        except Exception as exc:
            logger.warning("identity verify skipped — no vision client: %s", exc)
            return [{"scene": s.get("id"), "query": s.get("search_query"),
                     "verdict": "unchecked", "reason": "no vision client"}
                    for s in targets]
    results = []
    for s in targets:
        p = Path(s["matched_asset"])
        if not p.is_absolute():
            p = project_path / p
        prompt = (f"Is this image actually the specific work described as: "
                  f"\"{s.get('search_query')}\"? Reply STRICT JSON: "
                  f"{{\"match\": true|false, \"reason\": \"<one line>\"}}")
        try:
            raw = await llm_vision.generate_with_image(prompt, str(p))
            import re as _re
            m = _re.search(r"\{.*\}", raw, _re.S)
            j = json.loads(m.group(0)) if m else {}
            results.append({"scene": s.get("id"), "query": s.get("search_query"),
                            "verdict": "verified" if j.get("match") else "MISMATCH",
                            "reason": j.get("reason", "")})
        except Exception as exc:
            results.append({"scene": s.get("id"), "query": s.get("search_query"),
                            "verdict": "unchecked", "reason": str(exc)[:120]})
    return results
