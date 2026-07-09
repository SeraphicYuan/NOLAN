"""Mount `comparison` video panels at the index root (archetype B).

The composer's `comparison` block renders a video side as a TRANSPARENT HOLE carrying `data-cmp-*`
attributes (src + panel rect on the 1920x1080 canvas). The framework only drives a `<video>` that is
a DIRECT child of the index host root — never one inside a sub-composition (`media_in_subcomposition`).
So this step reads those holes from each mounted frame and injects a positioned `<video>` into
`index.html`, BEHIND the frame. Net effect: a video-vs-video is literally two stacked root videos with
the frame's divider / labels / title painted on top (exactly "stack two videos with a border on each").

  python inject_comparison_videos.py <project_dir>   # edits <project_dir>/index.html in place (idempotent)

Styles are inlined (the frame's scoped <style> does not reach an element mounted at the index root).
"""
import re
import sys
from pathlib import Path

_VHOLE = re.compile(r'<div\b[^>]*\bdata-cmp-video="[^"]*"[^>]*>')
MARK0, MARK1 = "<!-- cmp-videos:start -->", "<!-- cmp-videos:end -->"


def _attr(tag, name):
    m = re.search(r'\b' + re.escape(name) + r'="([^"]*)"', tag)
    return m.group(1) if m else None


def collect_mounts(index_html, proj):
    """Every video hole across every frame the index mounts, resolved to an absolute (rect, window)."""
    mounts = []
    for m in re.finditer(r'<div\b[^>]*\bdata-composition-src="([^"]*)"[^>]*>', index_html):
        tag, src = m.group(0), m.group(1)
        start, dur = _attr(tag, "data-start") or "0", _attr(tag, "data-duration") or "0"
        fpath = proj / src
        if not fpath.exists():
            continue
        for vm in _VHOLE.finditer(fpath.read_text(encoding="utf-8")):
            vtag, rect = vm.group(0), _attr(vm.group(0), "data-cmp-rect")
            if not rect:
                continue
            x, y, w, h = (int(float(v)) for v in rect.split(","))
            mounts.append({"src": _attr(vtag, "data-cmp-video"), "id": _attr(vtag, "data-cmp-id") or "cmpvid",
                           "mstart": _attr(vtag, "data-cmp-mstart") or "0",
                           "framed": _attr(vtag, "data-cmp-framed") == "1", "gray": _attr(vtag, "data-cmp-gray") == "1",
                           "x": x, "y": y, "w": w, "h": h, "start": start, "dur": dur})
    return mounts


def render_video(m, track):
    # z-order is DOM order (injected before the frame mount → behind it); track-index is temporal only,
    # so each concurrent video needs a DISTINCT track to avoid `overlapping_clips_same_track`.
    style = (f"position:absolute;left:{m['x']}px;top:{m['y']}px;width:{m['w']}px;height:{m['h']}px;"
             "object-fit:cover;background:#000;display:block;")
    if m["framed"]:
        style += "border-radius:20px;border:3px solid rgba(255,255,255,0.16);box-shadow:0 22px 52px rgba(0,0,0,0.5);"
    if m["gray"]:
        style += "filter:grayscale(1) contrast(1.03);"
    ms = f' data-media-start="{m["mstart"]}"' if str(m["mstart"]) not in ("", "0") else ""
    return (f'<video id="{m["id"]}" class="clip cmp-rootvid" data-start="{m["start"]}" data-duration="{m["dur"]}" '
            f'data-track-index="{track}" src="{m["src"]}" muted playsinline{ms} style="{style}"></video>')


def inject(proj: Path):
    idx = proj / "index.html"
    html = idx.read_text(encoding="utf-8")
    html = re.sub(re.escape(MARK0) + r".*?" + re.escape(MARK1), "", html, flags=re.S)  # idempotent
    mounts = collect_mounts(html, proj)
    if not mounts:
        print("no comparison video holes found — nothing to inject")
        return 0
    block = MARK0 + "".join(render_video(m, 8 + i) for i, m in enumerate(mounts)) + MARK1
    html = re.sub(r'(<div\b[^>]*\bid="root"[^>]*>)', lambda mm: mm.group(1) + block, html, count=1)
    idx.write_text(html, encoding="utf-8")
    print(f"injected {len(mounts)} root video(s): " + ", ".join(f"{m['id']}@{m['x']},{m['y']} {m['w']}x{m['h']}" for m in mounts))
    return len(mounts)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python inject_comparison_videos.py <project_dir>")
    inject(Path(sys.argv[1]))
