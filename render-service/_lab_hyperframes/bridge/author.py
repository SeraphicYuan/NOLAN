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
THEMES_DIR = Path(__file__).resolve().parents[3] / "themes"       # repo_root/themes (matches compose._theme_vars)


def theme_exists(theme) -> bool:
    return bool(theme) and (THEMES_DIR / str(theme) / "tokens.css").exists()


def resolve_theme(spec, cli_theme=None, out_dir=None):
    """Which NOLAN theme this comp renders in. Priority: --theme > spec['theme'] > the comp's
    hyperframes.json['theme'] > the Vox house default. Returns (theme, source, ok). This is the seam
    that lets a compose-first essay use ANY of the themes/ registry instead of hardcoded Vox."""
    theme, source = None, ""
    if cli_theme:
        theme, source = cli_theme, "--theme"
    elif spec.get("theme"):
        theme, source = spec["theme"], "spec.theme"
    elif out_dir:
        try:
            comp = Path(out_dir).resolve().parents[1]              # <comp>/compositions/frames -> <comp>
            hj = json.load(open(comp / "hyperframes.json", encoding="utf-8"))
            if hj.get("theme"):
                theme, source = hj["theme"], "hyperframes.json"
        except Exception:
            pass
    if not theme:
        return "highlighter-editorial", "default", True
    return theme, source, theme_exists(theme)

# minimum non-empty fields per scene type — the accept gate (schema lives in catalog.json)
REQUIRED = {"stat": ["items"], "statement": ["lines"], "geo": ["kind", "highlight"],
            "timeline": ["events"], "raw": ["html", "tl"], "newshead": ["headline"], "collage": ["subjects"],
            "diagram": ["root"], "comparison": ["left", "right"], "juxtaposition": ["left", "right"],
            "gallery": ["images"],
            "carousel": ["images"], "document": ["source"], "lower_third": ["name"],
            "annotate": ["src", "callouts"], "quadrant": ["x", "y"], "venn": ["sets"],
            "sankey": ["source", "targets"], "scale": ["items"], "pie": ["segments"], "funnel": ["stages"],
            "spectrum": ["axis", "items"], "cycle": ["steps"],
            "chart": ["series"], "code": ["code"], "social_card": ["platform"]}


# Seek-safety lint for `raw` (bespoke) scenes: author.py otherwise gates STRUCTURE only, so a hand-authored
# scene with a non-deterministic / time-based / repeating tween would pass the composer gate and only break
# later at assembly. These patterns unambiguously break the ONE-paused-timeline seek model, so reject them here
# (the whole frame reverts). Templated blocks are seek-safe by construction; this only inspects `raw` html/tl.
_RAW_SEEK_FORBIDDEN = [
    ("Math.random", "non-deterministic Math.random()"),
    ("Date.now", "time-based Date.now()"),
    ("new Date(", "time-based new Date()"),
    ("performance.now", "time-based performance.now()"),
    ("yoyo:", "a yoyo (repeating) tween"),
    ("yoyo :", "a yoyo (repeating) tween"),
    ("repeat:-1", "an infinite repeat"),
    ("repeat: -1", "an infinite repeat"),
]


def _raw_seek_errors(fid, sid, data):
    """Return seek-safety violations in a raw scene's html/tl strings (transforms/opacity + deterministic only)."""
    frag = data.get("html") or []
    if isinstance(frag, str):
        frag = [frag]
    blob = " ".join(str(x) for x in frag) + " " + " ".join(str(x) for x in (data.get("tl") or []))
    return [f"{fid}/{sid} (raw): {why} — not seek-safe (the frame is ONE paused, seeked timeline)"
            for needle, why in _RAW_SEEK_FORBIDDEN if needle in blob]


