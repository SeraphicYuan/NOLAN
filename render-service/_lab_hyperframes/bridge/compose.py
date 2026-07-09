"""Deterministic scene composer — the "block kit" (Vox / highlighter-editorial).

Finding: HyperFrames registry blocks can't be mounted N times as ANIMATED instances
(same element ids + same window.__timelines key collide across clones — smoke-tested:
2nd instance renders blank). So the reusable modules are stamped at BUILD time here,
with per-scene id prefixes + one merged timeline — the same output the frame-workers
hand-wrote, generated in milliseconds instead of ~16 min/frame of LLM authoring.

Three reusable block-templates:  media_ground · stat_lockup · highlight_statement
Driver: compose_frame(frame_id, scenes) -> a <template>-wrapped frame sub-composition.

  python compose.py --spec scenes.json --out-dir <project>/compositions/frames
"""
import argparse, json, html, re
from pathlib import Path

FONTS = ("@import url('https://fonts.googleapis.com/css2?family=Libre+Franklin:ital,wght@0,600;0,700;0,800;0,900;1,600&"
         "family=Lora:ital,wght@0,400;0,600;0,700;1,500&family=UnifrakturMaguntia&family=Inter:wght@500;600&display=swap');")
CSS = """
#root{position:absolute;inset:0;width:1920px;height:1080px;container-type:size;overflow:hidden;
  font-family:"Libre Franklin",sans-serif;background:transparent;}
.gnd{position:absolute;inset:0;background-size:cover;background-position:center;transform-origin:50% 50%;will-change:transform;}
.paper-gnd{position:absolute;inset:0;}
.scrim{position:absolute;inset:0;pointer-events:none;}
.kick{position:absolute;top:6.4cqw;left:5.5cqw;font-family:"Inter",sans-serif;font-weight:600;font-size:0.9cqw;
  letter-spacing:0.14em;text-transform:uppercase;opacity:0;}
.stmt{position:absolute;left:5.5cqw;bottom:16cqh;max-width:80cqw;font-weight:800;font-size:4.6cqw;line-height:1.08;
  letter-spacing:-0.012em;}
.stmt .ln{display:block;opacity:0;}
.hlwrap{position:relative;display:inline-block;}
.hlblock{position:absolute;left:-0.08em;right:-0.08em;top:0.06em;bottom:0.08em;background:#FFF200;transform:scaleX(0);
  transform-origin:left center;z-index:-1;}
.capbar{position:absolute;left:5.5cqw;bottom:9cqh;background:#F1F3F2;color:#2B2D2C;padding:0.5cqw 1.1cqw;
  font-family:"Inter",sans-serif;font-weight:600;font-size:0.82cqw;letter-spacing:0.1em;text-transform:uppercase;opacity:0;}
.slrow{position:absolute;left:5.5cqw;top:34cqh;display:flex;gap:4cqw;align-items:flex-start;}
.slitem{display:flex;flex-direction:column;min-width:18cqw;}
.slnumwrap{position:relative;display:inline-block;}
.slnum{font-weight:900;letter-spacing:-0.03em;line-height:1;font-variant-numeric:tabular-nums;font-size:6cqw;
  white-space:nowrap;opacity:0;}
.slpre{font-size:0.7em;}.slsuf{font-size:0.62em;}
.slul{position:absolute;left:0;right:0;bottom:-0.16em;height:0.14em;background:#FFF200;transform:scaleX(0);transform-origin:left center;}
.sllabel{margin-top:1.1cqw;font-family:"Inter",sans-serif;font-weight:500;font-size:0.85cqw;letter-spacing:0.12em;
  text-transform:uppercase;max-width:22cqw;line-height:1.45;opacity:0;}
.paper .slnum,.paper .sllead{color:#2B2D2C;}.paper .kick{color:#4C4E4D;}.paper .sllabel{color:#888880;}
.footage .slnum{color:#F6F7F6;}.footage .kick{color:#F6F7F6;}.footage .sllabel{color:#d6d9d6;}
.stmt.paper-t{color:#2B2D2C;}.stmt.footage-t{color:#F6F7F6;}
/* prop-cutout: object-as-evidence photo card (Vox), stacked ON TOP of the scene */
.prop{position:absolute;background:#fff;padding:0.5cqw;box-shadow:0 0.5cqw 1.8cqw rgba(0,0,0,0.38);opacity:0;transform-origin:center;}
.prop img{display:block;width:100%;height:auto;}
.prop-cap{margin-top:0.4cqw;font-family:"Lora",serif;font-style:italic;font-size:0.72cqw;color:#2B2D2C;text-align:center;}
/* geo-map: d3 choropleth (US states / world countries), one region highlighted + annotated */
.geomap{will-change:transform;}
.geomap svg{width:100%;height:100%;display:block;}
.gstate{fill:#DCDFDC;stroke:#F1F3F2;stroke-width:1.0;}
.ghl{fill:#FFF200;stroke:#2B2D2C;stroke-width:1.3;opacity:0;transform-box:fill-box;transform-origin:center;}
.geoleader{position:absolute;inset:0;pointer-events:none;}
.geoleader path{fill:none;stroke:#2B2D2C;stroke-width:2;}
.geopin{position:absolute;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;background:#2B2D2C;opacity:0;}
.geopin::after{content:"";position:absolute;inset:-9px;border:2px solid #2B2D2C;border-radius:50%;opacity:0.4;}
.geolabel{position:absolute;left:8cqw;top:20cqh;max-width:32cqw;}
.glab-k{font-family:"Inter",sans-serif;font-weight:600;font-size:0.9cqw;letter-spacing:0.14em;text-transform:uppercase;color:#4C4E4D;opacity:0;}
.glab-t{font-weight:900;font-size:5.4cqw;line-height:1;letter-spacing:-0.02em;color:#2B2D2C;margin:0.6cqw 0;opacity:0;}
.glab-t .gmark{background:#FFF200;box-decoration-break:clone;padding:0 0.1em;}
.glab-s{font-family:"Lora",serif;font-style:italic;font-size:1.3cqw;line-height:1.4;color:#4C4E4D;max-width:28cqw;opacity:0;}
/* timeline: Vox stylized horizontal timeline — drawing spine + camera pan + alternating circular callouts */
.tlbg{position:absolute;inset:0;background:radial-gradient(120% 120% at 50% 42%,#101210,#070807);}
.tlworld{position:absolute;top:0;left:0;height:100%;will-change:transform;}
.tlspine{position:absolute;height:8px;background:#FFF200;border-radius:4px;transform-origin:left center;transform:scaleX(0);box-shadow:0 0 22px rgba(255,242,0,0.35);}
.tlnode{position:absolute;width:28px;height:28px;margin:-14px 0 0 -14px;border-radius:50%;background:#0a0b0a;border:5px solid #FFF200;transform:scale(0);z-index:3;}
.tlnode::after{content:"";position:absolute;inset:5px;border-radius:50%;background:#FFF200;}
.tlv{position:absolute;width:2px;background:#EDEFEC;transform:scaleY(0);}
.tlh{position:absolute;height:2px;background:#EDEFEC;transform-origin:left center;transform:scaleX(0);}
.tlcirc{position:absolute;border-radius:50%;overflow:hidden;background:#181a18;transform:scale(0);will-change:transform;box-shadow:0 12px 40px rgba(0,0,0,0.5);}
.tlcirc img{width:100%;height:100%;object-fit:cover;filter:grayscale(1) contrast(1.06) brightness(1.08);display:block;}
.tlph{position:absolute;inset:0;background:linear-gradient(135deg,#2b2d2b,#141513);}
.tlph::after{content:"";position:absolute;inset:22% 22%;border:3px solid rgba(237,239,236,0.14);border-radius:50%;}
.tlring{position:absolute;overflow:visible;pointer-events:none;}
.tlring circle{fill:none;stroke:#EDEFEC;stroke-width:2.5;}
.tlyear{position:absolute;font-weight:900;font-size:2.4cqw;letter-spacing:-0.01em;color:#EDEFEC;opacity:0;white-space:nowrap;font-variant-numeric:tabular-nums;}
.tllbl{position:absolute;font-family:"Inter",sans-serif;font-weight:600;font-size:0.82cqw;letter-spacing:0.1em;text-transform:uppercase;color:#9a9c99;opacity:0;white-space:nowrap;}
.tltitle{position:absolute;top:7cqh;left:5.5cqw;font-weight:900;font-size:2.6cqw;letter-spacing:-0.01em;color:#F6F7F6;opacity:0;}
.tltitle .hl{background:#FFF200;color:#0a0b0a;padding:0 0.12em;box-decoration-break:clone;}
"""

