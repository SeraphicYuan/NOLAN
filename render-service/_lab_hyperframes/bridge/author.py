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
REQUIRED = {"stat": ["items"], "statement": ["lines"], "geo": ["kind"],
            "timeline": ["events"], "raw": ["html", "tl"], "newshead": ["headline"], "collage": ["subjects"],
            "diagram": ["root"], "comparison": ["left", "right"], "juxtaposition": ["left", "right"],
            "gallery": ["images"],
            "carousel": ["images"], "document": ["source"], "lower_third": ["name"],
            "annotate": ["src", "callouts"], "quadrant": ["x", "y"], "venn": ["sets"],
            "sankey": ["source", "targets"], "scale": ["items"], "pie": ["segments"], "funnel": ["stages"],
            "data_table": ["rows"], "trajectory": ["points"], "stream": ["series"], "bar_race": ["series"],
            "spectrum": ["axis", "items"], "cycle": ["steps"], "detail_zoom": ["src", "stops"],
            "hero": ["src", "title"], "chat_thread": ["messages"], "connection_board": ["nodes"], "spans": ["spans"],
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
            if t == "geo" and not d.get("highlight") and not d.get("routes"):
                errs.append(f"{fid}/{sid} (geo): needs `highlight` (regions) or `routes` (arcs) — an empty map shows nothing")
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
            # BLOCK-CHOICE GATE (#Track2): reject a PROVABLY-wrong block — an 'empty comparison' whose data
            # structurally can't be what the block is for (a pie with one slice, non-overlapping spans, a
            # connection_board that is a flow not a web). Deterministic; the author overrides a knowing
            # exception per-scene with data.block_ok=true. SINGLE source of truth (same rules as the sync
            # report + the authoring advisory): nolan.hyperframes.sync._selection_mismatch.
            if not d.get("block_ok"):
                try:
                    from nolan.hyperframes.sync import _selection_mismatch
                    mm = _selection_mismatch(sc)
                    if mm:
                        errs.append(f"{fid}/{sid} ({t}): BLOCK MISMATCH — {mm} "
                                    f"Switch the block, or set data.block_ok=true to override with a reason.")
                except ImportError:
                    pass                                        # bare bridge (no nolan) — the sync report catches it downstream
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


def selection_warnings(spec):
    """#6 — the structural block-selection critic, run at AUTHORING time (not just post-render). The agent
    hears 'these links form a tree — use diagram' / 'sparse data on a long hold — anchor/ground/split' BEFORE
    the render spend. SINGLE implementation: nolan.hyperframes.sync._selection_advice — the exact rules the
    sync report uses (no second dialect to drift). Advisory only; skipped if nolan isn't importable here."""
    try:
        from nolan.hyperframes.sync import _selection_advice
    except Exception:
        return []
    out = []
    for fr in spec.get("frames", []):
        for sc in fr.get("scenes", []):
            adv = _selection_advice(sc)
            if adv:
                out.append(f"{fr.get('id', '?')}/{sc.get('id', '?')} ({sc.get('type')}): {adv}")
    return out


_DATAVIZ_TYPES = {"chart", "stat", "sankey", "pie", "funnel", "quadrant", "cycle", "spectrum", "scale",
                  "spans", "venn", "connection_board"}


def reveal_char_advice(spec):
    """Authoring assist for the reveal-CHARACTER pool (reveal_chars module): reject an UNKNOWN
    `data.reveal_char`, and for a data scene that hasn't set one, SUGGEST a fitting character (meaning →
    motion) the author can accept or override. Advisory (the composer defaults to 'settle' regardless)."""
    try:
        import reveal_chars as rc
    except Exception:
        return []
    out = []
    for fr in spec.get("frames", []):
        for sc in fr.get("scenes", []):
            if sc.get("type") not in _DATAVIZ_TYPES:
                continue
            cur = (sc.get("data", {}) or {}).get("reveal_char")
            if cur is not None and not rc.is_valid(cur):
                out.append(f"{fr.get('id')}/{sc.get('id')}: reveal_char {cur!r} is not a known character "
                           f"{rc.ids()} — the composer will fall back to 'settle'")
            elif cur is None:
                sug = rc.suggest(sc)
                if sug != rc.DEFAULT:                        # only surface a MEANINGFUL (non-default) suggestion
                    out.append(f"{fr.get('id')}/{sc.get('id')} ({sc.get('type')}): consider reveal_char="
                               f"{sug!r} — {rc.resolve(sug)['purpose']}")
    return out


def anchor_warnings(spec):
    """#B authoring-time anchor hygiene (STATIC — no VO alignment yet): flag an `anchor` that LEADS with a
    number. Whisper writes numbers as DIGITS, so a spelled-out number-leading anchor often mis-matches —
    anchor on the CONTEXT words instead. (The full late/closing-anchor check runs at SYNC time, where the
    aligned VO exists.)"""
    try:
        from nolan.hyperframes.sync import _numberish_anchor
    except Exception:
        return []
    out = []
    for fr in spec.get("frames", []):
        for sc in fr.get("scenes", []):
            anc = (sc.get("data", {}) or {}).get("anchor") or sc.get("anchor")
            if isinstance(anc, str) and anc.strip() and _numberish_anchor(anc):
                out.append(f"{fr.get('id')}/{sc.get('id')}: anchor {anc!r} leads with a NUMBER — anchor on the "
                           f"CONTEXT words beside it (Whisper transcribes numbers as digits, so this may mis-match)")
    return out


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

    sels = selection_warnings(spec)                     # #6: block-selection advice at authoring time
    if sels:
        print("  ⚠ block-selection advice (the data suggests a better-fitting block or a fix — "
              "advisory, not a gate):")
        for s in sels:
            print(f"      · {s}")

    rcs = reveal_char_advice(spec)                       # reveal-CHARACTER validation + suggestion
    if rcs:
        print("  ◆ reveal-character (data.reveal_char — the reveal's motion personality; advisory):")
        for s in rcs:
            print(f"      · {s}")

    ancs = anchor_warnings(spec)                         # #B anchor hygiene (static): number-leading anchors
    if ancs:
        print("  ◆ anchor hygiene (anchor the OPENING of a beat's topic, not a number/closing aside):")
        for s in ancs:
            print(f"      · {s}")

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
