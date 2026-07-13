"""Post-process an assembled HyperFrames index.html to mount stock VIDEO grounds at the
HOST ROOT (archetype B) behind transparent frame scenes.

The faceless assembler mounts frames as sub-comps (track 1). <video> is illegal inside a
sub-comp (guard ②), so per-scene video grounds must live at the index root. This injects a
muted root-level <video class="clip"> for each requested window on a track BELOW the frame
track (so the transparent scene shows it through), just before </div> of #root.

  python inject_root_video.py --index <index.html> --clips '[{"src":"assets/videos/x.mp4","start":0,"duration":8.6}]'
"""
import argparse, json, re
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--clips", required=True, help="JSON list of {src,start,duration,track?}")
    args = ap.parse_args()
    idx = Path(args.index)
    html = idx.read_text(encoding="utf-8")
    clips = json.loads(args.clips)

    tags = []
    for i, c in enumerate(clips):
        track = c.get("track", 0)   # 0 = behind the frame track (1); transparent scene reveals it
        filt = f"filter:{c['filter']};" if c.get("filter") else ""   # ground.grade (cool/warm/darken/…)
        tags.append(
            f'      <video id="rootvid-{i}" class="clip" muted playsinline '
            f'src="{c["src"]}" data-start="{c["start"]}" data-duration="{c["duration"]}" '
            f'data-track-index="{track}" '
            f'style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;{filt}"></video>'
        )
    block = "\n".join(tags)

    # Insert just before the first #root/composition-root closing. The root div is the
    # element carrying data-composition-id="main"; inject before its matching </div>.
    # Simplest robust anchor: the assembler emits the caption/frames inside #root and the
    # root closes before the trailing <script>. Insert right after the root open tag so the
    # videos are the lowest siblings (track 0, painted first / behind higher tracks).
    m = re.search(r'(<div\s+id="root"[^>]*>)', html)
    if not m:
        raise SystemExit("could not find #root open tag in index.html")
    at = m.end()
    html = html[:at] + "\n" + block + "\n" + html[at:]
    idx.write_text(html, encoding="utf-8")
    print(f"injected {len(clips)} root video(s) into {idx.name}:")
    for c in clips:
        print(f"  {c['src']}  @ {c['start']}s for {c['duration']}s (track {c.get('track',0)})")


if __name__ == "__main__":
    main()