# d3 setup — runs once at frame load (before the timeline lines that animate what it builds).
# Placeholders are string-replaced (avoids f-string brace-escaping of the JS body).
_GEO_SETUP = r'''(function(){
  var W=1920,H=1080,SID="@SID@",CFG=@CFG@;
  var topo=window.@DATAVAR@, fc=topojson.feature(topo,topo.objects.@OBJKEY@);
  var byId={}; fc.features.forEach(function(f){byId[String(f.id)]=f;});
  var proj=d3.@PROJ@().fitExtent(@FIT@,fc), geo=d3.geoPath(proj), NS="http://www.w3.org/2000/svg";
  var svg=document.createElementNS(NS,"svg"); svg.setAttribute("viewBox","0 0 "+W+" "+H);
  fc.features.forEach(function(f){var dd=geo(f); if(!dd)return; var p=document.createElementNS(NS,"path"); p.setAttribute("d",dd); p.setAttribute("class","gstate"); svg.appendChild(p);});
  CFG.hl.forEach(function(id){var f=byId[id]; if(!f)return; var dd=geo(f); if(!dd)return; var p=document.createElementNS(NS,"path"); p.setAttribute("d",dd); p.setAttribute("class","ghl"); p.setAttribute("id",SID+"-hl-"+id); svg.appendChild(p);});
  document.getElementById(SID+"-map").appendChild(svg);
  var pf=byId[CFG.primary]||byId[CFG.hl[0]], c=geo.centroid(pf);
  var pin=document.getElementById(SID+"-pin"); pin.style.left=c[0]+"px"; pin.style.top=c[1]+"px";
  var label=document.getElementById(SID+"-label"), lx;
  if(c[0]<W*0.5){label.style.left="auto";label.style.right="8cqw";label.style.textAlign="right";lx=W*0.66;}
  else{label.style.right="auto";label.style.left="8cqw";label.style.textAlign="left";lx=W*0.34;}
  var lead=document.getElementById(SID+"-lead");
  lead.setAttribute("d","M "+lx+" "+(H*0.30)+" L "+c[0]+" "+c[1]);
  var len=lead.getTotalLength(); lead.style.strokeDasharray=len; lead.style.strokeDashoffset=len;
  document.getElementById(SID+"-k").textContent=CFG.kicker;
  var t=document.getElementById(SID+"-t"); var m=document.createElement("span"); m.className="gmark"; m.textContent=CFG.title; t.appendChild(m);
  document.getElementById(SID+"-s").innerHTML=CFG.sub;
})();'''

