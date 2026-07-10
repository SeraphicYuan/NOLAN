"""Thin NOLAN author step — the compose-first / bespoke-fallback wiring.

Flow (NOLAN module contract: draft -> validate -> accept):
  1. an AGENT reads a storyboard + catalog.json and PROPOSES a scenes_spec — picking a
     composer template for every beat it can, and only authoring a bespoke `raw` scene when
     nothing fits (see AUTHOR_PROMPT.md);
  2. THIS script is the deterministic gate: it validates the proposal against the catalog
     (loud failure on any drift), then builds the frames via compose.py.

  python author.py --spec scenes_spec.json --out-dir <project>/compositions/frames  # gate + build
  python author.py --spec scenes_spec.json --validate-only                          # gate only
"""
import argparse, json, sys
from pathlib import Path
import compose

HERE = Path(__file__).parent
CATALOG = json.load(open(HERE / "catalog.json", encoding="utf-8"))

# minimum non-empty fields per scene type — the accept gate (schema lives in catalog.json)
REQUIRED = {"stat": ["items"], "statement": ["lines"], "geo": ["kind", "highlight"],
            "timeline": ["events"], "raw": ["html", "tl"], "newshead": ["headline"], "collage": ["subjects"],
            "diagram": ["root"], "comparison": ["left", "right"], "gallery": ["images"],
            "carousel": ["images"], "document": ["source"], "lower_third": ["name"],
            "chart": ["series"], "code": ["code"], "social_card": ["platform"]}


def validate_spec(spec):
    errs = []
    templ = CATALOG["scene_templates"]
    for fr in spec.get("frames", []):
        fid = fr.get("id", "?")
        if "dur" not in fr:
            errs.append(f"{fid}: frame missing dur")
        for sc in fr.get("scenes", []):
            sid = sc.get("id", "?")
            t = sc.get("type")
            if t not in templ:
                errs.append(f"{fid}/{sid}: type {t!r} not in catalog {sorted(templ)}")
                continue
            for k in ("id", "start", "dur"):
                if k not in sc:
                    errs.append(f"{fid}/{sid}: missing {k}")
            d = sc.get("data", {})
            for req in REQUIRED.get(t, []):
                v = d.get(req)
                if v is None or (isinstance(v, (list, str)) and len(v) == 0):
                    errs.append(f"{fid}/{sid} ({t}): data.{req} required and non-empty")
            tr = sc.get("transition_out")
            if tr is not None:
                tk = tr.get("kind") if isinstance(tr, dict) else None
                if tk not in CATALOG.get("transitions", {}):
                    errs.append(f"{fid}/{sid}: transition_out.kind {tk!r} not in catalog "
                                f"{sorted(k for k in CATALOG.get('transitions', {}) if k != '_doc')}")
            if t == "geo" and d.get("kind") not in ("us", "world"):
                errs.append(f"{fid}/{sid} (geo): kind must be 'us' or 'world'")
            if t == "statement" and d.get("operative") and not any(d["operative"] in ln for ln in d.get("lines", [])):
                errs.append(f"{fid}/{sid} (statement): operative {d['operative']!r} not found in any line")
    return errs


# Font-metric extremes across the roster — a wide/heavy display font vs a narrow one. A block that
# survives both survives the rest, so the cross-theme audit only needs these two.
FONT_EXTREME_THEMES = ["bold-signal", "highlighter-editorial"]


def theme_layout_audit(spec, themes=None):
    """STUB — cross-theme layout-robustness gate. The one real theme risk is a wider theme font
    overflowing a fixed box (a token can move text WIDTH). Composes each frame under the metric-
    extreme themes and, WHEN FULLY WIRED, runs `hyperframes inspect`'s layout audit
    (container_overflow / content_overlap / clipped_text), failing on any hit.

    Today (stub) it only verifies the composer emits theme tokens + the fit primitive on themed
    output; the render-based `inspect` audit is TODO. Returns advisory warnings (non-blocking)."""
    themes = themes or FONT_EXTREME_THEMES
    warns = []
    for fr in spec.get("frames", []):
        for theme in themes:
            html = compose.compose_frame(fr["id"], fr["dur"], fr["scenes"], theme=theme)
            if "--accent" not in html:
                warns.append(f"{fr.get('id','?')}@{theme}: theme tokens not injected")
            if 'data-fit-w="' not in html:   # element-attr form (the injected fit SCRIPT also says data-fit)
                warns.append(f"{fr.get('id','?')}@{theme}: no fit-tagged bounded text "
                             "(a wider-font theme could overflow — tag hero/row text data-fit)")
            # TODO(theme-fit gate): write html into a scratch project, run `npx hyperframes inspect .`
            #   across seeked frames, parse container_overflow/content_overlap/clipped_text -> errors.
    return warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out-dir")
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args()
    spec = json.load(open(args.spec, encoding="utf-8"))

    errs = validate_spec(spec)
    if errs:
        print("SPEC REJECTED — proposal does not satisfy the catalog:")
        for e in errs:
            print("  ✗", e)
        sys.exit(1)

    # coverage report: how much the agent expressed with templates vs bespoke
    from collections import Counter
    counts = Counter(sc["type"] for fr in spec["frames"] for sc in fr["scenes"])
    total = sum(counts.values())
    bespoke = counts.get("raw", 0)
    print(f"OK — spec validates: {len(spec['frames'])} frame(s), {total} scenes "
          f"({total - bespoke} templated, {bespoke} bespoke) — {dict(counts)}")

    warns = theme_layout_audit(spec)
    if warns:
        print("THEME-FIT audit (advisory) — cross-theme layout robustness:")
        for w in warns:
            print("  ⚠", w)

    if args.validate_only:
        return
    if not args.out_dir:
        sys.exit("--out-dir required to build")
    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    for fr in spec["frames"]:
        html = compose.compose_frame(fr["id"], fr["dur"], fr["scenes"])
        (out / f'{fr["id"]}.html').write_text(html, encoding="utf-8")
        print(f'  built {fr["id"]}.html — {len(fr["scenes"])} scenes')


if __name__ == "__main__":
    main()
