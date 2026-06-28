"""Embed a theme's web fonts as base64 @font-face into article/fonts.css, so the
built single-file HTML is fully offline (no remote Google Fonts <link>).

Usage (run from the article workspace, after scaffold):
    python3 <skill>/scripts/embed-theme-fonts.py --css-url "<google css2 url>"
    # then add  import "./fonts.css";  to article/main.tsx (after reacticle/styles.css)

The css2 URL lists the theme's families/weights. Build it from the theme's
--ra-font-heading / --ra-font-body / --ra-font-mono primary families. Examples:
  freddie:  family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Hanken+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@400;500
  press:    family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=Source+Serif+4:opsz,wght@8..60,400&family=JetBrains+Mono:wght@400;500
  (themes whose fonts are system stacks — e.g. tufte/Georgia — need no embedding.)

Only the latin subset is embedded (keeps size ~300-450 KB). Offline-first: the
output contains only data: URIs, no remote references.
"""
import argparse, base64, os, re, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120 Safari/537.36"}
DEFAULT = ("https://fonts.googleapis.com/css2?"
           "family=Fraunces:opsz,wght@9..144,400;9..144,600&"
           "family=Hanken+Grotesk:wght@400;500;700&"
           "family=JetBrains+Mono:wght@400;500&display=swap")


def fetch(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--css-url", default=DEFAULT, help="Google Fonts css2 URL for the theme's families")
    ap.add_argument("--out", default=os.path.join("article", "fonts.css"))
    ap.add_argument("--subset", default="latin", help="unicode subset comment to keep (default: latin)")
    args = ap.parse_args()

    css = fetch(args.css_url).decode("utf-8")
    blocks = re.split(r"(/\*[^*]+\*/)", css)
    out, kept = [], 0
    for i in range(1, len(blocks) - 1, 2):
        if blocks[i].strip() != f"/* {args.subset} */":
            continue
        m = re.search(r"@font-face\s*{[^}]*}", blocks[i + 1], re.S)
        if not m:
            continue
        face = m.group(0)
        u = re.search(r"url\((https://[^)]+\.woff2)\)", face)
        if not u:
            continue
        b64 = base64.b64encode(fetch(u.group(1))).decode("ascii")
        face = re.sub(r"src:\s*url\(https://[^)]+\)\s*format\('woff2'\)",
                      f"src: url(data:font/woff2;base64,{b64}) format('woff2')", face)
        out.append(face)
        kept += 1

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("/* Self-contained theme fonts (subset: %s), embedded base64 — offline-first. */\n" % args.subset)
        f.write("\n".join(out) + "\n")
    print(f"embedded {kept} font-faces -> {args.out} ({os.path.getsize(args.out)//1024} KB)")
    print("next: ensure article/main.tsx has  import \"./fonts.css\";  after reacticle/styles.css")


if __name__ == "__main__":
    main()