_GEO = {
  "us":    {"var": "__US",    "obj": "states",    "proj": "geoAlbersUsa",    "fit": "[[120,70],[1800,1000]]", "push": 1.035, "origin": "76% 54%"},
  "world": {"var": "__WORLD", "obj": "countries", "proj": "geoNaturalEarth1", "fit": "[[90,60],[1830,1020]]",  "push": 1.06,  "origin": "52% 40%"},
}

_CORNERS = {
    "br": "right:5cqw;bottom:22cqh;", "bl": "left:5cqw;bottom:22cqh;",
    "tr": "right:5cqw;top:15cqh;",   "tl": "left:5cqw;top:15cqh;",
}
def prop_cutout(sid, i, p, start, dur):
    """Reusable module: an object-as-evidence <img> card stacked over the scene (track 4),
    revealed with a scale + settle (+ optional tilt) on its cue. Vox 'here's the actual
    thing' beat. p: {src, corner, width, cue, tilt, caption}."""
    pid = f"{sid}-prop{i}"
    corner = _CORNERS.get(p.get("corner", "br"), _CORNERS["br"])
    w = p.get("width", "20cqw")
    tilt = float(p.get("tilt", 0))
    cap = f'<div class="prop-cap">{esc(p["caption"])}</div>' if p.get("caption") else ""
    frag = [f'<div id="{pid}" class="clip prop" data-start="{start}" data-duration="{dur}" data-track-index="{4+i}" '
            f'data-layout-allow-overflow style="{corner}width:{w};">'
            f'<img src="{esc(p["src"])}" alt=""/>{cap}</div>']
    cue = start + float(p.get("cue", dur * 0.35))
    tl = [f'tl.fromTo("#{pid}",{{opacity:0,scale:0.82,rotation:{tilt-5}}},'
          f'{{opacity:1,scale:1,rotation:{tilt},duration:0.6,ease:"power3.out"}},{cue});']
    return frag, tl

def _props_of(sid, sc):
    frag, tl = [], []
    for i, p in enumerate(sc["data"].get("props", [])):
        f, t = prop_cutout(sid, i, p, sc["start"], sc["dur"]); frag += f; tl += t
    return frag, tl

def esc(s): return html.escape(str(s), quote=True)

def _safe_sid(sid):
    """CSS-safe id prefix. Element ids/selectors can't start with a digit, but faceless frame
    ids are NN-title (e.g. 01-power) and scenes inherit them → '#01-power-s1-k' throws in
    querySelectorAll. Prepend a letter when digit-first and replace invalid chars."""
    s = re.sub(r"[^0-9A-Za-z_-]", "-", str(sid))
    if s and s[0].isdigit():
        s = "s" + s
    return s or "s"

def media_ground(sid, ground, start, dur):
    """Reusable BLOCK: full-bleed ground. image -> dimmed image + scrim + Ken-Burns;
    paper -> flat mist/parchment; transparent -> scrim only (root video shows through)."""
    frag, tl = [], []
    kind = ground.get("kind", "paper")
    if kind == "image":
        scr = "linear-gradient(90deg,rgba(20,21,20,0.72),rgba(20,21,20,0.30) 55%,rgba(20,21,20,0.45))," \
              "linear-gradient(rgba(20,21,20,0) 45%,rgba(20,21,20,0.62))"
        frag.append(f'<div id="{sid}-gnd" class="clip gnd" data-start="{start}" data-duration="{dur}" '
                    f'data-track-index="0" data-layout-allow-overflow style="background-image:url(\'{esc(ground["src"])}\');"></div>')
        frag.append(f'<div class="clip scrim" data-start="{start}" data-duration="{dur}" data-track-index="1" '
                    f'style="background:{scr};"></div>')
        f0, f1 = ground.get("kb", [1.03, 1.08])
        tl.append(f'tl.fromTo("#{sid}-gnd",{{scale:{f0}}},{{scale:{f1},duration:{dur},ease:"none"}},{start});')
    elif kind == "transparent":  # root video behind; scrim only
        scr = "linear-gradient(90deg,rgba(20,21,20,0.66),rgba(20,21,20,0.18) 55%,rgba(20,21,20,0.42))," \
              "linear-gradient(rgba(20,21,20,0) 50%,rgba(20,21,20,0.6))"
        frag.append(f'<div class="clip scrim" data-start="{start}" data-duration="{dur}" data-track-index="1" '
                    f'style="background:{scr};"></div>')
    else:  # paper / parchment
        col = "#EFE9DC" if ground.get("parchment") else "#F1F3F2"
        frag.append(f'<div class="clip paper-gnd" data-start="{start}" data-duration="{dur}" data-track-index="1" '
                    f'style="background:{col};"></div>')
    return frag, tl

