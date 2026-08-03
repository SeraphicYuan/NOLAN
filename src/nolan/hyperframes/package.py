"""The ship stage — everything between a finished render and a published video.

`nolan/packaging.py` has built chapters, subtitles, titles, description, thumbnails and credits since
SOTA #6. It reads `scene_plan.json`, which HF comps do not have — so the DOMINANT pipeline could not
reach its own packaging organ. That is the same stranded-organ shape as the VLM floor.

This is a SIBLING rather than an adapter, and the reason is worth recording because the plan said
otherwise. `build_package` is bound to the Director path in four places at once: `plan["sections"]`,
`output/final.mp4`, `assets/voiceover/voiceover.srt`, and — decisively — it renders its typographic
thumbnail card through the **Remotion** block library, which is the LEGACY renderer on this path
(CLAUDE.md). Synthesising a fake scene_plan to reach a Remotion card would have been more code than
this, and would have produced the wrong artifact. The pure pieces (`_hook_sentence`, the title prompt)
are IMPORTED from it, so the taste that lives in those is shared rather than forked.

Everything lands in `<comp>/package/` with a `package.json` inventory, mirroring the Director path's
shape so a human (or a later tool) sees one format.

THE STALE GUARD is the reason Phase 1 came first. Titles and thumbnails are generated FROM a render;
if the specs have moved since that render, you are packaging a video you are not shipping. The
manifest makes that a comparison, so this refuses rather than warns.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import manifest as M
from . import provenance as PROV
from . import subtitles as SUBS
from .edit import _comp_dir, _project_script, _project_dir

logger = logging.getLogger(__name__)


def package_dir(comp: str) -> Path:
    d = _comp_dir(comp) / "package"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _script_text(comp: str) -> str:
    """The essay's script — SOURCE.md is the HF convention; fall back to the project's script.md."""
    for name in ("SOURCE.md", "SCRIPT.md", "STORYBOARD.md"):
        p = _comp_dir(comp) / name
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except OSError:
                pass
    try:
        return _project_script(_project_dir(comp))
    except Exception:
        return ""


def _theme(comp: str) -> str:
    try:
        return json.loads((_comp_dir(comp) / "hyperframes.json").read_text(encoding="utf-8")).get("theme") or ""
    except Exception:
        return ""


def check_fresh(comp: str) -> Dict[str, Any]:
    """Is the deliverable the video these artifacts would describe?"""
    cd = _comp_dir(comp)
    st = M.staleness(comp, cd)
    d = M.deliverable(cd)
    return {"deliverable": str(d) if d else None, "state": st["state"],
            "stale_frames": st.get("stale_frames") or [], "detail": st["detail"],
            "ok": bool(d) and st["state"] in ("current", "unknown")}


def build(comp: str, *, force: bool = False, llm=None) -> Dict[str, Any]:
    """Assemble `package/` for a finished comp. Returns the inventory.

    Refuses on a stale deliverable unless `force` — packaging a render the specs have moved past is
    how you end up promoting a video you are not shipping."""
    fresh = check_fresh(comp)
    if not fresh["ok"] and not force:
        raise RuntimeError(
            f"package: refusing — {fresh['detail']}"
            + (f" (stale: {', '.join(fresh['stale_frames'])})" if fresh["stale_frames"] else "")
            + ". Re-run `nolan hf-finish`, or pass force=True to package the render as it stands.")
    if not fresh["deliverable"]:
        raise RuntimeError("package: there is no render to package (renders/video.mp4 is absent)")

    pkg = package_dir(comp)
    inv: Dict[str, Any] = {"version": 1, "comp": comp, "items": {},
                           "deliverable": fresh["deliverable"], "freshness": fresh["state"]}

    # 1 · chapters (VO sections ARE the beats — narration owns duration)
    chs = SUBS.chapters(comp)
    total = float((M.load(_comp_dir(comp)) or {}).get("duration_s") or 0)
    (pkg / "chapters.txt").write_text(SUBS.chapters_text(comp) + "\n", encoding="utf-8")
    inv["items"]["chapters"] = "chapters.txt"
    issues = SUBS.youtube_chapter_issues(chs, total) if total else []
    if issues:
        inv["items"]["chapter_issues"] = issues     # YouTube ignores a bad list SILENTLY — surface it

    # 2 · subtitles
    sub = SUBS.write(comp, out_dir=pkg)
    inv["items"]["subtitles"] = "subtitles.srt" if sub.get("ok") else None
    inv["items"]["subtitle_cues"] = sub.get("cues", 0)

    # 3 · provenance (a REPORT — see nolan.hyperframes.provenance for why it does not gate)
    rep = PROV.audit(comp)
    (pkg / "PROVENANCE.md").write_text(PROV.render_markdown(rep), encoding="utf-8")
    inv["items"]["provenance"] = "PROVENANCE.md"
    inv["items"]["provenance_summary"] = rep["summary"]["by_status"]

    # 4 · credits, if the project keeps them
    for cand in (_comp_dir(comp) / "CREDITS.md", _project_dir(comp) / "CREDITS.md"):
        try:
            if cand.exists():
                shutil.copyfile(cand, pkg / "CREDITS.md")
                inv["items"]["credits"] = "CREDITS.md"
                break
        except Exception:
            pass

    # 5 · the draft (titles / description / thumbnail briefs) — v1, revisable in Phase 4
    from .ship import initial_draft, render_description, write_draft
    draft = initial_draft(comp, script=_script_text(comp), llm=llm)
    write_draft(comp, draft, n=1)
    (pkg / "description.txt").write_text(render_description(comp, draft), encoding="utf-8")
    (pkg / "title_options.txt").write_text("\n".join(draft["titles"]) + "\n", encoding="utf-8")
    inv["items"]["titles"] = draft["titles"]
    inv["items"]["description"] = "description.txt"
    inv["items"]["draft"] = "drafts/draft-01.json"
    inv["current_draft"] = 1

    (pkg / "package.json").write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
    return inv


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.package",
                                 description="Build package/ for a finished HyperFrames comp.")
    ap.add_argument("comp")
    ap.add_argument("--force", action="store_true", help="package even if the render is stale")
    a = ap.parse_args()
    inv = build(a.comp, force=a.force)
    print(f"package/ for {a.comp} — render {inv['freshness']}")
    for k, v in inv["items"].items():
        print(f"  {k:22s} {v if not isinstance(v, (list, dict)) else json.dumps(v)[:70]}")


if __name__ == "__main__":
    main()
