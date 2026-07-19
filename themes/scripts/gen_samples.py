"""Generate the theme × archetype SAMPLE MATRIX: compose one canonical, theme-neutral seed scene per
archetype under every theme, mount each as a seek-able page, and (a sibling node script screenshots it).
The renders power the /themes "Samples" tab (visual specimen gallery) + double as an engine audit — any
cell that doesn't read as its archetype is a registry/layout finding (see docs/ENGINE_AUDIT.md).

Seeds are STATIC (final-state HTML, theme-neutral `var(--…)`, no motion) so a screenshot needs no timeline;
they exercise the archetype's LAYOUT, with neutral placeholder content (the sample shows the theme's
treatment, not a topic). Run:  python -X utf8 themes/scripts/gen_samples.py   then the node shooter.
"""
import json, re, sys
from pathlib import Path

# Windows-python path (this runs under D:\env\nolan\python.exe)
REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "render-service" / "_lab_hyperframes" / "bridge"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BRIDGE))
import compose  # noqa: E402

OUT = REPO / "themes" / "_samples"
OUT.mkdir(parents=True, exist_ok=True)
DUR = 4.0

# ── canonical seeds — one per archetype (static, theme-neutral). type "raw" = hand-authored final-state;
# a block name = the real production block (shows exactly what the pipeline emits).
_CENTERED_HERO = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:0;display:flex;'
    'flex-direction:column;align-items:center;justify-content:center;gap:calc(2.4cqh*var(--density,1));color:var(--text)">'
    '<div style="font-weight:var(--eyebrow-weight,700);'
    'font-size:calc(var(--eyebrow-size,1.15cqw)*var(--type-scale,1));'
    'font-family:var(--eyebrow-font,var(--font-mono)),ui-monospace;line-height:1;'
    'letter-spacing:var(--eyebrow-tracking,.34em);text-transform:var(--eyebrow-transform,uppercase);'
    'color:var(--eyebrow-color,var(--text-2))">By the numbers</div>'
    '<div style="font-weight:var(--hero-num-weight,800);font-style:var(--hero-num-style,normal);font-size:calc(20cqw*var(--type-scale,1));line-height:0.84;font-family:var(--hero-num-font,var(--font-display-en));letter-spacing:var(--hero-num-track,-0.02em)">'
    '73<span style="color:var(--accent)">%</span></div>'
    '<div style="width:8cqw;height:0.5cqh;background:var(--accent);border-radius:2px"></div></section>')

_FRAMED = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:0;display:flex;'
    'align-items:center;justify-content:center;color:var(--text)">'
    '<div style="width:50cqw;height:60cqh;border:var(--bw,2px) solid var(--text);border-radius:var(--r-card,4px);'
    'box-shadow:var(--card-shadow,none);'
    'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:calc(2.2cqh*var(--density,1));'
    'background:var(--surface)">'
    '<div style="font:700 0.95cqw/1 var(--font-mono),ui-monospace;letter-spacing:.32em;'
    'text-transform:uppercase;color:var(--text-2)">Figure 01</div>'
    '<div style="font:600 calc(3.2cqw*var(--type-scale,1))/1.15 var(--font-display-en);font-style:var(--display-style,normal);text-align:center;max-width:36cqw">'
    'The specimen, framed<br>and presented</div></div></section>')

_SWISS_GRID = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:calc(9cqw*var(--density,1));display:grid;'
    'grid-template-columns:1fr 1fr 1fr;grid-auto-rows:1fr;gap:calc(2.4cqw*var(--density,1));color:var(--text)">'
    + "".join(
        '<div style="border-top:2px solid var(--accent);padding-top:1.4cqh">'
        f'<div style="font:800 calc(4.6cqw*var(--type-scale,1))/1 var(--font-display-en)">{i:02d}</div>'
        '<div style="font:600 1cqw/1.35 var(--font-mono),ui-monospace;letter-spacing:.14em;'
        'text-transform:uppercase;color:var(--text-2);margin-top:0.8cqh">Item label</div></div>'
        for i in range(1, 7))
    + '</section>')

_SIDEBAR = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:0;display:flex;'
    'color:var(--text)">'
    '<div style="width:22cqw;background:var(--accent);color:var(--surface);display:flex;'
    'align-items:center;justify-content:center;font:800 calc(13cqw*var(--type-scale,1))/1 var(--font-display-en)">01</div>'
    '<div style="flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 calc(6cqw*var(--density,1));'
    'gap:calc(1.6cqh*var(--density,1))">'
    '<div style="font:700 0.95cqw/1 var(--font-mono),ui-monospace;letter-spacing:.32em;'
    'text-transform:uppercase;color:var(--text-2)">The first step</div>'
    '<div style="font:700 calc(4cqw*var(--type-scale,1))/1.12 var(--font-display-en);font-style:var(--display-style,normal);max-width:52cqw">'
    'A running marker beside the body</div></div></section>')