def _register(sid): return "paper" if False else ""

def stat_lockup(sid, sc):
    """Reusable BLOCK: 1-3 count-up numerals + labels + one underline sweep."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    reg = d.get("register", "paper")
    g, tl = media_ground(sid, d.get("ground", {"kind": "paper", "parchment": d.get("parchment")}), start, dur)
    frag = [f'<section class="scene clip {reg}" data-start="{start}" data-duration="{dur}" data-track-index="2">']
    frag.append(f'<div id="{sid}-k" class="kick">{esc(d.get("kicker",""))}</div>')
    frag.append(f'<div class="slrow">')
    tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start+0.1});')
    for i, it in enumerate(d["items"]):
        nid, uid, lid = f"{sid}-n{i}", f"{sid}-u{i}", f"{sid}-l{i}"
        ul = f'<span class="slul" id="{uid}"></span>' if it.get("underline") else ""
        frag.append(f'<div class="slitem"><div class="slnumwrap"><span class="slnum" id="{nid}"></span>{ul}</div>'
                    f'<div class="sllabel" id="{lid}">{esc(it.get("label",""))}</div></div>')
        cue = start + float(it.get("cue", 0.6 + i*0.4))
        if it.get("value") is not None and it.get("from") is None:
            tl.append(f'document.getElementById("{nid}").textContent={json.dumps(str(it["value"]))};')
            tl.append(f'tl.fromTo("#{nid}",{{opacity:0,scale:0.8}},{{opacity:1,scale:1,duration:0.5,ease:"power4.out"}},{cue});')
        else:
            pre, suf = json.dumps(it.get("prefix","")), json.dumps(it.get("suffix",""))
            frm, to = float(it.get("from",0)), float(it.get("to",0))
            tl.append(f'(function(){{var el=document.getElementById("{nid}"),st={{v:{frm}}},f=function(n){{return {pre}+Math.round(n)+{suf};}};'
                      f'el.textContent=f({frm});tl.set(el,{{opacity:1}},{cue});'
                      f'tl.fromTo(st,{{v:{frm}}},{{v:{to},duration:1.4,ease:"power3.out",onUpdate:function(){{el.textContent=f(st.v);}}}},{cue});}})();')
        tl.append(f'tl.fromTo("#{lid}",{{opacity:0,y:12}},{{opacity:1,y:0,duration:0.5}},{cue+0.15});')
        if it.get("underline"):
            tl.append(f'tl.fromTo("#{uid}",{{scaleX:0}},{{scaleX:1,duration:0.45,ease:"power2.out"}},{cue+1.2});')
    frag.append('</div></section>')
    pf, pt = _props_of(sid, sc)
    return g + frag + pf, tl + pt

def highlight_statement(sid, sc):
    """Reusable BLOCK: a statement with ONE yellow-block sweep + optional caption-bar."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    reg = d.get("register", "footage")
    tcls = "paper-t" if reg == "paper" else "footage-t"
    g, tl = media_ground(sid, d.get("ground", {"kind": "transparent"}), start, dur)
    frag = [f'<section class="scene clip {reg}" data-start="{start}" data-duration="{dur}" data-track-index="2">']
    frag.append(f'<div id="{sid}-k" class="kick">{esc(d.get("kicker",""))}</div>')
    tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start+0.2});')
    op = d.get("operative","")
    frag.append(f'<div class="stmt {tcls}">')
    for li, line in enumerate(d["lines"]):
        lid = f"{sid}-ln{li}"
        if op and op in line:
            before, after = line.split(op, 1)
            hid = f"{sid}-hl{li}"
            inner = (f'{esc(before)}<span class="hlwrap"><span id="{sid}-op{li}">{esc(op)}</span>'
                     f'<span class="hlblock" id="{hid}"></span></span>{esc(after)}')
            frag.append(f'<span class="ln" id="{lid}">{inner}</span>')
            cue = start + float(d.get("cue", 3.0))
            tl.append(f'tl.fromTo("#{hid}",{{scaleX:0}},{{scaleX:1,duration:0.4,ease:"power2.out"}},{cue});')
            tl.append(f'tl.to("#{sid}-op{li}",{{color:"#2B2D2C",duration:0.25}},{cue+0.05});')
        else:
            frag.append(f'<span class="ln" id="{lid}">{esc(line)}</span>')
        tl.append(f'tl.fromTo("#{lid}",{{opacity:0,yPercent:60}},{{opacity:1,yPercent:0,duration:0.6,ease:"power3.out"}},{start+0.4+li*0.35});')
    frag.append('</div>')
    if d.get("captionBar"):
        cid = f"{sid}-cap"
        frag.append(f'<div id="{cid}" class="capbar">{esc(d["captionBar"])}</div>')
        tl.append(f'tl.fromTo("#{cid}",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start+float(d.get("capCue",dur*0.8))});')
    frag.append('</section>')
    pf, pt = _props_of(sid, sc)
    return g + frag + pf, tl + pt

