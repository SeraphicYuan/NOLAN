"""NOLAN -> HyperFrames asset bridge, Phase 1.5: COLLECT -> CAPTION -> INVENTORY.

"NOLAN is the camera." Fans out NOLAN's whole acquisition stack (stock image x N
providers + stock VIDEO + — optionally — krea2 gen), freezes a candidate POOL into a
HyperFrames project's capture/assets/, vision-captions each with OpenRouter qwen-VL, and
writes capture/extracted/asset-descriptions.md — the SAME inventory shape the capture-based
workflows (product-launch / website) already select `asset_candidates` from. So HyperFrames
keeps its own selection judgment; NOLAN just fills the pool.

  python pool.py --needs needs.json --project <hyperframes_project_dir> [--per 3] [--no-caption]

needs.json: [ { "id","query","media_type":"image|video","sources":[...]?,"n":int? }, ... ]
"""
import argparse, asyncio, json, os
from pathlib import Path


def _client(cfg):
    from nolan.image_search import ImageSearchClient
    s = cfg.image_sources
    return ImageSearchClient(
        pexels_api_key=s.pexels_api_key or None,
        pixabay_api_key=s.pixabay_api_key or None,
        smithsonian_api_key=getattr(s, "smithsonian_api_key", "") or None,
        keys={
            "europeana": getattr(s, "europeana_api_key", ""),
            "dpla": getattr(s, "dpla_api_key", ""),
            "flickr": getattr(s, "flickr_api_key", ""),
            "unsplash": getattr(s, "unsplash_access_key", ""),
            "rijksmuseum": getattr(s, "rijksmuseum_api_key", ""),
            "harvard": getattr(s, "harvard_api_key", ""),
            "coverr": getattr(s, "coverr_api_key", ""),
        },
    )


def _valid_image(path: Path) -> bool:
    """Reject non-decodable downloads (HTML error pages saved as .jpg, truncated files).
    Chrome renders AVIF/WebP-in-.jpg fine, and Pillow decodes them, so this only culls
    genuinely broken files — the pool-hygiene gap the first run surfaced."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.load()
        return True
    except Exception:
        return False


def _download_video(result, out_path: Path) -> bool:
    import urllib.request
    from nolan.asset_gate import check_candidate
    gate = check_candidate(result, tier="stock")
    if not gate.ok:
        print(f"      video gate-refused: {'; '.join(gate.reasons)}")
        return False
    req = urllib.request.Request(result.url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Referer": "https://www.google.com/"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(out_path, "wb") as f:
            f.write(r.read())
        return out_path.stat().st_size > 10000
    except Exception as e:
        print(f"      video download failed: {type(e).__name__}: {e}")
        return False


def collect(cfg, needs, assets_dir: Path, per: int):
    client = _client(cfg)
    pool = []
    for need in needs:
        mt = need.get("media_type", "image")
        n = int(need.get("n", per))
        print(f"  [{need['id']}] {mt} search: {need['query']!r}")
        try:
            results = client.search_assets(need["query"], media_type=mt,
                                           sources=need.get("sources"), max_results=n * 3)
        except Exception as e:
            print(f"    search error: {type(e).__name__}: {e}"); continue
        got = 0
        for i, res in enumerate(results):
            if got >= n:
                break
            ext = ".mp4" if mt == "video" else ".jpg"
            base = f"{need['id']}_{got:02d}{ext}"
            out = assets_dir / ("videos/" + base if mt == "video" else base)
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                if mt == "video":
                    res = client.resolve_video(res) or res
                    if not res.url:
                        continue
                    ok = _download_video(res, out)
                else:
                    res = client.resolve_asset(res)
                    ok = client.download_image(res, out) is not None
                    if ok and not _valid_image(out):   # cull HTML/truncated downloads
                        out.unlink(missing_ok=True); ok = False
                        print(f"    x {base}: not a decodable image — rejected")
            except Exception as e:
                print(f"    dl error: {type(e).__name__}: {e}"); ok = False
            if ok:
                got += 1
                pool.append({"id": need["id"], "file": ("videos/" + base if mt == "video" else base),
                             "media_type": mt, "query": need["query"],
                             "source": res.source, "source_url": res.source_url,
                             "photographer": res.photographer, "license": res.license,
                             "width": res.width, "height": res.height,
                             "duration": res.duration, "caption": ""})
                print(f"    + {out.name}  ({res.source})")
        if got == 0:
            print(f"    (nothing downloaded for {need['id']})")
    return pool


async def caption(cfg, pool, assets_dir: Path):
    from nolan.vision import create_vision_provider
    from nolan.evoke_broll import _vision_config
    prov = create_vision_provider(_vision_config(cfg))
    prompt = ("Describe this image for a video editor's asset inventory in ONE line "
              "(<=24 words): concrete subject, setting, mood, dominant palette, and whether "
              "it is photoreal or illustration. No preamble.")
    sem = asyncio.Semaphore(4)

    async def cap(item):
        if item["media_type"] == "video":
            # caption the poster if we have one on disk; else describe from query
            item["caption"] = f"[video] {item['query']} (stock clip, {item.get('duration') or '?'}s)"
            return
        p = assets_dir / item["file"]
        async with sem:
            try:
                item["caption"] = (await prov.describe_image(p, prompt)).strip().replace("\n", " ")
            except Exception as e:
                item["caption"] = f"({item['query']})"
                print(f"    caption failed {item['file']}: {type(e).__name__}")
    await asyncio.gather(*(cap(it) for it in pool))
    return pool


def write_inventory(pool, project: Path):
    ex = project / "capture" / "extracted"
    ex.mkdir(parents=True, exist_ok=True)
    lines = ["# Asset descriptions (NOLAN pool → HyperFrames inventory)\n",
             "Candidate assets collected by the NOLAN acquisition fan-out. The storyboard step",
             "SELECTS from these into per-frame `asset_candidates` — HyperFrames keeps selection.\n"]
    for it in pool:
        path = f"assets/{it['file']}"
        tag = " [video]" if it["media_type"] == "video" else ""
        cred = f"{it.get('source') or '?'}" + (f" / {it['photographer']}" if it.get("photographer") else "")
        lines.append(f"- `{path}`{tag} — {it['caption']}  _(need: {it['id']}; {cred}; {it.get('license') or 'license?'})_")
    (ex / "asset-descriptions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (project / "pool.json").write_text(json.dumps(pool, indent=2), encoding="utf-8")
    print(f"  inventory: {len(pool)} assets → capture/extracted/asset-descriptions.md + pool.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--needs", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--per", type=int, default=3)
    ap.add_argument("--no-caption", action="store_true")
    args = ap.parse_args()
    from nolan.config import load_config
    cfg = load_config()
    needs = json.load(open(args.needs, encoding="utf-8"))
    project = Path(args.project)
    assets_dir = project / "capture" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    print("COLLECT")
    pool = collect(cfg, needs, assets_dir, args.per)
    if pool and not args.no_caption:
        print("CAPTION (OpenRouter qwen-VL)")
        asyncio.run(caption(cfg, pool, assets_dir))
    write_inventory(pool, project)


if __name__ == "__main__":
    main()