# a clean, static, theme-robust timeline (all events visible on a spine; no images; respects polarity) —
# the archetype's ideal layout (the Vox `timeline` block is the animated cinematic production variant)
_TIMELINE = (
    '<section class="scene clip" data-track-index="2" style="position:absolute;inset:0;display:flex;'
    'flex-direction:column;justify-content:center;padding:0 calc(9cqw*var(--density,1));color:var(--text)">'
    '<div style="font:700 0.95cqw/1 var(--font-mono),ui-monospace,monospace;letter-spacing:.32em;'
    'text-transform:uppercase;color:var(--text-2)">A short history</div>'
    '<div style="position:relative;margin-top:13cqh;height:0.32cqh;background:var(--accent)">'
    + "".join(
        f'<div style="position:absolute;left:{x}%;top:50%;transform:translate(-50%,-50%);text-align:center">'
        f'<div style="position:absolute;left:50%;bottom:2.4cqh;transform:translateX(-50%);'
        f'font:800 calc(3.4cqw*var(--type-scale,1))/1 var(--font-display-en);font-style:var(--display-style,normal);white-space:nowrap">{yr}</div>'
        '<div style="width:1.5cqw;height:1.5cqw;border-radius:50%;background:var(--accent);'
        'border:0.28cqw solid var(--surface);box-sizing:border-box"></div>'
        f'<div style="position:absolute;left:50%;top:2.4cqh;transform:translateX(-50%);'
        f'font:600 0.9cqw/1.35 var(--font-mono),ui-monospace,monospace;letter-spacing:.08em;'
        f'text-transform:uppercase;color:var(--text-2);white-space:nowrap">{lb}</div></div>'
        for x, yr, lb in [(12, "1969", "First<br>message"), (37, "1983", "TCP / IP"),
                          (62, "1991", "The web"), (87, "2007", "Mobile")])
    + '</div></section>')

SEEDS = {
    "centered-hero":    {"type": "raw", "data": {"html": [_CENTERED_HERO], "tl": []}},
    "editorial-column": {"type": "statement",
                         "data": {"kicker": "The claim", "lines": ["The models are", "getting cheaper", "and better"]}},
    "framed":           {"type": "raw", "data": {"html": [_FRAMED], "tl": []}},
    "swiss-grid":       {"type": "raw", "data": {"html": [_SWISS_GRID], "tl": []}},
    "sidebar":          {"type": "raw", "data": {"html": [_SIDEBAR], "tl": []}},
    "timeline":         {"type": "raw", "data": {"html": [_TIMELINE], "tl": []}},
}

THEMES = sorted(d.name for d in (REPO / "themes").iterdir()
                if d.is_dir() and (d / "theme.json").exists())


def theme_bg(theme):
    try:
        p = json.loads((REPO / "themes" / theme / "theme.json").read_text(encoding="utf-8")).get("preview", {})
        return p.get("shell") or p.get("surface") or "#111"
    except Exception:
        return "#111"


def mount(template, bg):
    inner = re.sub(r"</?template>", "", template)
    inner = inner.replace("https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js", "gsap.min.js")
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<style>html,body{{margin:0;padding:0}}#stage{{position:relative;width:1920px;height:1080px;"
            f"overflow:hidden;background:{bg}}}</style></head><body><div id='stage'>{inner}</div></body></html>")


def main():
    # vendor gsap next to the mounted pages (empty-tl static seeds don't animate, but the compose output
    # registers a timeline; a present gsap makes the screenshotter fast — no per-cell timeout wait).
    import shutil
    for cand in (REPO / ".agents/skills/talking-head-recut/assets/vendor/gsap.min.js",
                 REPO / "agent/skills/talking-head-recut/assets/vendor/gsap.min.js"):
        if cand.exists():
            shutil.copyfile(cand, OUT / "gsap.min.js")
            break
    manifest = []
    for arche, seed in SEEDS.items():
        for theme in THEMES:
            scene = {"id": "s1", "start": 0.0, "dur": DUR, "meta": {"archetype": arche}, **seed}
            tpl = compose.compose_frame(arche, DUR, [scene], theme=theme)
            (OUT / f"{arche}__{theme}.html").write_text(mount(tpl, theme_bg(theme)), encoding="utf-8")
            manifest.append({"archetype": arche, "theme": theme,
                             "html": f"{arche}__{theme}.html", "png": f"{arche}__{theme}.png"})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"composed {len(manifest)} cells ({len(SEEDS)} archetypes × {len(THEMES)} themes) → {OUT}")


if __name__ == "__main__":
    main()