def geo_map(sid, sc):
    """Reusable BLOCK: a d3 choropleth map (US states or world countries) with one or more
    regions highlighted, a pin + leader line + Vox label. d3 computes the projection +
    geometry + centroid; GSAP reveals it (seek-safe); CSS themes it. data: {kind:"us"|"world",
    highlight:[ids], primary?, kicker, title, sub}. FIPS for US, ISO-numeric for world."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    g = _GEO.get(d.get("kind", "us"), _GEO["us"])
    hl = [str(x) for x in d.get("highlight", [])]
    primary = str(d.get("primary", hl[0] if hl else ""))
    cfg = {"hl": hl, "primary": primary, "kicker": d.get("kicker", ""),
           "title": d.get("title", ""), "sub": d.get("sub", "")}
    frag = [
        # own mist ground on a track-0 clip (frame-worker rule: never a bg on #root)
        f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="0" '
        f'style="position:absolute;inset:0;background:#F1F3F2;"></div>',
        f'<div id="{sid}-map" class="clip geomap" data-start="{start}" data-duration="{dur}" '
        f'data-track-index="1" style="transform-origin:{g["origin"]};"></div>',
        f'<svg id="{sid}-leader" class="clip geoleader" data-start="{start}" data-duration="{dur}" '
        f'data-track-index="2" viewBox="0 0 1920 1080" preserveAspectRatio="none"><path id="{sid}-lead" d=""/></svg>',
        f'<div id="{sid}-pin" class="clip geopin" data-start="{start}" data-duration="{dur}" data-track-index="3"></div>',
        f'<div id="{sid}-label" class="clip geolabel" data-start="{start}" data-duration="{dur}" data-track-index="4">'
        f'<div id="{sid}-k" class="glab-k"></div><div id="{sid}-t" class="glab-t"></div><div id="{sid}-s" class="glab-s"></div></div>',
    ]
    setup = (_GEO_SETUP.replace("@SID@", sid).replace("@CFG@", json.dumps(cfg, ensure_ascii=False))
             .replace("@DATAVAR@", g["var"]).replace("@OBJKEY@", g["obj"])
             .replace("@PROJ@", g["proj"]).replace("@FIT@", g["fit"]))
    tl = [setup,
        f'tl.from("#{sid}-map",{{opacity:0,y:24,duration:0.7,ease:"power2.out"}},{start});',
        f'tl.to("#{sid}-map",{{scale:{g["push"]},duration:{dur},ease:"none"}},{start});',
        f'tl.to("#{sid}-map svg .ghl",{{opacity:1,duration:0.5,ease:"power2.out",stagger:0.12}},{start+1.1});',
        f'tl.from("#{sid}-map svg .ghl",{{scale:0.5,duration:0.6,ease:"back.out(2)",stagger:0.12}},{start+1.1});',
        f'tl.to("#{sid}-pin",{{opacity:1,duration:0.3}},{start+1.5});',
        f'tl.from("#{sid}-pin",{{scale:0,duration:0.5,ease:"back.out(3)"}},{start+1.5});',
        f'tl.to("#{sid}-lead",{{strokeDashoffset:0,duration:0.55,ease:"power2.inOut"}},{start+1.7});',
        f'tl.fromTo("#{sid}-k",{{opacity:0,y:12}},{{opacity:1,y:0,duration:0.5}},{start+1.9});',
        f'tl.fromTo("#{sid}-t",{{opacity:0,y:20}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},{start+2.05});',
        f'tl.fromTo("#{sid}-s",{{opacity:0,y:16}},{{opacity:1,y:0,duration:0.6}},{start+2.3});',
    ]
    return frag, tl

def raw_scene(sid, sc):
    """Bespoke passthrough: an agent-authored scene that no template covers. data.html is
    the scene's HTML fragment(s) (clip elements, sid-prefixed ids, tracks); data.tl is the
    list of GSAP lines (frame-absolute times) merged into the frame's one timeline. This is
    the 'go bespoke' escape hatch — templated + hand-authored scenes coexist in one frame."""
    d = sc["data"]
    frag = d.get("html", [])
    if isinstance(frag, str):
        frag = [frag]
    return list(frag), list(d.get("tl", []))

import math

def timeline(sid, sc):
    """Reusable BLOCK: a Vox-style stylized timeline (the XoC62NDH4aw look). A spine draws in,
    the camera pans event-to-event, each event pops a node + connector to a circular image cutout
    (mask scale-in + a stroked ring that draws) with a big year + kicker label. Pure GSAP+CSS/SVG,
    seek-safe (transforms/opacity/strokeDashoffset only), one merged timeline, per-scene ids.
      axis:"horizontal" (default) — spine runs left->right, camera pans horizontally, callouts
        alternate via elbow connectors (side:"up"|"down", auto-alternates).
      axis:"vertical" — spine runs top<->bottom, camera pans vertically (dir:"down"(default)|"up"),
        branches go out LEFT/RIGHT (side:"left"|"right", auto-alternates).
    data: {events:[{year, label?, image?, side?}], axis?, dir?, title?, titleHi?, focus?, gap?, spine?}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    events = d.get("events", [])
    n = max(1, len(events))
    D = 260; R = D / 2 - 6; C = 2 * math.pi * R   # circle diam, ring radius, circumference (build-time draw)
    img = lambda ev: (f'<img src="{esc(ev["image"])}" alt=""/>' if ev.get("image") else '<div class="tlph"></div>')
    frag = [f'<div id="{sid}-bg" class="clip tlbg" data-start="{start}" data-duration="{dur}" data-track-index="0"></div>']
    tl = []
    lead = 0.6
    step = (dur - lead - 1.2) / max(1, n - 1) if n > 1 else 0
    sdraw = min(1.5, dur * 0.16)

    def circle_ring(cid, rid, ev, c_left, c_top):
        return [f'<div id="{cid}" class="tlcirc" style="left:{c_left:.0f}px;top:{c_top:.0f}px;width:{D}px;height:{D}px;">{img(ev)}</div>',
                f'<svg id="{rid}" class="tlring" style="left:{c_left:.0f}px;top:{c_top:.0f}px;width:{D}px;height:{D}px;" viewBox="0 0 {D} {D}">'
                f'<circle cx="{D/2}" cy="{D/2}" r="{R:.1f}" stroke-dasharray="{C:.1f}" stroke-dashoffset="{C:.1f}"/></svg>']

    def reveal(nid, cid, rid, yid, lid, has_label, cue):
        t = [f'tl.fromTo("#{nid}",{{scale:0}},{{scale:1,duration:0.45,ease:"back.out(2)"}},{cue:.2f});',
             f'tl.fromTo("#{cid}",{{scale:0}},{{scale:1,duration:0.55,ease:"back.out(1.6)"}},{cue+0.38:.2f});',
             f'tl.fromTo("#{rid} circle",{{strokeDashoffset:{C:.1f}}},{{strokeDashoffset:0,duration:0.70,ease:"power2.inOut"}},{cue+0.42:.2f});',
             f'tl.fromTo("#{yid}",{{opacity:0,y:14}},{{opacity:1,y:0,duration:0.50,ease:"power3.out"}},{cue+0.50:.2f});']
        if has_label:
            t.append(f'tl.fromTo("#{lid}",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.50}},{cue+0.62:.2f});')
        return t

    if d.get("axis", "horizontal") == "vertical":
        SX = int(d.get("spine", 960))       # spine x (screen center by default)
        FOCUS = int(d.get("focus", 540))    # screen y the active event sits at
        up = d.get("dir", "down") == "up"   # camera / travel direction
        CONN, BOXW = 160, 480               # branch length, left-label box width
        solo = bool(d.get("solo"))          # one graph on screen at a time (opposite side stays free)
        sorg = "center bottom" if up else "center top"

        def vgeom(right, Yc):
            if right:
                h_left, h_org, c_left = SX, "left", SX + CONN
                lbl_left, lbl_extra = SX + CONN + D + 28, ""
            else:
                h_left, h_org, c_left = SX - CONN, "right", SX - CONN - D
                lbl_left, lbl_extra = (SX - CONN - D - 28) - BOXW, f"width:{BOXW}px;text-align:right;"
            return h_left, h_org, c_left, lbl_left, lbl_extra, Yc - D / 2, Yc - 46, Yc + 8

        def vbranch_frag(hid, cid, rid, yid, lid, ev, right, Yc):
            h_left, h_org, c_left, lbl_left, lbl_extra, c_top, y_top, l_top = vgeom(right, Yc)
            f = [f'<div id="{hid}" class="tlh" style="left:{h_left}px;top:{Yc-1}px;width:{CONN}px;transform-origin:{h_org} center;"></div>']
            f += circle_ring(cid, rid, ev, c_left, c_top)
            f.append(f'<div id="{yid}" class="tlyear" style="left:{lbl_left:.0f}px;top:{y_top:.0f}px;{lbl_extra}">{esc(ev.get("year",""))}</div>')
            if ev.get("label"):
                f.append(f'<div id="{lid}" class="tllbl" style="left:{lbl_left:.0f}px;top:{l_top:.0f}px;{lbl_extra}">{esc(ev["label"])}</div>')
            return f

        if solo:
            # SOLO: fixed spine + a playhead node at the focus point. Each event's graph swaps in
            # place — the previous slides out as the next slides in — so only ONE is ever on screen,
            # keeping the opposite side clear for other content. side is consistent (default right).
            side_def = d.get("solo_side", "right")
            enter = 150 if not up else -150
            frag.append(f'<div id="{sid}-world" class="clip tlworld" data-start="{start}" data-duration="{dur}" '
                        f'data-track-index="2" data-layout-allow-overflow style="width:1920px;height:1080px;">')
            frag.append(f'<div id="{sid}-spine" class="tlspine" style="left:{SX-4}px;top:0;width:8px;height:1080px;transform-origin:{sorg};"></div>')
            frag.append(f'<div id="{sid}-pn" class="tlnode" style="left:{SX}px;top:{FOCUS}px;"></div>')
            tl.append(f'tl.fromTo("#{sid}-spine",{{scaleX:1,scaleY:0}},{{scaleX:1,scaleY:1,duration:{sdraw:.2f},ease:"power2.out"}},{start});')
            tl.append(f'tl.fromTo("#{sid}-pn",{{scale:0}},{{scale:1,duration:0.5,ease:"back.out(2)"}},{start+0.05});')
            for i, ev in enumerate(events):
                right = (ev.get("side") or side_def) == "right"
                cue = start + lead + i * step
                gid, hid = f"{sid}-g{i}", f"{sid}-h{i}"
                cid, rid, yid, lid = f"{sid}-c{i}", f"{sid}-r{i}", f"{sid}-y{i}", f"{sid}-l{i}"
                frag.append(f'<div id="{gid}" style="position:absolute;inset:0;opacity:0;">')
                frag += vbranch_frag(hid, cid, rid, yid, lid, ev, right, FOCUS)
                frag.append('</div>')
                tl.append(f'tl.fromTo("#{gid}",{{opacity:0,y:{enter}}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},{cue:.2f});')
                tl.append(f'tl.fromTo("#{sid}-pn",{{scale:1}},{{scale:1.25,duration:0.16,ease:"power2.out"}},{cue:.2f});')
                tl.append(f'tl.to("#{sid}-pn",{{scale:1,duration:0.34,ease:"power2.inOut"}},{cue+0.16:.2f});')
                tl.append(f'tl.fromTo("#{hid}",{{scaleX:0}},{{scaleX:1,duration:0.30,ease:"power2.out"}},{cue+0.10:.2f});')
                tl.append(f'tl.fromTo("#{cid}",{{scale:0}},{{scale:1,duration:0.55,ease:"back.out(1.6)"}},{cue+0.15:.2f});')
                tl.append(f'tl.fromTo("#{rid} circle",{{strokeDashoffset:{C:.1f}}},{{strokeDashoffset:0,duration:0.70,ease:"power2.inOut"}},{cue+0.20:.2f});')
                tl.append(f'tl.fromTo("#{yid}",{{opacity:0}},{{opacity:1,duration:0.45,ease:"power2.out"}},{cue+0.32:.2f});')
                if ev.get("label"):
                    tl.append(f'tl.fromTo("#{lid}",{{opacity:0}},{{opacity:1,duration:0.45}},{cue+0.44:.2f});')
                if i < n - 1:  # slide out before the next arrives -> strictly one graph at a time
                    ex = max(cue + 0.9, start + lead + (i + 1) * step - 0.55)
                    tl.append(f'tl.to("#{gid}",{{opacity:0,y:{-enter},duration:0.45,ease:"power2.in"}},{ex:.2f});')
        else:
            GAP = int(d.get("gap", 480))        # world spacing between events
            worldH = 2 * FOCUS + (n - 1) * GAP
            frag.append(f'<div id="{sid}-world" class="clip tlworld" data-start="{start}" data-duration="{dur}" data-track-index="2" '
                        f'data-layout-allow-overflow style="width:1920px;height:{worldH}px;">')
            frag.append(f'<div id="{sid}-spine" class="tlspine" style="left:{SX-4}px;top:0;width:8px;height:{worldH}px;transform-origin:{sorg};"></div>')
            tl.append(f'tl.fromTo("#{sid}-spine",{{scaleX:1,scaleY:0}},{{scaleX:1,scaleY:1,duration:{sdraw:.2f},ease:"power2.out"}},{start});')
            for i, ev in enumerate(events):
                Y = FOCUS + (n - 1 - i) * GAP if up else FOCUS + i * GAP
                right = (ev.get("side") or ("right" if i % 2 == 0 else "left")) == "right"
                cue = start + lead + i * step
                nid, hid = f"{sid}-n{i}", f"{sid}-h{i}"
                cid, rid, yid, lid = f"{sid}-c{i}", f"{sid}-r{i}", f"{sid}-y{i}", f"{sid}-l{i}"
                frag.append(f'<div id="{nid}" class="tlnode" style="left:{SX}px;top:{Y}px;"></div>')
                frag += vbranch_frag(hid, cid, rid, yid, lid, ev, right, Y)
                pan = FOCUS - Y
                if i == 0:
                    tl.append(f'tl.set("#{sid}-world",{{y:{pan}}},{start});')
                else:
                    tl.append(f'tl.to("#{sid}-world",{{y:{pan},duration:0.75,ease:"power2.inOut"}},{max(start,cue-0.5):.2f});')
                tl.append(f'tl.fromTo("#{hid}",{{scaleX:0}},{{scaleX:1,duration:0.28,ease:"power2.out"}},{cue+0.12:.2f});')
                tl += reveal(nid, cid, rid, yid, lid, bool(ev.get("label")), cue)
    else:
        SY = 540                            # spine y (canvas mid)
        FOCUS = int(d.get("focus", 640))    # screen x the active node pans to
        GAP = int(d.get("gap", 760))        # world spacing between events
        HV, OFF = 150, 70                   # vertical stub, elbow jog
        worldW = FOCUS + (n - 1) * GAP + 900
        frag.append(f'<div id="{sid}-world" class="clip tlworld" data-start="{start}" data-duration="{dur}" data-track-index="2" '
                    f'data-layout-allow-overflow style="width:{worldW}px;">')
        frag.append(f'<div id="{sid}-spine" class="tlspine" style="left:0;top:{SY-4}px;width:{worldW}px;"></div>')
        tl.append(f'tl.fromTo("#{sid}-spine",{{scaleX:0}},{{scaleX:1,duration:{sdraw:.2f},ease:"power2.out"}},{start});')
        for i, ev in enumerate(events):
            X = FOCUS + i * GAP
            up = (ev.get("side") or ("up" if i % 2 == 0 else "down")) == "up"
            cue = start + lead + i * step
            nid, vid, hid = f"{sid}-n{i}", f"{sid}-v{i}", f"{sid}-h{i}"
            cid, rid, yid, lid = f"{sid}-c{i}", f"{sid}-r{i}", f"{sid}-y{i}", f"{sid}-l{i}"
            # year + label sit in the connector GAP (between spine and elbow), never inside the circle
            if up:
                v_top, h_y, c_top, y_top, l_top, v_org = SY - HV, SY - HV, SY - HV - D, SY - HV + 12, SY - HV + 80, "bottom"
            else:
                v_top, h_y, c_top, y_top, l_top, v_org = SY, SY + HV, SY + HV, SY + 14, SY + 82, "top"
            c_left = X + OFF - D / 2
            frag.append(f'<div id="{nid}" class="tlnode" style="left:{X}px;top:{SY}px;"></div>')
            frag.append(f'<div id="{vid}" class="tlv" style="left:{X-1}px;top:{v_top}px;height:{HV}px;transform-origin:center {v_org};"></div>')
            frag.append(f'<div id="{hid}" class="tlh" style="left:{X}px;top:{h_y}px;width:{OFF}px;"></div>')
            frag += circle_ring(cid, rid, ev, c_left, c_top)
            frag.append(f'<div id="{yid}" class="tlyear" style="left:{X+14}px;top:{y_top}px;">{esc(ev.get("year",""))}</div>')
            if ev.get("label"):
                frag.append(f'<div id="{lid}" class="tllbl" style="left:{X+14}px;top:{l_top}px;">{esc(ev["label"])}</div>')
            if i > 0:  # pan the world so this event lands at FOCUS, just before it pops
                tl.append(f'tl.to("#{sid}-world",{{x:{-i*GAP},duration:0.75,ease:"power2.inOut"}},{max(start,cue-0.5):.2f});')
            tl.append(f'tl.fromTo("#{vid}",{{scaleY:0}},{{scaleY:1,duration:0.30,ease:"power2.out"}},{cue+0.12:.2f});')
            tl.append(f'tl.fromTo("#{hid}",{{scaleX:0}},{{scaleX:1,duration:0.22,ease:"power2.out"}},{cue+0.30:.2f});')
            tl += reveal(nid, cid, rid, yid, lid, bool(ev.get("label")), cue)
    frag.append('</div>')  # close .tlworld
    if d.get("title"):
        t, op = d["title"], d.get("titleHi", "")
        html_t = (f'{esc(t.split(op,1)[0])}<span class="hl">{esc(op)}</span>{esc(t.split(op,1)[1])}'
                  if op and op in t else esc(t))
        frag.append(f'<div id="{sid}-title" class="clip tltitle" data-start="{start}" data-duration="{dur}" '
                    f'data-track-index="3">{html_t}</div>')
        tl.append(f'tl.fromTo("#{sid}-title",{{opacity:0,y:-12}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},{start+0.2});')
    return frag, tl

