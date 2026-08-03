"""Thumbnails — composed in HyperFrames, judged at the size they are actually seen.

THE SPLIT THAT MAKES THIS REAL. Do not ask an image model for the finished thumbnail: diffusion still
mangles text and every strong concept here is type-led, the punch comes from a REAL object you already
have on screen, and you need pixel-exact repeatability to A/B. So:

    concept (headline <=4 words + a pool asset + a layout)   ->  LLM
    cutout                                                   ->  rembg
    composite + type                                         ->  HyperFrames, the essay's own theme
    score                                                    ->  VLM, at 168x94

JUDGE AT FEED SIZE. A thumbnail is chosen in a mobile feed at roughly 168x94 px. Scoring a 1920px
render passes designs that are unreadable where the decision is actually made — the most common way a
thumbnail process produces confident garbage. The VLM is shown the downscaled image.

RENDER BIG, SHIP SMALL: composed at 1920x1080 and downscaled to 1280x720, because supersampling gives
noticeably cleaner type edges at feed size than authoring at 720p.

The layout set is deliberately SMALL and hardcoded — four arrangements, no templating language.
Registry-first is how unused abstractions get built; a fifth layout can earn the generalisation.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .edit import _comp_dir, _scaffold_preview, list_frames

FEED_W, FEED_H = 168, 94              # where the decision is actually made
OUT_W, OUT_H = 1280, 720

# id -> what it is FOR. The honesty test asserts this set equals what `_compose` can render.
LAYOUTS: Dict[str, str] = {
    "statement-card": "the headline alone, huge, on the theme surface — for a claim that needs no object",
    "object-left": "a cut-out object on the left, headline stacked right — the default when you have a hero",
    "missing-value": "a list/board where one row's value is a conspicuous blank — for an absence",
    "two-tags": "one object, two conflicting labels — for a contradiction stated in numbers",
}


def _theme(comp: str) -> str:
    try:
        return json.loads((_comp_dir(comp) / "hyperframes.json").read_text(encoding="utf-8")).get("theme") or ""
    except Exception:
        return "highlighter-editorial"


def _tokens(theme: str) -> Dict[str, str]:
    """The essay's own palette + type, so a thumbnail looks like the video it sells."""
    out = {"surface": "#111", "text": "#fff", "accent": "#e5b53f",
           "display": "Georgia, serif", "mono": "ui-monospace, monospace"}
    f = Path(__file__).resolve().parents[3] / "themes" / theme / "tokens.css"
    if not f.exists():
        return out
    css = f.read_text(encoding="utf-8")
    for key, pat in (("surface", r"--surface:\s*([^;]+);"), ("text", r"--text:\s*([^;]+);"),
                     ("accent", r"--accent:\s*([^;]+);"),
                     ("display", r"--font-display-en:\s*([^;]+);"), ("mono", r"--font-mono:\s*([^;]+);")):
        m = re.search(pat, css)
        if m:
            out[key] = m.group(1).strip()
    return out


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _compose(layout: str, headline: str, tok: Dict[str, str], asset: Optional[str],
             sub: str = "") -> str:
    """One 1920x1080 HTML frame. Type is set in the theme's own faces; no external requests."""
    head = _esc(headline).upper()
    words = head.split()
    hi = words[-1] if words else ""
    body = " ".join(words[:-1])
    img = f'<img src="{_esc(asset)}" alt="">' if asset else ""
    common = f"""<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1920px;height:1080px;overflow:hidden;background:{tok['surface']};
  font-family:{tok['display']};color:{tok['text']}}}
.wrap{{position:absolute;inset:0;display:flex;align-items:center;padding:96px}}
h1{{font-size:150px;line-height:0.94;font-weight:900;letter-spacing:-0.02em}}
h1 .hi{{color:{tok['accent']}}}
.sub{{font-family:{tok['mono']};font-size:34px;letter-spacing:0.14em;text-transform:uppercase;
  opacity:.72;margin-top:28px}}
img{{max-width:100%;max-height:100%;object-fit:contain}}
/* Sized from a real render: at 56px these rows were unreadable in a 168px feed tile and left the
   frame two-thirds empty. A thumbnail has no small type. */
.rows{{font-family:{tok['mono']};font-size:96px;line-height:1.42;font-weight:700}}
.rows .dim{{opacity:.45}}
.rows .hit{{color:{tok['accent']};font-size:112px}}
.rows .hit b{{font-size:150px;vertical-align:-14px}}
.tag{{font-family:{tok['mono']};font-size:64px;padding:14px 30px;border:6px solid {tok['accent']};
  border-radius:14px;display:inline-block}}
</style>"""
    if layout == "object-left":
        inner = (f'<div style="flex:0 0 46%;height:100%;display:flex;align-items:center">{img}</div>'
                 f'<div style="flex:1;padding-left:64px"><h1>{body} <span class="hi">{hi}</span></h1>'
                 + (f'<div class="sub">{_esc(sub)}</div>' if sub else "") + "</div>")
    elif layout == "missing-value":
        rows = "".join(f'<div class="dim">{_esc(r)}</div>'
                       for r in (sub or "GOLD $2,431|SILVER $28.14|OIL $79.02").split("|"))
        inner = (f'<div style="flex:1"><div class="rows">{rows}'
                 f'<div class="hit">{head} <b>&mdash;</b></div></div></div>')
    elif layout == "two-tags":
        a, b = (sub.split("|") + ["", ""])[:2] if sub else ("$10,000", "$1,000")
        inner = (f'<div style="flex:0 0 44%;height:100%;display:flex;align-items:center">{img}</div>'
                 f'<div style="flex:1;padding-left:64px"><div class="tag">{_esc(a)}</div>'
                 f'<div style="height:28px"></div><div class="tag">{_esc(b)}</div>'
                 f'<h1 style="font-size:96px;margin-top:34px">{head}</h1></div>')
    else:                                                    # statement-card
        inner = (f'<div style="flex:1;text-align:center"><h1 style="font-size:190px">{body} '
                 f'<span class="hi">{hi}</span></h1>'
                 + (f'<div class="sub">{_esc(sub)}</div>' if sub else "") + "</div>")
    return (f'<template>{common}<div class="scene clip" data-start="0" data-duration="1">'
            f'<div class="wrap">{inner}</div></div></template>')