def validate_spec(spec):
    errs = []
    templ = CATALOG["scene_templates"]
    for fr in spec.get("frames", []):
        fid = fr.get("id", "?")
        if "dur" not in fr:
            errs.append(f"{fid}: frame missing dur")
        ftr = fr.get("transition_out")                          # FRAME-level clip transition INTO the next frame
        if isinstance(ftr, dict) and ftr.get("kind"):           # (distinct from a SCENE's within-frame transition_out)
            try:
                from nolan.hyperframes.transitions import transition_kinds
                kinds = transition_kinds()
                if ftr["kind"] not in kinds:
                    errs.append(f"{fid}: frame transition_out.kind {ftr['kind']!r} not a stocked clip "
                                f"transition {sorted(kinds)}")
            except ImportError:                                 # bare bridge — executor resolves against the manifest
                pass
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
            if t == "raw":
                errs.extend(_raw_seek_errors(fid, sid, d))
            tr = sc.get("transition_out")
            if tr is not None:
                tk = tr.get("kind") if isinstance(tr, dict) else None
                if tk not in CATALOG.get("transitions", {}):
                    errs.append(f"{fid}/{sid}: transition_out.kind {tk!r} not in catalog "
                                f"{sorted(k for k in CATALOG.get('transitions', {}) if k != '_doc')}")
            g = d.get("ground")                                 # effects umbrella: gate ground.treatments vs the registry
            if isinstance(g, dict) and g.get("treatments") is not None:
                try:
                    from nolan.effects.registry import validate_treatments
                    errs.extend(f"{fid}/{sid}: {e}" for e in validate_treatments(g["treatments"]))
                except ImportError:                             # bare compose context — executor is lenient (skips unknown)
                    pass
            if t == "geo" and d.get("kind") not in ("us", "world"):
                errs.append(f"{fid}/{sid} (geo): kind must be 'us' or 'world'")
            if t == "statement" and d.get("operative") and not any(d["operative"] in ln for ln in d.get("lines", [])):
                errs.append(f"{fid}/{sid} (statement): operative {d['operative']!r} not found in any line")
            if t == "comparison":                               # comparison is a VISUAL contrast — sides are image|video
                for sk in ("left", "right"):
                    st = (d.get(sk) or {}).get("type", "image")
                    if st not in ("image", "video"):
                        errs.append(f"{fid}/{sid} (comparison): {sk}.type {st!r} is not visual. Comparison sides "
                                    f"must be image|video (a title/kicker and a `stat` number ride ONLY as an "
                                    f"OVERLAY). For a text-vs-text / stat-vs-stat / stat-vs-text contrast use "
                                    f"`juxtaposition`.")
            if t == "juxtaposition":                            # juxtaposition is the NON-visual dialectic — sides are text|stat
                for sk in ("left", "right"):
                    st = (d.get(sk) or {}).get("type", "text")
                    if st not in ("text", "stat"):
                        errs.append(f"{fid}/{sid} (juxtaposition): {sk}.type {st!r} — sides must be text|stat. "
                                    f"For an image/video contrast use `comparison`.")
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
    ap.add_argument("--theme", help="theme slug under themes/ (else spec.theme / the comp's hyperframes.json / Vox default)")
    args = ap.parse_args()
    spec = json.load(open(args.spec, encoding="utf-8"))

    # Asset base for compose-time measurement (spotlight's clear mode reads the cutout's pixels). Derived
    # from --out-dir (<comp>/compositions/frames -> <comp>); unset under --validate-only so the gate stays
    # pure and blocks fall back deterministically.
    compose._ASSET_BASE = None
    if args.out_dir:
        try:
            compose._ASSET_BASE = Path(args.out_dir).resolve().parents[1]
        except Exception:
            compose._ASSET_BASE = None

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

    theme, tsrc, tok = resolve_theme(spec, args.theme, args.out_dir)
    if not tok:
        print(f"  ⚠ theme {theme!r} (via {tsrc}) not found under themes/ — using highlighter-editorial")
        theme, tsrc = "highlighter-editorial", "fallback"
    print(f"  theme: {theme} (via {tsrc})")

    warns = theme_layout_audit(spec, themes=list(dict.fromkeys(FONT_EXTREME_THEMES + [theme])))
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
        html = compose.compose_frame(fr["id"], fr["dur"], fr["scenes"], theme=theme)
        (out / f'{fr["id"]}.html').write_text(html, encoding="utf-8")
        print(f'  built {fr["id"]}.html — {len(fr["scenes"])} scenes')


if __name__ == "__main__":
    main()
