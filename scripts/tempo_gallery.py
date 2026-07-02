"""Build a served gallery that ties #1 (knowledge assets) + #2 (tempo arc) together on the
real Homer project: per beat — the arc energy, the transition/motion the arc chose, the
knowledge-named real artwork retrieved, and (for a few) a tempo-driven motion clip.

Writes into projects/_library/_broll_generated/ (served at /broll-gen/tempo_homer.html)."""
import io, sys
from pathlib import Path
sys.path.insert(0, "src")
from PIL import Image
from nolan.config import load_config
from nolan.llm import create_text_llm
from nolan.script_context import ScriptContext
from nolan.tempo_plan import design_tempo, motion_for_tempo
from nolan.knowledge_query import expand_queries
from nolan.image_search import ImageSearchClient, ImageScorer
from nolan import still_motion

RENDER_BEATS = {0, 4, 7}          # low / high / low — show the tempo range as motion clips
OUT = Path("projects/_library/_broll_generated/tempo_homer")
OUT.mkdir(parents=True, exist_ok=True)

cfg = load_config()
llm = create_text_llm(cfg)
ctx = ScriptContext.load("homer")
tempo = design_tempo(ctx, llm=llm)
src = cfg.image_sources
client = ImageSearchClient(pexels_api_key=src.pexels_api_key, pixabay_api_key=src.pixabay_api_key,
                          smithsonian_api_key=src.smithsonian_api_key, keys=src.provider_keys())
dl = ImageScorer()

def fetch_asset(phrases, stem):
    for ph in phrases[:6]:
        try:
            hits = client.search_assets(ph, media_type="image", max_results=4)
        except Exception:
            hits = []
        for h in hits:
            data = dl._download_image(h.url)
            if not data:
                continue
            try:
                im = Image.open(io.BytesIO(data)).convert("RGB")
            except Exception:
                continue
            if im.width < 400 or im.height < 300:
                continue
            p = OUT / f"{stem}.jpg"
            im.save(p, "JPEG", quality=86)
            return p, (h.title or ph)[:70], ph
    return None, "", ""

rows = []
for bt in tempo.beats:
    print(f"beat {bt.idx}: {bt.title[:40]} e={bt.energy:.2f}")
    kq = expand_queries(ctx, bt.idx, llm=llm, kind="artwork", n=5)
    asset_p, asset_title, used_q = fetch_asset(kq.all_queries(), f"b{bt.idx}")
    clip_name = ""
    if bt.idx in RENDER_BEATS and asset_p:
        mid, dur = motion_for_tempo(bt, "image")
        try:
            out = OUT / f"b{bt.idx}_motion.mp4"
            still_motion.render_still(str(asset_p.resolve()), mid, out, dur)
            clip_name = out.name
            print(f"   rendered {mid} {dur}s -> {clip_name}")
        except Exception as ex:
            print("   render failed:", ex)
    rows.append({"bt": bt, "asset": asset_p.name if asset_p else "", "title": asset_title,
                 "q": used_q, "clip": clip_name,
                 "named": [a.title for a in kq.named_assets[:3]]})

# ---- render HTML ----
def bar(e):
    w = int(e * 100)
    col = "#f2c14e" if e >= 0.7 else "#7aa2f7" if e >= 0.5 else "#6b7280"
    return f'<div class="bar"><div class="fill" style="width:{w}%;background:{col}"></div><span>{e:.2f}</span></div>'

cards = []
for r in rows:
    bt = r["bt"]
    media = (f'<video src="tempo_homer/{r["clip"]}" controls autoplay muted loop playsinline></video>'
             if r["clip"] else
             (f'<img src="tempo_homer/{r["asset"]}">' if r["asset"] else '<div class="noimg">no asset</div>'))
    named = " · ".join(r["named"])
    cards.append(f'''<div class="card">
      <div class="media">{media}</div>
      <div class="body">
        <div class="ttl">{bt.idx+1}. {bt.title}</div>
        {bar(bt.energy)}
        <div class="lv"><span class="chip">trans: {bt.transition}</span>
          <span class="chip">motion: {bt.motion_speed}</span>
          <span class="chip">{bt.pace_dir}</span></div>
        <div class="asset">▸ {r["title"] or "—"}</div>
        <div class="named">knowledge: {named}</div>
      </div></div>''')

html = f'''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tempo + Knowledge — Homer</title><style>
:root{{color-scheme:dark}} body{{margin:0;background:#0d0d10;color:#e8e8ea;
font:15px/1.5 -apple-system,"Segoe UI",Roboto,sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:30px 20px 60px}}
h1{{font-size:23px;margin:0 0 4px}} .sub{{color:#9a9aa2;margin:0 0 24px;font-size:14px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:20px}}
.card{{background:#16161b;border:1px solid #26262e;border-radius:12px;overflow:hidden}}
.media{{aspect-ratio:16/10;background:#000}} .media img,.media video{{width:100%;height:100%;object-fit:cover;display:block}}
.noimg{{display:flex;align-items:center;justify-content:center;height:100%;color:#555}}
.body{{padding:12px 14px 14px}} .ttl{{font-size:14px;font-weight:600;margin-bottom:8px}}
.bar{{position:relative;height:18px;background:#23232b;border-radius:5px;overflow:hidden;margin-bottom:8px}}
.bar .fill{{height:100%}} .bar span{{position:absolute;right:6px;top:0;font-size:11px;line-height:18px;color:#000;font-weight:700}}
.lv{{margin-bottom:6px}} .chip{{display:inline-block;font-size:11px;padding:2px 7px;border-radius:999px;background:#2a2a34;color:#c7c7d0;margin:2px 4px 0 0}}
.asset{{font-size:13px;color:#cdcdd4;margin-top:4px}} .named{{font-size:11px;color:#7d7d86;margin-top:3px}}
@media(max-width:520px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<h1>Editorial rhythm + knowledge assets — Homer</h1>
<p class="sub">One whole-script pass over the real Homer plan. Per beat: the <b>energy</b> the arc assigned,
the <b>transition</b> &amp; <b>motion</b> it chose (was: 100% flat hard cuts), and the <b>specific real artwork</b>
the knowledge bridge named &amp; retrieved. Beats 1/5/8 show tempo as an actual motion clip (slow breathe → fast push → slow breathe).</p>
<div class="grid">{"".join(cards)}</div></div></body></html>'''

(Path("projects/_library/_broll_generated/tempo_homer.html")).write_text(html, encoding="utf-8")
print("\nWROTE gallery ->", "projects/_library/_broll_generated/tempo_homer.html")
print("beats:", len(rows), "| assets:", sum(1 for r in rows if r["asset"]), "| clips:", sum(1 for r in rows if r["clip"]))
