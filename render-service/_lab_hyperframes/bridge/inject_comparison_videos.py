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
    """Every video hole across every frame the index mounts, resolved to an absolute (rect, window).

    The video is positioned at the SCENE's global window (frame global start + the hole's scene-local
    `data-cmp-sstart`, for `data-cmp-sdur` seconds) and plays FROM ITS START — exactly like a ground
    (inject_root_video). This is why a short comparison clip no longer freezes: the old code used the
    whole-FRAME window, so a scene late in the frame seeked the clip past its end and clamped. Falls back
    to the frame window for legacy HTML with no `data-cmp-sstart` (recompose to get the scene-window form)."""
    mounts = []
    for m in re.finditer(r'<div\b[^>]*\bdata-composition-src="([^"]*)"[^>]*>', index_html):
        tag, src = m.group(0), m.group(1)
        frame_start = float(_attr(tag, "data-start") or "0")
        frame_dur = _attr(tag, "data-duration") or "0"
        fpath = proj / src
        if not fpath.exists():
            continue
        for vm in _VHOLE.finditer(fpath.read_text(encoding="utf-8")):
            vtag, rect = vm.group(0), _attr(vm.group(0), "data-cmp-rect")
            if not rect:
                continue
            x, y, w, h = (int(float(v)) for v in rect.split(","))
            sstart, sdur = _attr(vtag, "data-cmp-sstart"), _attr(vtag, "data-cmp-sdur")
            if sstart is not None and sdur is not None:      # scene window → the video plays from 0 during the scene
                vstart, vdur = f"{frame_start + float(sstart):.3f}", sdur
            else:                                            # legacy: whole-frame window (a late scene may freeze)
                vstart, vdur = f"{frame_start:.3f}", frame_dur
            mounts.append({"src": _attr(vtag, "data-cmp-video"), "id": _attr(vtag, "data-cmp-id") or "cmpvid",
                           "mstart": _attr(vtag, "data-cmp-mstart") or "0",
                           "framed": _attr(vtag, "data-cmp-framed") == "1", "gray": _attr(vtag, "data-cmp-gray") == "1",
                           "x": x, "y": y, "w": w, "h": h, "start": vstart, "dur": vdur})
    return mounts


# The HyperFrames renderer schedules only tracks 0..13 — a clip on data-track-index >= 14 is silently
# DROPPED and its panel renders BLACK (incident: the-openai-debate f11s04, the 7th comparison panel).
_TRACK_CAP = 14


def assign_tracks(mounts, base=8):
    """data-track-index for each mount. It is TEMPORAL (collision detection), not z-order (z = DOM order),
    so comparison videos that DON'T overlap in time can SHARE a track. The old `base+i` handed every panel a
    distinct index; with 7 panels the last reached track 14 — past the renderer's 14-track window (0..13) —
    so it was silently dropped and the panel rendered black. Greedy interval-coloring reuses low tracks:
    only the two panels of a single comparison scene overlap, so nothing exceeds base+1. base=8 is a
    proven-rendering track that clears grounds(0), the frame sub-comp(1) and the voice track(10)."""
    tracks = [base] * len(mounts)
    end_on = {}                                   # track -> end time of the clip currently occupying it
    for i in sorted(range(len(mounts)), key=lambda k: (float(mounts[k]["start"]), k)):
        s = float(mounts[i]["start"])
        e = s + float(mounts[i]["dur"] or 0)
        t = base
        while end_on.get(t, -1.0) > s:            # a clip on track t is still playing at s → try the next
            t += 1
        tracks[i] = t
        end_on[t] = e
    return tracks


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
    # FREEZE-HEAL comparison sides too (assemble_media only heals `ground:{kind:video}`): a clip shorter
    # than its scene window freezes on the last frame for the rest of the scene. Loop each to its window.
    try:
        from assemble_media import heal_video_freezes
        healed = heal_video_freezes(proj, [{"src": m["src"], "duration": float(m["dur"])} for m in mounts])
        for m, h in zip(mounts, healed):
            m["src"] = h["src"]
    except Exception as e:
        print(f"  (comparison freeze-heal skipped: {type(e).__name__}: {e})")
    tracks = assign_tracks(mounts)
    if tracks and max(tracks) >= _TRACK_CAP:      # loud, not silent — a dropped track = a BLACK panel
        print(f"  ⚠ comparison track-index {max(tracks)} >= renderer cap ({_TRACK_CAP}); the renderer only "
              f"schedules tracks 0..{_TRACK_CAP - 1} so this panel would render BLACK — too many panels "
              f"overlap in time (raise the cap only if the renderer's track window grew)")
    block = MARK0 + "".join(render_video(m, t) for m, t in zip(mounts, tracks)) + MARK1
    html = re.sub(r'(<div\b[^>]*\bid="root"[^>]*>)', lambda mm: mm.group(1) + block, html, count=1)
    idx.write_text(html, encoding="utf-8")
    print(f"injected {len(mounts)} root video(s): " + ", ".join(f"{m['id']}@{m['x']},{m['y']} {m['w']}x{m['h']}" for m in mounts))
    return len(mounts)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python inject_comparison_videos.py <project_dir>")
    inject(Path(sys.argv[1]))