BLOCKS = {"stat": stat_lockup, "statement": highlight_statement, "geo": geo_map, "raw": raw_scene,
          "timeline": timeline}

def compose_frame(frame_id, dur, scenes):
    body, tl = [], []
    for sc in scenes:
        sc = {**sc, "id": _safe_sid(sc["id"])}   # digit-first ids break #selectors
        f, t = BLOCKS[sc["type"]](sc["id"], sc)
        body += f; tl += t
    # geo scenes need d3 + topojson + geometry loaded before the timeline script (which
    # contains their setup IIFE). Loaded next to GSAP — the assembler guarantees script order.
    geo = [sc for sc in scenes if sc["type"] == "geo"]
    libs = ""
    if geo:
        kinds = set(sc["data"].get("kind", "us") for sc in geo)
        libs = ('  <script src="vendor/d3.min.js"></script>\n'
                '  <script src="vendor/topojson-client.min.js"></script>\n')
        if "us" in kinds:    libs += '  <script src="vendor/us-states.js"></script>\n'
        if "world" in kinds: libs += '  <script src="vendor/world.js"></script>\n'
    return f"""<template>
  <style>{FONTS}{CSS}</style>
  <div id="root" data-composition-id="{frame_id}" data-width="1920" data-height="1080">
    {chr(10).join('    '+b for b in body)}
  </div>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
{libs}  <script>
    window.__timelines = window.__timelines || {{}};
    var tl = gsap.timeline({{ paused: true }});
    {chr(10).join('    '+x for x in tl)}
    tl.to({{}}, {{ duration: {dur} }}, 0);
    window.__timelines["{frame_id}"] = tl;
  </script>
</template>
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    spec = json.load(open(args.spec, encoding="utf-8"))
    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    for fr in spec["frames"]:
        html_out = compose_frame(fr["id"], fr["dur"], fr["scenes"])
        (out / f'{fr["id"]}.html').write_text(html_out, encoding="utf-8")
        print(f'composed {fr["id"]}.html — {len(fr["scenes"])} scenes, {len(html_out)} bytes')

if __name__ == "__main__":
    main()