def cutout(comp: str, asset: str) -> Optional[str]:
    """Background-removed copy of a pool asset, so type can overlap the subject. rembg is installed."""
    src = _comp_dir(comp) / "assets" / Path(asset).name
    if not src.exists():
        return None
    out = _comp_dir(comp) / "package" / "thumbnails" / f"_cut_{src.stem}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        return out.name
    try:
        from rembg import remove
        out.write_bytes(remove(src.read_bytes()))
        return out.name
    except Exception:
        return None


def render(comp: str, brief: Dict[str, Any], index: int = 1) -> Dict[str, Any]:
    """Compose ONE thumbnail from a brief -> package/thumbnails/NN-<layout>.png (1280x720)."""
    layout = brief.get("layout") if brief.get("layout") in LAYOUTS else "statement-card"
    tok = _tokens(_theme(comp))
    asset = brief.get("asset") or brief.get("subject_asset")
    rel = None
    if asset:
        cut = cutout(comp, asset) if brief.get("cutout", True) else None
        rel = cut or f"assets/{Path(asset).name}"
    html = _compose(layout, brief.get("headline", ""), tok, rel, brief.get("sub", ""))

    tdir = _comp_dir(comp) / "package" / "thumbnails"
    tdir.mkdir(parents=True, exist_ok=True)
    frames = [f.get("id") if isinstance(f, dict) else f for f in list_frames(comp)]
    if not frames:
        return {"ok": False, "detail": "comp has no frames to scaffold from"}
    pdir = _scaffold_preview(comp, frames[0], html_text=html, preview_id=f"_thumb_{index}",
                             dur_override=1.0)
    if rel and not rel.startswith("assets/"):
        try:                                             # stage the cut-out into the scaffold
            (pdir / rel).write_bytes((tdir / rel).read_bytes())
        except OSError:
            pass
    r = subprocess.run(["npx", "--yes", "hyperframes@latest", "snapshot", str(pdir),
                        "--at", "0.4", "--no-end", "--describe", "false"],
                       cwd=str(pdir), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", shell=(os.name == "nt"))
    snaps = sorted((pdir / "snapshots").glob("frame-*.png")) if (pdir / "snapshots").is_dir() else []
    if not snaps:
        return {"ok": False, "detail": (r.stdout + r.stderr)[-300:] or "snapshot produced nothing"}
    out = tdir / f"{index:02d}-{layout}.png"
    try:                                                  # render big, ship small
        from PIL import Image
        with Image.open(snaps[0]) as im:
            im.convert("RGB").resize((OUT_W, OUT_H), Image.LANCZOS).save(out, quality=92)
    except Exception:
        out.write_bytes(snaps[0].read_bytes())
    return {"ok": True, "png": str(out), "layout": layout, "headline": brief.get("headline", "")}


def feed_preview(png) -> Optional[Path]:
    """The same image at 168x94 — what the judge (and the viewer) actually sees."""
    try:
        from PIL import Image
        out = Path(png).with_name(Path(png).stem + f".feed{FEED_W}.png")
        with Image.open(png) as im:
            im.convert("RGB").resize((FEED_W, FEED_H), Image.LANCZOS).save(out)
        return out
    except Exception:
        return None


_JUDGE = ("You are looking at a YouTube thumbnail AT THE SIZE IT APPEARS IN A MOBILE FEED "
          f"({FEED_W}x{FEED_H} px). Judge only what you can actually resolve at this size. "
          'Reply STRICT JSON: {"readable": true|false, "words_legible": "<what you can read>", '
          '"focal_clarity": 1-5, "verdict": "ship"|"revise", "note": "one line"}')


def score(comp: str, png) -> Dict[str, Any]:
    """VLM verdict on the FEED-SIZE image. A 1920px score passes thumbnails that vanish at 168px."""
    small = feed_preview(png)
    if not small:
        return {"ok": False, "detail": "could not downscale"}
    try:
        import asyncio
        from nolan.config import load_config
        from nolan.evoke_broll import _vision_config
        from nolan.vision import create_vision_provider
        prov = create_vision_provider(_vision_config(load_config()))
        raw = asyncio.run(prov.describe_image(small, _JUDGE))
        m = re.search(r"\{.*\}", raw or "", re.S)
        return {"ok": True, **(json.loads(m.group(0)) if m else {"verdict": "?", "note": (raw or "")[:160]})}
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


def build(comp: str, briefs: Optional[List[Dict[str, Any]]] = None, judge: bool = True) -> Dict[str, Any]:
    """Render every brief in the current draft and (optionally) score each at feed size."""
    if briefs is None:
        from .ship import load_draft
        briefs = (load_draft(comp) or {}).get("thumbnail_briefs") or []
    out = []
    for i, b in enumerate(briefs, 1):
        res = render(comp, b, index=i)
        if res.get("ok") and judge:
            res["score"] = score(comp, Path(res["png"]))
        out.append(res)
    return {"comp": comp, "thumbnails": out, "rendered": sum(1 for r in out if r.get("ok"))}


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="nolan.hyperframes.thumbnail",
                                 description="Render + feed-size-judge thumbnails for a comp.")
    ap.add_argument("comp")
    ap.add_argument("--no-judge", action="store_true")
    a = ap.parse_args()
    res = build(a.comp, judge=not a.no_judge)
    print(f"{res['rendered']}/{len(res['thumbnails'])} rendered")
    for t in res["thumbnails"]:
        if t.get("ok"):
            s = t.get("score") or {}
            print(f"  {Path(t['png']).name:28s} {t['headline'][:30]:32s} "
                  f"{s.get('verdict', '-')}  {s.get('note', '')[:60]}")
        else:
            print(f"  FAILED — {t.get('detail', '')[:90]}")


if __name__ == "__main__":
    main()
