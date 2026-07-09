"""NOLAN -> HyperFrames asset bridge: RESOLVE (krea2/ComfyUI or stock) -> INJECT (project assets/ + ledger).

Video-workflow-AGNOSTIC by design: it targets the two genuinely shared seams the
skill survey identified — the project `assets/<basename>` landing dir (which every
HyperFrames assembler + the core clip contract resolve `src="assets/..."` against)
and, optionally, media-use's `.media/` ledger via `resolve --from`. It does NOT
touch any workflow's per-scene plan fields; a thin per-workflow "plan-writer" adapter
does that separately.

Usage:
  python resolve_inject.py --intents intents.json --project <hyperframes_project_dir> [--ids id1,id2] [--style ",Dark Moody Atmosphere"]
"""
import argparse, asyncio, json
from pathlib import Path


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--intents", required=True)
    ap.add_argument("--project", required=True, help="HyperFrames project dir (has assets/)")
    ap.add_argument("--ids", default="", help="comma-separated subset of intent ids")
    ap.add_argument("--style", default=",Dark Moody Atmosphere", help="krea2 Fooocus style (leading comma)")
    ap.add_argument("--width", type=int, default=1344, help="gen width (lower = less VRAM; grounds get object-fit:cover)")
    ap.add_argument("--height", type=int, default=768, help="gen height (16:9-ish)")
    args = ap.parse_args()

    from nolan.config import load_config
    from nolan.workflow_registry import get_registry

    intents = json.load(open(args.intents, encoding="utf-8"))
    if args.ids:
        want = set(s.strip() for s in args.ids.split(",") if s.strip())
        intents = [i for i in intents if i["id"] in want]
    proj = Path(args.project)
    assets = proj / "assets"          # THE agnostic landing dir
    assets.mkdir(parents=True, exist_ok=True)

    cfg = load_config()
    client, entry = get_registry().build_client("krea2-style-select", cfg, style=args.style,
                                                width=args.width, height=args.height)
    if not await client.check_connection():
        raise SystemExit("ComfyUI not reachable — is it running on 127.0.0.1:8080?")
    print(f"krea2 client: workflow={getattr(entry,'name',None)} style={args.style} size={client.width}x{client.height}")

    manifest_path = proj / "bridge_assets.json"
    manifest = json.load(open(manifest_path, encoding="utf-8")) if manifest_path.exists() else {}
    for it in intents:
        out = assets / f"bg_{it['id']}.png"
        print(f"  resolve {it['id']} -> {out.name}")
        await client.generate(it["prompt"], out)
        ok = out.exists()
        manifest[it["id"]] = {
            "asset": f"assets/bg_{it['id']}.png", "ok": ok,
            "frame": it.get("frame"), "scene": it.get("scene"),
            "treatment": it.get("treatment"),
            "provenance": {"source": "nolan:comfyui:krea2-style-select", "style": args.style,
                            "prompt": it["prompt"]},
        }
        print(f"    {'OK' if ok else 'FAIL'} {out}")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {manifest_path}")


if __name__ == "__main__":
    asyncio.run(main())
