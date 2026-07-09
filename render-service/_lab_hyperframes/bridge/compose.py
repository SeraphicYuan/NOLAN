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
.hlwrap{position:relative;display:inline-block;isolation:isolate;}
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
/* newshead: a newspaper headline card (Vox "newspaper animation" look) */
.nhbg{position:absolute;inset:0;background:radial-gradient(130% 130% at 50% 38%,#2b2d2c,#161716);}
.nhcard{position:absolute;background:#ECE9E1;overflow:hidden;box-shadow:0 22px 64px rgba(0,0,0,0.55);transform-origin:center;}
.nhcard .tex{position:absolute;inset:0;background-image:radial-gradient(circle,rgba(20,22,18,0.09) 1.1px,transparent 1.4px);background-size:20px 20px;opacity:0.7;}
.nhcard .vig{position:absolute;inset:0;box-shadow:inset 0 0 150px rgba(110,100,80,0.20);}
.nhdate{position:absolute;display:inline-block;background:#C8232C;color:#F7F3EA;font-family:"Lora",serif;font-weight:700;font-size:18px;letter-spacing:0.02em;padding:6px 12px;opacity:0;}
.nhhead{position:absolute;font-family:"Lora",serif;font-weight:700;color:#191712;font-size:60px;line-height:1.14;letter-spacing:-0.005em;}
.nhline{display:block;}
.nhhead .w{display:inline-block;}
.nhhl-wrap{position:relative;display:inline-block;}
.nhhl{position:absolute;left:-0.05em;right:-0.05em;top:0.12em;bottom:0.16em;background:#FFF23B;transform:scaleX(0);transform-origin:left center;z-index:-1;}
.nhsub{position:absolute;font-family:"Lora",serif;font-weight:400;color:#38362d;font-size:23px;line-height:1.5;opacity:0;}
.nhsub .subhl{background:#FFF23B;-webkit-box-decoration-break:clone;box-decoration-break:clone;padding:0 2px;}
.nhsrc{position:absolute;display:flex;align-items:center;gap:16px;opacity:0;}
.nhsrc .mast{font-family:"UnifrakturMaguntia",serif;color:#191712;font-size:42px;line-height:1;}
.nhsrc .rule{height:2px;background:#191712;transform:scaleX(0);transform-origin:left center;}
.nhphoto{position:absolute;overflow:hidden;filter:grayscale(1) contrast(1.06);opacity:0;box-shadow:0 8px 22px rgba(0,0,0,0.32);}
.nhphoto img{width:100%;height:100%;object-fit:cover;display:block;}
.nhcap{position:absolute;font-family:"Lora",serif;font-style:italic;font-size:15px;color:#4a4840;opacity:0;}
.nharrow{position:absolute;overflow:visible;pointer-events:none;}
.nharrow path{fill:none;stroke:#C8232C;stroke-width:6;stroke-linecap:round;stroke-linejoin:round;}
.nhcut{position:absolute;overflow:visible;opacity:0;will-change:transform;}
.nhcut img{width:100%;height:100%;object-fit:contain;object-position:left center;display:block;filter:grayscale(1) contrast(1.08) drop-shadow(4px 0 0 #C8232C) drop-shadow(-4px 0 0 #C8232C) drop-shadow(0 4px 0 #C8232C) drop-shadow(0 -4px 0 #C8232C) drop-shadow(3px 3px 0 #C8232C) drop-shadow(-3px 3px 0 #C8232C) drop-shadow(3px -3px 0 #C8232C) drop-shadow(-3px -3px 0 #C8232C);}
/* collage: cut-out subjects (people/objects) assembling into a tableau on a backdrop */
.clgbg{position:absolute;inset:0;}
.clgvig{position:absolute;inset:0;pointer-events:none;}
.clgworld{position:absolute;inset:0;will-change:transform;transform-origin:center;}
.collage-sub{position:absolute;width:0;height:0;will-change:transform,opacity;}
.collage-sub img{position:absolute;left:0;top:0;transform:translate(-50%,-50%);display:block;}
.collage-sub.shadow img{filter:drop-shadow(0 16px 26px rgba(0,0,0,0.42));}
/* diagram: d3-computed node-link graph (tree/flow/radial). d3 lays out ONCE at load; GSAP reveals (seek-safe). */
.dgbg{position:absolute;inset:0;background:#F1F3F2;}
.dgbg.dark{background:radial-gradient(120% 120% at 50% 40%,#14171a,#090b0d);}
.dglinks{position:absolute;inset:0;pointer-events:none;overflow:visible;}
.dglinks path.dglink{fill:none;stroke:#B7BCB9;stroke-width:3;stroke-linecap:round;}
.dglinks.dark path.dglink{stroke:#3b4247;}
.dgstage{position:absolute;inset:0;overflow:hidden;}
.dgworld{position:absolute;left:0;top:0;transform-origin:0 0;will-change:transform;}
.dgnode-w{position:absolute;transform:translate(-50%,-50%);}
.dgnode{opacity:0;transform-origin:center;min-width:110px;max-width:290px;background:#fff;
  border:2px solid #2B2D2C;border-radius:12px;padding:0.85cqw 1.2cqw;text-align:center;
  box-shadow:0 0.4cqw 1.1cqw rgba(0,0,0,0.13);}
.dgnode.pill{border-radius:999px;}
.dgnode .lab{font-weight:800;font-size:1.15cqw;line-height:1.14;letter-spacing:-0.01em;color:#2B2D2C;}
.dgnode .sub{font-family:"Inter",sans-serif;font-weight:500;font-size:0.78cqw;line-height:1.3;color:#6b6d6a;margin-top:0.28cqw;}
.dgnode.hl{background:#FFF200;border-color:#2B2D2C;}
.dgnode.hl .sub{color:#4C4E4D;}
.dgnode.root{background:#2B2D2C;border-color:#2B2D2C;}
.dgnode.root .lab{color:#F6F7F6;}.dgnode.root .sub{color:#c9ccc9;}
/* dark register: the node-container clip carries .dg-dark; nodes are its descendants */
.dg-dark .dgnode{background:#191c1f;border-color:#EDEFEC;box-shadow:0 0.5cqw 1.5cqw rgba(0,0,0,0.5);}
.dg-dark .dgnode .lab{color:#F6F7F6;}.dg-dark .dgnode .sub{color:#9a9c99;}
.dg-dark .dgnode.hl{background:#FFF200;border-color:#FFF200;}
.dg-dark .dgnode.hl .lab{color:#0a0b0a;}.dg-dark .dgnode.hl .sub{color:#3a3a2a;}
.dg-dark .dgnode.root{background:#0a0b0a;border-color:#EDEFEC;}
.dgkick{position:absolute;top:6.2cqw;left:5.5cqw;font-family:"Inter",sans-serif;font-weight:600;font-size:0.9cqw;
  letter-spacing:0.14em;text-transform:uppercase;color:#4C4E4D;opacity:0;}
.dgkick.on-dark{color:#9a9c99;}
.dgtitle{position:absolute;top:8.0cqw;left:5.5cqw;max-width:82cqw;font-weight:900;font-size:2.6cqw;line-height:1.06;
  letter-spacing:-0.015em;color:#2B2D2C;opacity:0;}
.dgtitle.on-dark{color:#F6F7F6;}
.dgtitle .hl{background:#FFF200;color:#2B2D2C;padding:0 0.1em;box-decoration-break:clone;}
/* comparison: split A-vs-B; each panel hosts a typed content (image/text/stat/video) + per-side effects */
.cmp-panel{position:absolute;overflow:hidden;background:#0d0f11;will-change:transform;}
.cmp-media{position:absolute;inset:0;background-size:cover;background-position:center;transform-origin:50% 50%;will-change:transform;}
.cmp-media video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block;}
.cmp-scrim{position:absolute;inset:0;pointer-events:none;background:linear-gradient(rgba(10,11,12,0) 42%,rgba(10,11,12,0.72));}
.cmp-vig{position:absolute;inset:0;pointer-events:none;}
.cmp-tint{position:absolute;inset:0;pointer-events:none;mix-blend-mode:multiply;}
.cmp-paper{position:absolute;inset:0;}
.cmp-label{position:absolute;left:1.6cqw;top:1.4cqw;background:#FFF200;color:#2B2D2C;font-family:"Inter",sans-serif;
  font-weight:700;font-size:0.8cqw;letter-spacing:0.1em;text-transform:uppercase;padding:0.4cqw 0.9cqw;border-radius:6px;opacity:0;z-index:4;}
.cmp-txt{position:absolute;left:2.4cqw;right:2.4cqw;bottom:6.5cqh;z-index:3;}
.cmp-txt.mid{top:50%;bottom:auto;transform:translateY(-50%);}
/* bottom title over media = a localized lower-third scrim (bound to the panel) so the overlay reads on ANY footage */
.cmp-txt:not(.mid)::before{content:"";position:absolute;left:-2.4cqw;right:-2.4cqw;top:-1.8cqh;bottom:-6.5cqh;
  background:linear-gradient(transparent,rgba(8,9,10,0.88));z-index:-1;pointer-events:none;}
.cmp-txt .k{font-family:"Inter",sans-serif;font-weight:600;font-size:0.82cqw;letter-spacing:0.13em;text-transform:uppercase;opacity:0;margin-bottom:0.5cqw;}
.cmp-txt .t{font-weight:800;font-size:2.1cqw;line-height:1.1;letter-spacing:-0.012em;}
.cmp-txt .t .ln{display:block;opacity:0;}
.cmp-txt .t .mark{background:#FFF200;color:#2B2D2C;padding:0 0.08em;box-decoration-break:clone;}
.cmp-txt.paper .k{color:#4C4E4D;}.cmp-txt.paper .t{color:#2B2D2C;}
.cmp-txt.footage .k{color:#EDEFEC;text-shadow:0 1px 6px rgba(0,0,0,0.6);}.cmp-txt.footage .t{color:#F6F7F6;text-shadow:0 2px 12px rgba(0,0,0,0.6);}
.cmp-num{position:absolute;left:0;right:0;top:50%;transform:translateY(-50%);text-align:center;z-index:3;padding:0 2cqw;}
.cmp-num .v{font-weight:900;font-size:5.6cqw;line-height:1;letter-spacing:-0.03em;font-variant-numeric:tabular-nums;opacity:0;}
.cmp-num .l{font-family:"Inter",sans-serif;font-weight:500;font-size:0.9cqw;letter-spacing:0.12em;text-transform:uppercase;margin-top:0.8cqw;opacity:0;}
.cmp-num.paper .v{color:#2B2D2C;}.cmp-num.paper .l{color:#6b6d6a;}
.cmp-num.footage .v{color:#F6F7F6;}.cmp-num.footage .l{color:#d6d9d6;}
.cmp-div{position:absolute;background:#0a0b0c;z-index:5;}
.cmp-vs-w{position:absolute;transform:translate(-50%,-50%);z-index:6;}
.cmp-vs{width:5.2cqw;height:5.2cqw;border-radius:50%;background:#2B2D2C;color:#FFF200;display:flex;align-items:center;
  justify-content:center;font-weight:900;font-size:1.5cqw;letter-spacing:-0.02em;transform-origin:center;transform:scale(0);box-shadow:0 0.4cqw 1.4cqw rgba(0,0,0,0.42);}
.cmp-htitle{position:absolute;left:0;right:0;top:0;height:150px;display:flex;flex-direction:column;justify-content:center;
  align-items:center;text-align:center;z-index:7;background:linear-gradient(#0a0b0c,rgba(10,11,12,0));}
.cmp-htitle .k{font-family:"Inter",sans-serif;font-weight:600;font-size:0.82cqw;letter-spacing:0.14em;text-transform:uppercase;color:#c9ccc9;opacity:0;margin-bottom:0.4cqw;}
.cmp-htitle .t{font-weight:900;font-size:1.9cqw;letter-spacing:-0.015em;color:#F6F7F6;opacity:0;}
.cmp-htitle .t .hl{background:#FFF200;color:#2B2D2C;padding:0 0.1em;box-decoration-break:clone;}
.cmp-panel.framed{border-radius:20px;border:3px solid rgba(255,255,255,0.16);box-shadow:0 1.2cqw 3cqw rgba(0,0,0,0.5);}
.cmp-vhole{background:transparent;}
/* a root-mounted comparison video element (archetype B): direct child of #root, positioned to a panel rect */
.cmp-rootvid{position:absolute;object-fit:cover;background:#000;display:block;}
.cmp-rootvid.framed{border-radius:20px;border:3px solid rgba(255,255,255,0.16);overflow:hidden;box-shadow:0 1.2cqw 3cqw rgba(0,0,0,0.5);}
/* text-reveal vocabulary (gsapify "Text & Typography", rewritten seek-safe). Units (chars/words)
   are split at BUILD time into .rv-u spans so each reveal is a pure fn of timeline progress. */
.rv-u{display:inline-block;will-change:transform,opacity;backface-visibility:hidden;}
.rv-w{margin-right:0.28em;}
.rv-caret{opacity:0;font-weight:400;}
/* gradient reveal = base ink/white text + ONE bright accent band swept through (clean, not a muddy
   full ink->yellow blend); background-image (not the shorthand) so background-clip:text isn't reset. */
.stmt .ln.rv-grad{background-image:linear-gradient(90deg in oklab,var(--rv-c1) 0%,var(--rv-c1) 43%,var(--rv-c2) 50%,var(--rv-c1) 57%,var(--rv-c1) 100%);
  background-size:300% 100%;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent;}
/* gallery: a grid/masonry of framed images revealing staggered; optional spotlight-one (others blur+dim) */
.galbg{position:absolute;inset:0;}
.galvig{position:absolute;inset:0;pointer-events:none;}
.galworld{position:absolute;inset:0;will-change:transform;transform-origin:center;}
.galcard{position:absolute;box-sizing:border-box;overflow:hidden;background:#fff;padding:0.42cqw;
  box-shadow:0 0.8cqw 2.2cqw rgba(0,0,0,0.44);transform-origin:center;will-change:transform,opacity,filter;filter:blur(0px);}
.galcard.noframe{padding:0;background:transparent;box-shadow:0 0.6cqw 1.7cqw rgba(0,0,0,0.4);}
.galcard img{width:100%;height:100%;object-fit:cover;display:block;}
.galcap{position:absolute;font-family:"Inter",sans-serif;font-weight:600;font-size:0.72cqw;letter-spacing:0.08em;
  text-transform:uppercase;color:#EDEFEC;opacity:0;text-align:center;}
.galhcap{position:absolute;font-family:"Lora",serif;font-style:italic;font-size:1.15cqw;color:#F6F7F6;opacity:0;
  text-align:center;text-shadow:0 2px 12px rgba(0,0,0,0.65);}
.galtitle{position:absolute;top:5.5cqh;left:0;width:100%;text-align:center;font-weight:900;font-size:2.4cqw;
  letter-spacing:-0.01em;color:#F6F7F6;opacity:0;}
.galtitle .hl{background:#FFF200;color:#0a0b0a;padding:0 0.12em;box-decoration-break:clone;}
/* carousel: a temporal image sequence — full-bleed slider (crossfade/kenburns) OR 3D coverflow */
.carworld{position:absolute;inset:0;}
.carslide{position:absolute;inset:0;opacity:0;overflow:hidden;will-change:opacity;}
.carslide img{width:100%;height:100%;object-fit:cover;display:block;will-change:transform;}
.carstage{position:absolute;inset:0;perspective:1600px;}
.car3d{position:absolute;inset:0;transform-style:preserve-3d;}
.carcard{position:absolute;left:50%;top:50%;overflow:hidden;border-radius:10px;background:#000;
  box-shadow:0 30px 90px rgba(0,0,0,0.62);backface-visibility:hidden;will-change:transform,opacity;}
.carcard img{width:100%;height:100%;object-fit:cover;display:block;}
.carcap{position:absolute;left:0;width:100%;bottom:19cqh;text-align:center;font-family:"Lora",serif;z-index:7;
  font-style:italic;font-size:1.35cqw;color:#F8F8F6;opacity:0;text-shadow:0 2px 14px rgba(0,0,0,0.7);}
.cartitle{position:absolute;top:5.5cqh;left:0;width:100%;text-align:center;font-weight:900;font-size:2.4cqw;
  letter-spacing:-0.01em;color:#F6F7F6;opacity:0;z-index:8;text-shadow:0 2px 16px rgba(0,0,0,0.6),0 1px 3px rgba(0,0,0,0.5);}
.cartitle .hl{background:#FFF200;color:#0a0b0a;padding:0 0.12em;box-decoration-break:clone;text-shadow:none;}
/* carousel cards layout: a horizontal track of framed cards that scrolls (style:slider, layout:cards) */
.cartrack{position:absolute;left:0;will-change:transform;}
.carcarditem{position:absolute;overflow:hidden;border-radius:14px;background:#000;transform-origin:center;
  box-shadow:0 24px 70px rgba(0,0,0,0.55);will-change:transform,opacity;}
.carcarditem img{width:100%;height:100%;object-fit:cover;display:block;}
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
    reveal = d.get("reveal")
    lbase = "#2B2D2C" if reg == "paper" else "#F6F7F6"
    for i, it in enumerate(d["items"]):
        nid, uid, lid = f"{sid}-n{i}", f"{sid}-u{i}", f"{sid}-l{i}"
        ul = f'<span class="slul" id="{uid}"></span>' if it.get("underline") else ""
        cue = start + float(it.get("cue", 0.6 + i*0.4))
        # numerals keep their count-up; a reveal style (if set) applies to the LABEL text
        if reveal in REVEALS and reveal != "rise":
            linner, lcls, lattr, ltl = reveal_text(lid, it.get("label", ""), reveal, start, cue + 0.15, dur, base=lbase)
            label_div = f'<div class="{("sllabel " + lcls).strip()}" id="{lid}"{lattr}>{linner}</div>'
        else:
            label_div = f'<div class="sllabel" id="{lid}">{esc(it.get("label",""))}</div>'
            ltl = [f'tl.fromTo("#{lid}",{{opacity:0,y:12}},{{opacity:1,y:0,duration:0.5}},{cue+0.15});']
        frag.append(f'<div class="slitem"><div class="slnumwrap"><span class="slnum" id="{nid}"></span>{ul}</div>{label_div}</div>')
        if it.get("value") is not None and it.get("from") is None:
            tl.append(f'document.getElementById("{nid}").textContent={json.dumps(str(it["value"]))};')
            tl.append(f'tl.fromTo("#{nid}",{{opacity:0,scale:0.8}},{{opacity:1,scale:1,duration:0.5,ease:"power4.out"}},{cue});')
        else:
            pre, suf = json.dumps(it.get("prefix","")), json.dumps(it.get("suffix",""))
            frm, to = float(it.get("from",0)), float(it.get("to",0))
            tl.append(f'(function(){{var el=document.getElementById("{nid}"),st={{v:{frm}}},f=function(n){{return {pre}+Math.round(n)+{suf};}};'
                      f'el.textContent=f({frm});tl.set(el,{{opacity:1}},{cue});'
                      f'tl.fromTo(st,{{v:{frm}}},{{v:{to},duration:1.4,ease:"power3.out",onUpdate:function(){{el.textContent=f(st.v);}}}},{cue});}})();')
        tl += ltl
        if it.get("underline"):
            tl.append(f'tl.fromTo("#{uid}",{{scaleX:0}},{{scaleX:1,duration:0.45,ease:"power2.out"}},{cue+1.2});')
    frag.append('</div></section>')
    pf, pt = _props_of(sid, sc)
    return g + frag + pf, tl + pt

# ── Text-reveal vocabulary ────────────────────────────────────────────────────
# gsapify.com "Text & Typography" effects, re-expressed SEEK-SAFE: every style is a
# pure function of the paused timeline's progress (no Math.random, no setTimeout), so
# each frame renders deterministically under HyperFrames' seek/render model. gsapify's
# transform-based styles (char/word/flip) are seek-safe verbatim; scramble/decode/glitch/
# typewriter use Math.random()/setTimeout live and are rewritten as progress-driven here.
# Ref (verbatim source): bridge/_ref_reveals/gsapify_animations.js.  "split" = how a line
# is broken into animatable .rv-u units (char | word) or left whole (line).
REVEALS = {
    "rise":       {"split": "line", "desc": "the whole line rises + fades up (the Vox default)"},
    "char":       {"split": "char", "desc": "letters fade + rise, staggered (gsapify stagger-letter-reveal)"},
    "word":       {"split": "word", "desc": "words slide up with a slight tilt, staggered (word-by-word-slide)"},
    "flip":       {"split": "char", "desc": "letters flip in on the X axis with depth (letter-3d-flip)"},
    "typewriter": {"split": "char", "desc": "letters appear left->right behind a caret (typewriter)"},
    "scramble":   {"split": "char", "desc": "letters cycle glyphs then resolve L->R, deterministic (text-scramble)"},
    "decode":     {"split": "char", "desc": "katakana/hex glyphs decode into the text L->R (matrix-decode)"},
    "gradient":   {"split": "line", "desc": "an accent gradient wipes the text in L->R (gradient-text-reveal)"},
    "glitch":     {"split": "line", "desc": "RGB-split + jitter that settles to clean (glitch-text)"},
}

def _rv_seg(el, seg, split, idx, reals):
    """Unit-split ONE text segment into sid-prefixed <span class="rv-u"> spans (chars or words);
    spaces stay literal (char split) or become right-margins (word split). Appends each unit's
    real text to `reals` and advances the shared counter `idx` so ids stay unique across the
    before/operative/after segments of a line."""
    out = []
    if split == "word":
        for w in seg.split(" "):
            if w == "":
                continue
            i = idx[0]; idx[0] += 1; reals.append(w)
            out.append(f'<span class="rv-u rv-w" id="{el}-u{i}">{esc(w)}</span>')
    else:
        for ch in seg:
            if ch == " ":
                out.append(" "); continue
            i = idx[0]; idx[0] += 1; reals.append(ch)
            out.append(f'<span class="rv-u rv-c" id="{el}-u{i}">{esc(ch)}</span>')
    return "".join(out)

def _rv_inner(el, text, split, operative):
    """Build a line's inner HTML for a reveal style. Returns (inner_html, reals, op_wrap_id).
    If an operative substring is present it is wrapped in .hlwrap (+ a .hlblock sweep bar); for
    split styles the operative's own units live inside the wrap so they animate with the rest."""
    idx = [0]; reals = []
    if split == "line":
        if operative and operative in text:
            b, a = text.split(operative, 1)
            inner = (f'{esc(b)}<span class="hlwrap" id="{el}-opw"><span class="rv-op">{esc(operative)}</span>'
                     f'<span class="hlblock" id="{el}-hb"></span></span>{esc(a)}')
            return inner, [text], f"{el}-opw"
        return esc(text), [text], None
    if operative and operative in text:
        b, a = text.split(operative, 1)
        inner = (_rv_seg(el, b, split, idx, reals)
                 + f'<span class="hlwrap" id="{el}-opw">' + _rv_seg(el, operative, split, idx, reals)
                 + f'<span class="hlblock" id="{el}-hb"></span></span>'
                 + _rv_seg(el, a, split, idx, reals))
        return inner, reals, f"{el}-opw"
    return _rv_seg(el, text, split, idx, reals), reals, None

def _rv_dur(style, n, dur):
    """Approx entrance length (s) so the operative sweep can fire just after the text lands."""
    if style == "char":  return 0.5 + 0.03 * n
    if style == "word":  return 0.6 + 0.08 * n
    if style == "flip":  return 0.6 + 0.05 * n
    if style == "typewriter": return min(dur * 0.55, 0.06 * n + 0.3)
    if style in ("scramble", "decode"): return min(dur * 0.7, 2.2)
    if style == "gradient": return min(dur * 0.6, 1.6)
    if style == "glitch":   return min(dur * 0.5, 0.9)
    return 0.6

def _rv_js_scramble(el, reals, start, cue, d, matrix):
    """SEEK-SAFE scramble/decode: a proxy tween is a clock; each .rv-u's glyph is a pure fn of
    (progress, index) — no Math.random. Left->right resolve; charset differs for matrix decode."""
    charset = "アカサタナハマヤラワ0123456789ABCDEF" if matrix \
              else "ABCDEFGHIJKLMNOPQRSTUVWXYZ#$%&*@"
    js = ('(function(){var el=document.getElementById("@EL@");if(!el)return;'
          'var us=el.querySelectorAll(".rv-u"),R=@ARR@,CH=@CH@,n=R.length;'
          'tl.set(el,{opacity:0},@START@);tl.set(el,{opacity:1},@CUE@);'
          'tl.to({v:0},{v:1,duration:@DUR@,ease:"none",onUpdate:function(){var p=this.progress(),rev=Math.floor(p*n*1.08);'
          'for(var i=0;i<n;i++){us[i].textContent=(i<rev)?R[i]:CH.charAt((Math.floor(p*n*3)+i*7)%CH.length);}},'
          'onComplete:function(){for(var i=0;i<n;i++)us[i].textContent=R[i];}},@CUE@);})();')
    return [js.replace("@EL@", el).replace("@ARR@", json.dumps(reals, ensure_ascii=False))
              .replace("@CH@", json.dumps(charset, ensure_ascii=False))
              .replace("@START@", f"{start}").replace("@CUE@", f"{cue}").replace("@DUR@", f"{d:.2f}")]

def _rv_js_typewriter(el, start, cue, d):
    """SEEK-SAFE typewriter: shown-count = round(progress*n). Untyped chars are display:none
    (take no space), so the trailing caret rides the typing front instead of parking at line end."""
    js = ('(function(){var el=document.getElementById("@EL@");if(!el)return;'
          'var us=el.querySelectorAll(".rv-u"),n=us.length,cr=document.getElementById("@EL@-cr");'
          'tl.set(el,{opacity:1},@START@);tl.set(us,{display:"none"},@START@);if(cr)tl.set(cr,{opacity:0},@START@);'
          'tl.to({v:0},{v:1,duration:@DUR@,ease:"none",onUpdate:function(){var sh=Math.round(this.progress()*n);'
          'for(var i=0;i<n;i++)us[i].style.display=(i<sh)?"inline-block":"none";if(cr)cr.style.opacity=1;},'
          'onComplete:function(){for(var i=0;i<n;i++)us[i].style.display="inline-block";if(cr)cr.style.opacity=0;}},@CUE@);})();')
    return [js.replace("@EL@", el).replace("@START@", f"{start}").replace("@CUE@", f"{cue}").replace("@DUR@", f"{d:.2f}")]

def _rv_js_glitch(el, start, cue, d):
    """SEEK-SAFE glitch: RGB-split text-shadow + x/skew jitter, amplitude decays with progress
    (deterministic sines), settling to clean at p=1 (onComplete clears the inline styles)."""
    js = ('(function(){var el=document.getElementById("@EL@");if(!el)return;'
          'tl.set(el,{opacity:0},@START@);tl.set(el,{opacity:1},@CUE@);'
          'tl.to({v:0},{v:1,duration:@DUR@,ease:"power2.out",onUpdate:function(){var p=this.progress(),a=1-p;'
          'var jx=Math.sin(p*44)*5*a,sk=Math.sin(p*61)*4*a;'
          'el.style.transform="translateX("+jx.toFixed(2)+"px) skewX("+sk.toFixed(2)+"deg)";'
          'el.style.textShadow=(2.5*a).toFixed(2)+"px 0 rgba(255,30,90,"+(0.85*a).toFixed(2)+"),"'
          '+(-2.5*a).toFixed(2)+"px 0 rgba(0,200,255,"+(0.85*a).toFixed(2)+")";},'
          'onComplete:function(){el.style.transform="";el.style.textShadow="";}},@CUE@);})();')
    return [js.replace("@EL@", el).replace("@START@", f"{start}").replace("@CUE@", f"{cue}").replace("@DUR@", f"{d:.2f}")]

# Simple transform-stagger styles are pure DATA: (from-vars, to-vars) GSAP object literals. Add a
# new stagger reveal by adding ONE row here — no change to _rv_entrance, reveal_text, or any block.
_RV_STAGGER = {
    "char": ('{opacity:0,yPercent:80}',
             '{opacity:1,yPercent:0,duration:0.5,stagger:0.03,ease:"back.out(1.7)"}'),
    "word": ('{opacity:0,yPercent:120,rotation:6}',
             '{opacity:1,yPercent:0,rotation:0,duration:0.6,stagger:0.08,ease:"power3.out"}'),
    "flip": ('{opacity:0,rotationX:-90,transformOrigin:"50% 50% -20px"}',
             '{opacity:1,rotationX:0,duration:0.6,stagger:0.05,ease:"back.out(1.4)"}'),
}
_RV_PERSPECTIVE = {"flip"}   # styles whose line needs a CSS perspective for 3D children

def _rv_entrance(el, style, reals, start, cue, dur):
    """The GSAP lines that reveal one text element `#el` in `style` at `cue` (frame-absolute s).
    Every branch is seek-safe (transforms/opacity, or a progress-driven proxy that mutates the DOM).
    Simple stagger styles come straight from _RV_STAGGER (data); the JS-driven ones have a builder."""
    L = f'"#{el}"'; S = f'"#{el} .rv-u"'
    if style in _RV_STAGGER:
        frm, to = _RV_STAGGER[style]
        return [f'tl.set({L},{{opacity:1}},{start});', f'tl.set({S},{{opacity:0}},{start});',
                f'tl.fromTo({S},{frm},{to},{cue});']
    if style == "typewriter":
        return _rv_js_typewriter(el, start, cue, min(dur * 0.55, 0.06 * len(reals) + 0.3))
    if style in ("scramble", "decode"):
        return _rv_js_scramble(el, reals, start, cue, min(dur * 0.7, 2.2), style == "decode")
    if style == "gradient":
        d = min(dur * 0.6, 1.6)
        # accent band sweeps L->R with the clip wipe; both ends land on a band-free window -> solid base at rest
        return [f'tl.set({L},{{opacity:1,clipPath:"inset(0 100% 0 0)",backgroundPosition:"100% 0"}},{start});',
                f'tl.fromTo({L},{{clipPath:"inset(0 100% 0 0)",backgroundPosition:"100% 0"}},'
                f'{{clipPath:"inset(0 0% 0 0)",backgroundPosition:"0% 0",duration:{d:.2f},ease:"power2.inOut"}},{cue});']
    if style == "glitch":
        return _rv_js_glitch(el, start, cue, min(dur * 0.5, 0.9))
    return [f'tl.fromTo({L},{{opacity:0,yPercent:60}},{{opacity:1,yPercent:0,duration:0.6,ease:"power3.out"}},{cue});']

def reveal_text(el, text, style, start, cue, dur, operative=None, base="#2B2D2C"):
    """THE single entry point every text-bearing block calls to reveal one text element. Returns
    (inner_html, css_class, style_attr, tl_lines): the caller stamps inner_html inside its OWN
    element (adding css_class + style_attr to it) and merges tl_lines into the frame timeline.
    Blocks NEVER branch on the concrete style, so a new reveal is added via REVEALS + _rv_entrance
    (+ an _RV_STAGGER row for a simple one) ONLY — zero block changes.
      text: the plain string to reveal · operative: optional substring to yellow-sweep after landing."""
    style = style if style in REVEALS else "rise"
    split = REVEALS[style]["split"]
    inner, reals, opw = _rv_inner(el, text, split, operative)
    cls, attr = "", ""
    if style == "gradient":
        cls, attr = "rv-grad", f' style="--rv-c1:{base};--rv-c2:#FFF200;"'
    elif style in _RV_PERSPECTIVE:
        attr = ' style="perspective:600px;"'
    if style == "typewriter":
        inner += f'<span class="rv-caret" id="{el}-cr">▌</span>'
    tl = list(_rv_entrance(el, style, reals, start, cue, dur))
    if opw:
        sweep = cue + _rv_dur(style, len(reals) or 1, dur) + 0.05
        tl.append(f'tl.fromTo("#{el}-hb",{{scaleX:0}},{{scaleX:1,duration:0.4,ease:"power2.out"}},{sweep:.2f});')
        tgt = f"#{el}-opw .rv-op" if split == "line" else f"#{el}-opw .rv-u"
        tl.append(f'tl.to("{tgt}",{{color:"#2B2D2C",duration:0.25}},{sweep+0.05:.2f});')
    return inner, cls, attr, tl

def highlight_statement(sid, sc):
    """Reusable BLOCK: a statement with ONE yellow-block sweep + optional caption-bar.
    data.reveal (default "rise") selects a text-entrance style from REVEALS (char/word/flip/
    typewriter/scramble/decode/gradient/glitch); the operative sweep still fires after the text lands."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    reg = d.get("register", "footage")
    tcls = "paper-t" if reg == "paper" else "footage-t"
    g, tl = media_ground(sid, d.get("ground", {"kind": "transparent"}), start, dur)
    frag = [f'<section class="scene clip {reg}" data-start="{start}" data-duration="{dur}" data-track-index="2">']
    frag.append(f'<div id="{sid}-k" class="kick">{esc(d.get("kicker",""))}</div>')
    tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start+0.2});')
    op = d.get("operative", "")
    reveal = d.get("reveal", "rise")
    if reveal not in REVEALS:
        reveal = "rise"
    frag.append(f'<div class="stmt {tcls}">')
    if reveal == "rise":
        # ── default path (unchanged): the whole line rises, the operative gets a yellow sweep ──
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
    else:
        # ── reveal-vocabulary path: delegate each line to reveal_text (the shared entry point) ──
        base = "#2B2D2C" if reg == "paper" else "#F6F7F6"
        for li, line in enumerate(d["lines"]):
            lid = f"{sid}-ln{li}"
            inner, cls, attr, tll = reveal_text(lid, line, reveal, start, start + 0.4 + li * 0.55, dur, operative=op, base=base)
            frag.append(f'<span class="{("ln " + cls).strip()}" id="{lid}"{attr}>{inner}</span>')
            tl += tll
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

def newshead(sid, sc):
    """Reusable BLOCK: a newspaper headline card (Vox 'newspaper animation'). Paper card (dot-grid
    newsprint) with a red date tag, a bold serif headline whose words CASCADE in with a yellow
    highlighter sweep on a phrase, a serif subhead (optional yellow highlight), a blackletter source
    masthead + drawn rule, an optional framed grayscale photo sliding in from the right, and an
    optional red hand-drawn arrow annotation. Pure GSAP+CSS/SVG, seek-safe, one merged timeline.
    data: {date?, headline:[lines]|str, highlight?, subhead?, subhighlight?, source?, image?, caption?, arrow?}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    cx0, cy0, cw, ch = 110, 128, 1700, 824      # card rect on the 1920x1080 canvas
    pad = 74
    headline = d.get("headline", [])
    if isinstance(headline, str):
        headline = [headline]
    tilt = float(d.get("tilt", 0))               # small rotation of the whole card (deg)
    ptilt = float(d.get("image_tilt", 0))        # extra rotation of the photo, relative to card (deg)
    headY = pad + (58 if d.get("date") else 6)
    has_img = bool(d.get("image"))
    if has_img:
        pw, ph = int(cw * 0.34), int(ch * 0.55)
        px_l, py_l = cw - pad - pw, headY        # photo top-right, aligned with the headline top
        textW = px_l - 46 - pad
    else:
        pw = ph = px_l = py_l = 0
        textW = cw - 2 * pad

    def words(s):  # wrap each word in a .w span (cascade target); trailing space preserves flow
        return "".join(f'<span class="w">{esc(w)}</span> ' for w in s.split(" ") if w)

    frag = [f'<div id="{sid}-bg" class="clip nhbg" data-start="{start}" data-duration="{dur}" data-track-index="0"></div>',
            f'<section id="{sid}-scene" class="clip" data-start="{start}" data-duration="{dur}" data-track-index="2" style="position:absolute;inset:0;">',
            f'<div id="{sid}-card" class="nhcard" style="left:{cx0}px;top:{cy0}px;width:{cw}px;height:{ch}px;">',
            '<div class="tex"></div><div class="vig"></div>']
    tl = [f'tl.fromTo("#{sid}-card",{{opacity:0,scale:0.965,y:22,rotation:{tilt}}},{{opacity:1,scale:1,y:0,rotation:{tilt},duration:0.6,ease:"power3.out"}},{start});']

    if d.get("date"):
        frag.append(f'<div id="{sid}-date" class="nhdate" style="left:{pad}px;top:{pad}px;">{esc(d["date"])}</div>')
        tl.append(f'tl.fromTo("#{sid}-date",{{opacity:0,y:-8}},{{opacity:1,y:0,duration:0.4,ease:"power2.out"}},{start+0.35});')

    frag.append(f'<div id="{sid}-head" class="nhhead" style="left:{pad}px;top:{headY}px;width:{textW}px;">')
    reveal = d.get("reveal")
    use_rv = reveal in REVEALS   # any reveal style overrides the native word-cascade
    hl_phrase, hl_done, line_cue = d.get("highlight", ""), False, start + 0.6
    for li, line in enumerate(headline):
        lid = f"{sid}-hl{li}"
        cue = line_cue + li * 0.42
        if use_rv:
            op = hl_phrase if (hl_phrase and not hl_done and hl_phrase in line) else None
            if op:
                hl_done = True
            inner, cls, attr, tll = reveal_text(lid, line, reveal, start, cue, dur, operative=op, base="#191712")
            frag.append(f'<span class="{("nhline " + cls).strip()}" id="{lid}"{attr}>{inner}</span>')
            tl += tll
        elif hl_phrase and not hl_done and hl_phrase in line:
            hl_done = True
            before, after = line.split(hl_phrase, 1)
            hbid = f"{lid}-y"
            inner = words(before) + f'<span class="nhhl-wrap">{words(hl_phrase)}<span class="nhhl" id="{hbid}"></span></span> ' + words(after)
            frag.append(f'<span class="nhline" id="{lid}">{inner}</span>')
            tl.append(f'tl.fromTo("#{hbid}",{{scaleX:0}},{{scaleX:1,duration:0.45,ease:"power2.out"}},{cue+0.6:.2f});')
            tl.append(f'tl.from("#{lid} .w",{{opacity:0,yPercent:70,duration:0.4,ease:"power3.out",stagger:0.045}},{cue:.2f});')
        else:
            frag.append(f'<span class="nhline" id="{lid}">{words(line)}</span>')
            tl.append(f'tl.from("#{lid} .w",{{opacity:0,yPercent:70,duration:0.4,ease:"power3.out",stagger:0.045}},{cue:.2f});')
    frag.append('</div>')
    head_end = line_cue + max(0, len(headline) - 1) * 0.42 + 0.6

    if d.get("subhead"):
        sub, subhl = d["subhead"], d.get("subhighlight", "")
        if subhl and subhl in sub:
            b, a = sub.split(subhl, 1)
            sub_html = f'{esc(b)}<span class="subhl">{esc(subhl)}</span>{esc(a)}'
        else:
            sub_html = esc(sub)
        subY = headY + len(headline) * 70 + 30
        frag.append(f'<div id="{sid}-sub" class="nhsub" style="left:{pad}px;top:{subY}px;width:{textW}px;">{sub_html}</div>')
        tl.append(f'tl.fromTo("#{sid}-sub",{{opacity:0,y:12}},{{opacity:1,y:0,duration:0.55,ease:"power3.out"}},{head_end+0.05:.2f});')

    if d.get("source"):
        frag.append(f'<div id="{sid}-src" class="nhsrc" style="left:{pad}px;top:{ch-pad-44}px;">'
                    f'<span class="mast">{esc(d["source"])}</span><span id="{sid}-rule" class="rule" style="width:340px;"></span></div>')
        tl.append(f'tl.fromTo("#{sid}-src",{{opacity:0,y:8}},{{opacity:1,y:0,duration:0.45}},{head_end+0.25:.2f});')
        tl.append(f'tl.fromTo("#{sid}-rule",{{scaleX:0}},{{scaleX:1,duration:0.5,ease:"power2.out"}},{head_end+0.4:.2f});')

    def arrow_svg(vw, vh, tx, ty):  # hand-drawn swoosh + separate two-barb head, pointing at (tx,ty)
        sx, sy = tx - 280, ty - 118
        curve = f"M {sx} {sy} C {sx+168} {sy-26}, {tx-78} {ty-140}, {tx} {ty}"
        head = f"M {tx} {ty} L {tx-46} {ty-4} M {tx} {ty} L {tx-8} {ty-48}"
        tl.append(f'tl.fromTo("#{sid}-arrow .curve",{{strokeDashoffset:1700}},{{strokeDashoffset:0,duration:0.6,ease:"power2.inOut"}},{start+1.15});')
        tl.append(f'tl.fromTo("#{sid}-arrow .head",{{strokeDashoffset:190}},{{strokeDashoffset:0,duration:0.22,ease:"power2.out"}},{start+1.65});')
        return (f'<svg id="{sid}-arrow" class="nharrow" style="left:0;top:0;width:{vw}px;height:{vh}px;" viewBox="0 0 {vw} {vh}">'
                f'<path class="curve" d="{curve}" style="stroke-dasharray:1700;stroke-dashoffset:1700;"/>'
                f'<path class="head" d="{head}" style="stroke-dasharray:190;stroke-dashoffset:190;"/></svg>')

    siblings = []  # layers that bleed BEYOND the card (drawn after it, over the paper + off its edge)
    if has_img and d.get("cutout"):
        # cutout variant: a transparent-PNG subject (grayscale + red outline) that bleeds off the
        # card's right/bottom into the dark. Lives at the section root so the card's clip can't crop it.
        cW, cH = 1080, 720
        cL, cT = cx0 + cw - 700, cy0 + 130       # big on the card's right; bleeds off the right edge
        siblings.append(f'<div id="{sid}-photo" class="nhcut" style="left:{cL}px;top:{cT}px;width:{cW}px;height:{cH}px;">'
                        f'<img src="{esc(d["image"])}" alt=""/></div>')
        tl.append(f'tl.fromTo("#{sid}-photo",{{opacity:0,x:74,scale:1.06,rotation:{ptilt-2}}},{{opacity:1,x:0,scale:1,rotation:{ptilt},duration:0.7,ease:"power3.out"}},{start+0.7});')
        if d.get("arrow"):
            siblings.append(arrow_svg(1920, 1080, cL + 40, cT + 96))
    elif has_img:
        frag.append(f'<div id="{sid}-photo" class="nhphoto" style="left:{px_l}px;top:{py_l}px;width:{pw}px;height:{ph}px;">'
                    f'<img src="{esc(d["image"])}" alt=""/></div>')
        tl.append(f'tl.fromTo("#{sid}-photo",{{opacity:0,x:44,scale:1.05,rotation:{ptilt-2}}},{{opacity:1,x:0,scale:1,rotation:{ptilt},duration:0.6,ease:"power3.out"}},{start+0.7});')
        if d.get("caption"):
            frag.append(f'<div id="{sid}-cap" class="nhcap" style="left:{px_l}px;top:{py_l+ph+10}px;width:{pw}px;">{esc(d["caption"])}</div>')
            tl.append(f'tl.fromTo("#{sid}-cap",{{opacity:0}},{{opacity:1,duration:0.4}},{start+1.25});')
        if d.get("arrow"):
            frag.append(arrow_svg(cw, ch, px_l + 16, py_l + 16))

    frag.append('</div>')       # close card (its overflow:hidden clips paper content)
    frag += siblings           # cutout/arrow bleed beyond the card
    frag.append('</section>')
    return frag, tl

def _collage_layout(layout, n):
    """Preset positions for N subjects (0..1 canvas coords) when a subject omits explicit x/y.
    Explicit per-subject x/y/scale always override these. Kept deterministic (no randomness)."""
    out = []
    if layout in ("heroes", "heroes-tight"):     # 1-2 big flanking figures + a small row in front
        tight = layout == "heroes-tight"         # tight = closer/bigger heroes + an overlapping cast row
        heroes = min(2, n); rest = n - heroes
        hx = ([0.39, 0.61] if tight else [0.30, 0.70])[:heroes]
        hs = 1.28 if tight else 1.15
        for k in range(heroes):
            out.append({"x": hx[k], "y": 0.44, "scale": hs, "rotation": -2 if k == 0 else 2,
                        "from": "left" if k == 0 else "right"})
        ry, rs, sp = (0.72, 0.46, 0.115) if tight else (0.78, 0.5, 0.16)
        for k in range(rest):
            x = 0.5 + (k - (rest - 1) / 2) * sp if rest > 1 else 0.5
            out.append({"x": x, "y": ry, "scale": rs,
                        "rotation": ((-3 if k % 2 else 3) if tight else 0), "from": "bottom"})
        return out
    if layout == "cluster":                      # loose overlapping ring around center
        for i in range(n):
            ang = (i / max(1, n)) * 2 * math.pi
            out.append({"x": 0.5 + 0.17 * math.cos(ang), "y": 0.5 + 0.12 * math.sin(ang),
                        "scale": 0.72, "rotation": (-3 if i % 2 else 3), "from": "center"})
        return out
    if layout == "scatter":                      # deterministic staggered scatter, varied sizes
        xs = [0.24, 0.52, 0.78, 0.36, 0.66, 0.5]; ys = [0.40, 0.33, 0.43, 0.68, 0.64, 0.52]
        scs = [0.85, 1.0, 0.85, 0.6, 0.6, 0.72]
        for i in range(n):
            out.append({"x": xs[i % len(xs)], "y": ys[i % len(ys)], "scale": scs[i % len(scs)],
                        "rotation": (4 if i % 2 else -4), "from": "bottom"})
        return out
    for i in range(n):                           # "row" (default): evenly spaced, same size
        x = 0.5 + (i - (n - 1) / 2) * 0.19 if n > 1 else 0.5
        out.append({"x": x, "y": 0.60, "scale": 0.72, "rotation": 0, "from": "bottom"})
    return out

def collage(sid, sc):
    """Reusable BLOCK: a kinetic COLLAGE — cut-out subjects (people/objects, transparent PNGs) that
    scale/slide IN staggered and assemble into a layered tableau on a backdrop, then hold. (Distinct
    from a photo montage: no frames/table — borderless cutouts composited into one scene.) Positions
    are explicit per subject OR from a `layout` preset. Seek-safe (transforms/opacity), one timeline.
    data: {subjects:[{src, x?, y? (0..1 center), scale?, rotation?, from?, at?, shadow?}], backdrop?, vignette?, layout?, camera?}."""
    # Deferred options (build in-place when a real beat asks — same block, don't fork a template):
    #   • parallax: opt-in idle drift tied to the camera push, each subject offset by its scale/depth
    #     (deterministic fn of tl progress → still seek-safe; no loops/yoyo).
    #   • edge:"torn": ragged cutout mask + a thin paper lip + shadow (per-subject/global), like the
    #     newshead framed/cutout split. A FULL paper-craft look (tape/halftone/kraft/handwriting) is a
    #     different identity → its own `scrapbook` template, not an option here.  (HYPERFRAMES_HANDOFF §12)
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    subjects = d.get("subjects", [])
    n = max(1, len(subjects))
    B, W, H = 560, 1920, 1080                     # base subject width @ scale 1.0; canvas
    frag, tl = [], []
    bg = d.get("backdrop", "#ffffff")             # color | image path | "transparent"
    if bg and bg != "transparent":
        if isinstance(bg, str) and (bg.endswith((".png", ".jpg", ".jpeg", ".webp")) or "/" in bg):
            frag.append(f'<div class="clip clgbg" data-start="{start}" data-duration="{dur}" data-track-index="0" '
                        f'style="background:#111;background-image:url(\'{esc(bg)}\');background-size:cover;background-position:center;"></div>')
        else:
            frag.append(f'<div class="clip clgbg" data-start="{start}" data-duration="{dur}" data-track-index="0" style="background:{esc(bg)};"></div>')
    vig = float(d.get("vignette", 0))
    if vig > 0:
        frag.append(f'<div class="clip clgvig" data-start="{start}" data-duration="{dur}" data-track-index="1" '
                    f'style="background:radial-gradient(125% 125% at 50% 45%,transparent 42%,rgba(0,0,0,{min(0.85,vig):.2f}));"></div>')
    frag.append(f'<div id="{sid}-world" class="clip clgworld" data-start="{start}" data-duration="{dur}" '
                f'data-track-index="2" data-layout-allow-overflow>')
    pos = _collage_layout(d.get("layout", "row"), n)
    _OFF = {"left": (-260, 0), "right": (260, 0), "top": (0, -220), "bottom": (0, 210), "center": (0, 0)}
    lead = 0.4
    for i, s in enumerate(subjects):
        p = pos[i]
        x, y, scl = float(s.get("x", p["x"])), float(s.get("y", p["y"])), float(s.get("scale", p["scale"]))
        rot = float(s.get("rotation", p.get("rotation", 0)))
        frm = s.get("from", p.get("from", "bottom"))
        cls = "collage-sub" + ("" if s.get("shadow", True) is False else " shadow")
        sidk = f"{sid}-s{i}"
        frag.append(f'<div id="{sidk}" class="{cls}" style="left:{x*W:.0f}px;top:{y*H:.0f}px;">'
                    f'<img src="{esc(s["src"])}" style="width:{int(B*scl)}px;"/></div>')
        ox, oy = _OFF.get(frm, _OFF["bottom"])
        cue = start + (float(s["at"]) if "at" in s else lead + i * 0.38)
        tl.append(f'tl.fromTo("#{sidk}",{{opacity:0,x:{ox},y:{oy},scale:0.72,rotation:{rot-5}}},'
                  f'{{opacity:1,x:0,y:0,scale:1,rotation:{rot},duration:0.7,ease:"back.out(1.4)"}},{cue:.2f});')
    frag.append('</div>')  # close world
    if d.get("camera") == "push":
        tl.append(f'tl.fromTo("#{sid}-world",{{scale:1}},{{scale:1.05,duration:{dur},ease:"none"}},{start});')
    return frag, tl

# d3 lays out the graph ONCE at frame load (before the timeline lines that reveal it) — the geo
# pattern: d3 for STATIC geometry (deterministic, no d3.transition/rAF), GSAP for motion (seek-safe).
# Deterministic layouts only — d3.tree/cluster (NOT forceSimulation: its jiggle() calls Math.random).
# Placeholders are string-replaced (avoids f-string brace-escaping of the JS body).
_DIAG_SETUP = r'''(function(){
  var SID="@SID@",CFG=@CFG@,NS="http://www.w3.org/2000/svg",layout=CFG.layout||"tree",dir=CFG.dir||"",tour=!!CFG.tour;
  var root=d3.hierarchy(CFG.root);
  var dx=CFG.dx||(layout==="flow"?170:210), dy=CFG.dy||(layout==="flow"?320:210);
  d3.tree().nodeSize([dx,dy])(root);
  var nodes=root.descendants();
  if(layout==="radial"){ var rstep=CFG.rstep||230; nodes.forEach(function(n){ n.__r=n.depth*rstep; }); }
  function raw(n){
    if(layout==="flow")   return [(dir==="left"?-1:1)*n.y, n.x];        // horizontal: depth->x
    if(layout==="radial") return [Math.sin(n.x)*n.__r, -Math.cos(n.x)*n.__r];
    return [n.x, (dir==="up"?-1:1)*n.y];                                 // vertical: depth->y
  }
  var P=nodes.map(raw), xs=P.map(function(p){return p[0];}), ys=P.map(function(p){return p[1];});
  var minx=Math.min.apply(null,xs),maxx=Math.max.apply(null,xs),miny=Math.min.apply(null,ys),maxy=Math.max.apply(null,ys);
  var world=document.getElementById(SID+"-world"), svg=document.getElementById(SID+"-links"), s, ox, oy;
  if(tour){                                                             // natural size, no fit — camera navigates
    s=1; var pad=260; ox=pad-minx; oy=pad-miny;
    world.style.width=(maxx-minx+2*pad)+"px"; world.style.height=(maxy-miny+2*pad)+"px";
  } else {                                                              // fit the whole graph into the safe box
    var box=CFG.box||[[220,220],[1700,820]], bw=box[1][0]-box[0][0], bh=box[1][1]-box[0][1];
    var spanx=Math.max(1,maxx-minx), spany=Math.max(1,maxy-miny);
    s=Math.min(bw/spanx, bh/spany, 1); ox=box[0][0]+(bw-spanx*s)/2-minx*s; oy=box[0][1]+(bh-spany*s)/2-miny*s;
  }
  nodes.forEach(function(n){ var p=raw(n); n.__x=ox+p[0]*s; n.__y=oy+p[1]*s;
    var el=document.getElementById(SID+"-ndw"+n.data._i); if(el){el.style.left=n.__x+"px"; el.style.top=n.__y+"px";}});
  nodes.forEach(function(n){ if(!n.parent) return; var a=n.parent, b=n, d;
    if(layout==="flow") d="M"+a.__x+","+a.__y+"C"+((a.__x+b.__x)/2)+","+a.__y+" "+((a.__x+b.__x)/2)+","+b.__y+" "+b.__x+","+b.__y;
    else                d="M"+a.__x+","+a.__y+"C"+a.__x+","+((a.__y+b.__y)/2)+" "+b.__x+","+((a.__y+b.__y)/2)+" "+b.__x+","+b.__y;
    var p=document.createElementNS(NS,"path"); p.setAttribute("d",d); p.setAttribute("class","dglink");
    p.setAttribute("id",SID+"-lk"+b.data._i); svg.appendChild(p);
    var L=p.getTotalLength(); p.style.strokeDasharray=L; p.style.strokeDashoffset=L; });
  if(tour){   // camera target per INTERNAL node in DFS pre-order — frame {node + its children} centered
    var HW=170,HH=70, cam=[];
    root.eachBefore(function(f){
      if(!f.children||!f.children.length) return;
      var g=[f].concat(f.children), x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;
      g.forEach(function(m){ x0=Math.min(x0,m.__x-HW); y0=Math.min(y0,m.__y-HH); x1=Math.max(x1,m.__x+HW); y1=Math.max(y1,m.__y+HH); });
      var gw=Math.max(1,x1-x0), gh=Math.max(1,y1-y0), z=Math.max(0.35,Math.min(1560/gw,720/gh,1.45));
      cam.push({x:960-((x0+x1)/2)*z, y:560-((y0+y1)/2)*z, s:z});
    });
    window.__DG=window.__DG||{}; window.__DG[SID]={cam:cam};
  }
})();'''

def diagram(sid, sc):
    """Reusable BLOCK: a d3-computed node-link DIAGRAM (a process / hierarchy / system). d3.hierarchy
    lays the nodes out ONCE at frame load; GSAP reveals them seek-safely — parent→child pops, each
    connector DRAWS via strokeDashoffset. Themed highlighter-editorial (ink cards on mist, or dark).
    Pure GSAP+d3-static+SVG/CSS.
      layout:"tree"(default) vertical · "flow" horizontal process · "radial" hub-and-spoke.
      dir: tree → "down"(default)|"up"; flow → "right"(default)|"left".
      camera:"tour" → a "zoom into a canvas blanket" walk: the camera frames a node, its children
        branch out, then it dives into a child and repeats (DFS pre-order), so a big tree reveals as an
        endless focus→branch→dive. (default: fit the whole graph statically.)
    data: {root:{label, sub?, hl?, shape?, children?:[...]}, layout?, dir?, camera?, kicker?, title?,
           titleHi?, register?:paper|dark, shape?:pill, dx?, dy?, rstep?, box?}."""
    import copy
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    dark = d.get("register", "paper") == "dark"
    tour = d.get("camera") == "tour"
    root = copy.deepcopy(d["root"])
    flat, kids = [], {}  # flat: (index, node, depth) in DFS pre-order; kids[i] = child indices
    def walk(nd, depth, par):
        i = len(flat); nd["_i"] = i; flat.append((i, nd, depth)); kids[i] = []
        if par >= 0:
            kids[par].append(i)
        for ch in (nd.get("children") or []):
            walk(ch, depth + 1, i)
    walk(root, 0, -1)
    n = len(flat)
    cfg = {"root": root, "layout": d.get("layout", "tree"), "dir": d.get("dir", ""), "tour": tour}
    for k in ("dx", "dy", "rstep", "box"):
        if k in d:
            cfg[k] = d[k]
    if not tour and "box" not in cfg:  # push the graph down to clear a kicker/title, above the 83% keep-out
        top = 320 if d.get("title") else (250 if d.get("kicker") else 210)
        cfg["box"] = [[220, top], [1700, 820]]
    dgd = " dg-dark" if dark else ""
    world_style = "position:absolute;left:0;top:0;" if tour else "position:absolute;inset:0;"
    frag = [f'<div class="clip dgbg{" dark" if dark else ""}" data-start="{start}" data-duration="{dur}" data-track-index="0"></div>',
            f'<div class="clip dgstage{dgd}" data-start="{start}" data-duration="{dur}" data-track-index="1" '
            f'data-layout-allow-overflow>'
            f'<div id="{sid}-world" class="dgworld" style="{world_style}">'
            f'<svg id="{sid}-links" class="dglinks{" dark" if dark else ""}" style="position:absolute;left:0;top:0;'
            f'width:100%;height:100%;overflow:visible;pointer-events:none;"></svg>']
    for i, nd, depth in flat:
        cls = "dgnode" + (" root" if i == 0 else "")
        cls += " hl" if nd.get("hl") else ""
        cls += " pill" if (nd.get("shape") or d.get("shape")) == "pill" else ""
        sub = f'<div class="sub">{esc(nd["sub"])}</div>' if nd.get("sub") else ""
        frag.append(f'<div class="dgnode-w" id="{sid}-ndw{i}"><div class="{cls}" id="{sid}-nd{i}">'
                    f'<div class="lab">{esc(nd.get("label",""))}</div>{sub}</div></div>')
    frag.append('</div></div>')  # close world + stage
    tl = [_DIAG_SETUP.replace("@SID@", sid).replace("@CFG@", json.dumps(cfg, ensure_ascii=False))]

    def pop(j, cue, dr=0.5):
        return f'tl.fromTo("#{sid}-nd{j}",{{opacity:0,scale:0.55}},{{opacity:1,scale:1,duration:{dr},ease:"back.out(1.7)"}},{cue:.2f});'
    def draw(j, cue, dr=0.5):
        return f'tl.to("#{sid}-lk{j}",{{strokeDashoffset:0,duration:{dr},ease:"power2.inOut"}},{cue:.2f});'

    if tour:
        focus = [i for i, nd, depth in flat if kids[i]]   # internal nodes, DFS pre-order = the dive path
        lead = 0.6
        stepdur = max(1.1, (dur - lead - 0.6) / max(1, len(focus)))
        tl.append(f'tl.set("#{sid}-world",{{transformOrigin:"0px 0px"}},{start});')
        tl.append(pop(0, start + 0.15, 0.55))            # root appears first
        for s, fi in enumerate(focus):
            cs = start + lead + s * stepdur
            cam = f'window.__DG["{sid}"].cam[{s}]'
            if s == 0:
                tl.append(f'tl.set("#{sid}-world",{{x:{cam}.x,y:{cam}.y,scale:{cam}.s}},{start});')
            else:      # glide the camera to this node, arriving just before its children branch out
                tl.append(f'tl.to("#{sid}-world",{{x:{cam}.x,y:{cam}.y,scale:{cam}.s,duration:0.9,ease:"power2.inOut"}},{cs-0.9:.2f});')
            for ci, j in enumerate(kids[fi]):            # this focus node's children branch out
                rc = cs + 0.2 + ci * 0.16
                tl.append(draw(j, rc, 0.45))
                tl.append(pop(j, rc + 0.12, 0.45))
    else:
        lead = 0.5
        step = max(0.28, (dur - lead - 1.0) / max(1, n))
        for i, nd, depth in flat:
            cue = start + lead + i * step
            if i > 0:
                tl.append(draw(i, cue))
            tl.append(pop(i, cue + (0.15 if i > 0 else 0)))

    if d.get("kicker"):
        frag.append(f'<div id="{sid}-k" class="clip dgkick{" on-dark" if dark else ""}" data-start="{start}" '
                    f'data-duration="{dur}" data-track-index="3">{esc(d["kicker"])}</div>')
        tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start+0.2});')
    if d.get("title"):
        t, op = d["title"], d.get("titleHi", "")
        html_t = (f'{esc(t.split(op,1)[0])}<span class="hl">{esc(op)}</span>{esc(t.split(op,1)[1])}'
                  if op and op in t else esc(t))
        frag.append(f'<div id="{sid}-title" class="clip dgtitle{" on-dark" if dark else ""}" data-start="{start}" '
                    f'data-duration="{dur}" data-track-index="4">{html_t}</div>')
        tl.append(f'tl.fromTo("#{sid}-title",{{opacity:0,y:-12}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},{start+0.35});')
    return frag, tl


def _cmp_media(pid, spec, mtrack, start, dur):
    """A comparison panel's media fill (image bg OR framework-owned <video>) + its effects stack:
    kenburns (scale the wrapper so the injected video frame scales too), scrim, vignette, grayscale, tint."""
    frag, tl = [], []
    mid = f"{pid}-media"
    if spec.get("type") == "video":
        ms = f' data-media-start="{spec["media_start"]}"' if spec.get("media_start") is not None else ""
        gf = "filter:grayscale(1) contrast(1.03);" if spec.get("grayscale") else ""
        frag.append(f'<div class="cmp-media" id="{mid}" style="{gf}">'
                    f'<video class="clip" data-start="{start}" data-duration="{dur}" data-track-index="{mtrack}" '
                    f'src="{esc(spec["src"])}" muted playsinline{ms}></video></div>')
    else:
        gf = "filter:grayscale(1) contrast(1.03);" if spec.get("grayscale") else ""
        frag.append(f'<div class="cmp-media" id="{mid}" style="background-image:url(\'{esc(spec["src"])}\');{gf}"></div>')
    kb = spec.get("kenburns", True)
    if kb:
        f0, f1 = kb if isinstance(kb, list) else [1.05, 1.16]
        tl.append(f'tl.fromTo("#{mid}",{{scale:{f0}}},{{scale:{f1},duration:{dur},ease:"none"}},{start});')
    if spec.get("scrim", True):
        frag.append('<div class="cmp-scrim"></div>')
    vig = float(spec.get("vignette", 0) or 0)
    if vig > 0:
        frag.append(f'<div class="cmp-vig" style="box-shadow:inset 0 0 22cqw rgba(0,0,0,{min(0.92,vig):.2f});"></div>')
    if spec.get("tint"):
        frag.append(f'<div class="cmp-tint" style="background:{esc(spec["tint"])};"></div>')
    return frag, tl

def _cmp_text(pid, spec, start, dur, reg, bottom):
    """A comparison panel's text content: optional kicker + a 1-3 line title (optional highlight sweep)."""
    frag, tl = [], []
    frag.append(f'<div class="cmp-txt {reg}{"" if bottom else " mid"}">')
    if spec.get("kicker"):
        frag.append(f'<div class="k" id="{pid}-k">{esc(spec["kicker"])}</div>')
        tl.append(f'tl.fromTo("#{pid}-k",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start+0.45});')
    title = spec.get("title")
    if title is not None:
        lines = title if isinstance(title, list) else [title]
        op = spec.get("highlight", "")
        reveal = spec.get("reveal")
        rbase = "#2B2D2C" if reg == "paper" else "#F6F7F6"
        frag.append('<div class="t">')
        for li, ln in enumerate(lines):
            tid = f"{pid}-t{li}"
            if reveal in REVEALS and reveal != "rise":
                inner, cls, attr, tll = reveal_text(tid, ln, reveal, start, start + 0.6 + li * 0.28, dur, operative=(op or None), base=rbase)
                frag.append(f'<span class="{("ln " + cls).strip()}" id="{tid}"{attr}>{inner}</span>')
                tl += tll
            else:
                if op and op in ln:
                    b, a = ln.split(op, 1)
                    inner = f'{esc(b)}<span class="mark">{esc(op)}</span>{esc(a)}'
                else:
                    inner = esc(ln)
                frag.append(f'<span class="ln" id="{tid}">{inner}</span>')
                tl.append(f'tl.fromTo("#{tid}",{{opacity:0,yPercent:55}},{{opacity:1,yPercent:0,duration:0.55,'
                          f'ease:"power3.out"}},{start+0.6+li*0.28:.2f});')
        frag.append('</div>')
    frag.append('</div>')
    return frag, tl

def _cmp_stat(pid, spec, start, dur, reg):
    """A comparison panel's single big stat: a count-up (from/to) or a fixed value + label."""
    frag = [f'<div class="cmp-num {reg}"><div class="v" id="{pid}-v"></div>'
            + (f'<div class="l" id="{pid}-l">{esc(spec["label"])}</div>' if spec.get("label") else "") + '</div>']
    cue = start + 0.6
    pre, suf = json.dumps(spec.get("prefix", "")), json.dumps(spec.get("suffix", ""))
    tl = []
    if spec.get("value") is not None and spec.get("from") is None:
        tl.append(f'document.getElementById("{pid}-v").textContent={json.dumps(str(spec["value"]))};')
        tl.append(f'tl.fromTo("#{pid}-v",{{opacity:0,scale:0.8}},{{opacity:1,scale:1,duration:0.55,ease:"power4.out"}},{cue});')
    else:
        frm, to = float(spec.get("from", 0)), float(spec.get("to", 0))
        tl.append(f'(function(){{var el=document.getElementById("{pid}-v"),st={{v:{frm}}},f=function(n){{return {pre}+Math.round(n)+{suf};}};'
                  f'el.textContent=f({frm});tl.set(el,{{opacity:1}},{cue});'
                  f'tl.fromTo(st,{{v:{frm}}},{{v:{to},duration:1.4,ease:"power3.out",onUpdate:function(){{el.textContent=f(st.v);}}}},{cue});}})();')
    if spec.get("label"):
        tl.append(f'tl.fromTo("#{pid}-l",{{opacity:0,y:12}},{{opacity:1,y:0,duration:0.5}},{cue+0.2});')
    return frag, tl

def _panel_content(pid, spec, mtrack, start, dur):
    """Dispatch one comparison side to its content type. image/video → media(+effects)+optional overlaid
    title; text → paper/dark fill + centered statement; stat → fill + big number."""
    t = spec.get("type", "text")
    if t in ("image", "video"):
        frag, tl = _cmp_media(pid, spec, mtrack, start, dur)
        if spec.get("title") or spec.get("kicker"):
            tf, tt = _cmp_text(pid, spec, start, dur, reg="footage", bottom=True)
            frag += tf; tl += tt
        return frag, tl
    reg = spec.get("register", "paper")
    bg = spec.get("bg", "#F1F3F2" if reg == "paper" else "#111417")
    frag = [f'<div class="cmp-paper" style="background:{esc(bg)};"></div>']
    if t == "stat":
        f2, t2 = _cmp_stat(pid, spec, start, dur, reg)
    else:  # text
        f2, t2 = _cmp_text(pid, spec, start, dur, reg=("paper" if reg == "paper" else "footage"), bottom=False)
    return frag + f2, t2

def comparison(sid, sc):
    """Reusable BLOCK: a split A-vs-B / before-after CONTRAST. The canvas splits into two panels
    (vertical=side-by-side default, horizontal=stacked); each panel slides in; a divider draws + an
    optional center VS badge. Each side (`left`/`right`) is ANY content type — an `image` (Ken-Burns +
    scrim/vignette/grayscale/tint), a `text` block, a `stat`, or a real `video`. Two `style`s: `seamless`
    (panels tile, thin divider) or `framed` (bordered cards with a gap + backdrop). Seek-safe, one timeline.
      VIDEO uses archetype B: the panel is a transparent HOLE; the actual <video> is mounted at the INDEX
      root by `inject_comparison_videos.py` (positioned to the panel rect) — the framework's only legal
      motion-video path. So a video-vs-video is literally two stacked root videos with the frame's chrome on top.
    data: {left:{type, ...}, right:{type, ...}, axis?:vertical|horizontal, style?:seamless|framed,
           backdrop?:color, vs?:bool|str, kicker?, title?, titleHi?}.
      side spec: {type:image|video|text|stat, label?, + type fields:
        image: {src, kenburns?:[f,t]|bool, scrim?, vignette?, grayscale?, tint?, kicker?, title?, highlight?}
        video: {src, media_start?, scrim?, grayscale?, kicker?, title?, highlight?}  (mounted at index root)
        text:  {kicker?, title:str|[lines], highlight?, register?:paper|footage, bg?}
        stat:  {from,to | value, prefix?, suffix?, label, register?}}"""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    axis = d.get("axis", "vertical")
    framed = d.get("style", "seamless") == "framed"
    backdrop = d.get("backdrop", "#0a0b0c")
    W, H = 1920, 1080
    M = 46 if framed else 0                      # outer margin
    G = 34 if framed else 6                       # gap between the two panels
    topPad = 150 if (d.get("title") or d.get("kicker")) else 0
    sides = [d["left"], d["right"]]
    any_video = any(s.get("type") == "video" for s in sides)
    frag, tl = [], []
    # opaque backdrop base — skipped when a side is video (that region must stay transparent so the
    # root-mounted video shows through; the index body supplies the backdrop instead).
    if not any_video:
        frag.append(f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="0" '
                    f'style="position:absolute;inset:0;background:{esc(backdrop)};"></div>')
    top = topPad + M
    if axis == "horizontal":
        ph = (H - top - M - G) // 2
        geoms = [("top", M, top, W - 2 * M, ph), ("bottom", M, top + ph + G, W - 2 * M, ph)]
        div_style = f"left:0;top:{topPad+(H-topPad)//2-3}px;width:{W}px;height:6px;transform-origin:left center;"
        div_prop = "scaleX"
    else:
        pw = (W - 2 * M - G) // 2
        geoms = [("left", M, top, pw, H - top - M), ("right", M + pw + G, top, pw, H - top - M)]
        div_style = f"left:{W//2-3}px;top:{topPad}px;width:6px;height:{H-topPad}px;transform-origin:center;"
        div_prop = "scaleY"
    for k, (spec, geom) in enumerate([(sides[0], geoms[0]), (sides[1], geoms[1])]):
        side, gx, gy, gw, gh = geom
        pid = f"{sid}-{'l' if k == 0 else 'r'}"
        is_video = spec.get("type") == "video"
        fcls = " framed" if framed else ""
        vattrs = ""
        if is_video:   # transparent hole + data the injector reads to mount the root <video> at this rect
            fcls += " cmp-vhole"
            vattrs = (f' data-cmp-video="{esc(spec["src"])}" data-cmp-rect="{gx},{gy},{gw},{gh}" '
                      f'data-cmp-id="{pid}-vid" data-cmp-mstart="{spec.get("media_start",0)}" '
                      f'data-cmp-framed="{1 if framed else 0}" data-cmp-gray="{1 if spec.get("grayscale") else 0}"')
        frag.append(f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="{1+k}" '
                    f'style="position:absolute;inset:0;">'
                    f'<div id="{pid}" class="cmp-panel{fcls}"{vattrs} style="left:{gx}px;top:{gy}px;width:{gw}px;height:{gh}px;">')
        if is_video:
            inner_f, inner_t = [], []
            if spec.get("scrim", True):
                inner_f.append('<div class="cmp-scrim"></div>')
            if spec.get("title") or spec.get("kicker"):
                tf, tt = _cmp_text(pid, spec, start, dur, reg="footage", bottom=True)
                inner_f += tf; inner_t += tt
        else:
            inner_f, inner_t = _panel_content(pid, spec, 5 + k, start, dur)
        frag += inner_f
        if spec.get("label"):
            frag.append(f'<div class="cmp-label" id="{pid}-lbl">{esc(spec["label"])}</div>')
        frag.append('</div></div>')
        tl += inner_t
        pcue = start + (0.1 if k == 0 else 0.3)
        if is_video:   # fade the overlays in (the root video hard-cuts in at its data-start); don't slide the hole
            tl.append(f'tl.fromTo("#{pid}",{{opacity:0}},{{opacity:1,duration:0.6}},{pcue});')
        else:
            ax, off = {"left": ("xPercent", -12), "right": ("xPercent", 12),
                       "top": ("yPercent", -12), "bottom": ("yPercent", 12)}.get(side, ("xPercent", 0))
            tl.append(f'tl.fromTo("#{pid}",{{opacity:0,{ax}:{off}}},{{opacity:1,{ax}:0,duration:0.7,ease:"power3.out"}},{pcue});')
        if spec.get("label"):
            tl.append(f'tl.fromTo("#{pid}-lbl",{{opacity:0,y:-8}},{{opacity:1,y:0,duration:0.4}},{pcue+0.5});')
    # divider (seamless only — framed uses the gap) + VS badge + optional title, on one overlay clip
    frag.append(f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="3" style="position:absolute;inset:0;pointer-events:none;">')
    if not framed:
        frag.append(f'<div id="{sid}-div" class="cmp-div" style="{div_style}"></div>')
        tl.append(f'tl.fromTo("#{sid}-div",{{{div_prop}:0}},{{{div_prop}:1,duration:0.5,ease:"power2.inOut"}},{start+0.2});')
    if d.get("vs"):
        cx, cy = W // 2, topPad + (H - topPad) // 2
        frag.append(f'<div class="cmp-vs-w" style="left:{cx}px;top:{cy}px;"><div id="{sid}-vs" class="cmp-vs">'
                    f'{esc(d["vs"] if isinstance(d["vs"], str) else "VS")}</div></div>')
        tl.append(f'tl.fromTo("#{sid}-vs",{{scale:0}},{{scale:1,duration:0.5,ease:"back.out(2.2)"}},{start+0.7});')
    if d.get("title") or d.get("kicker"):
        t, op = d.get("title", ""), d.get("titleHi", "")
        html_t = (f'{esc(t.split(op,1)[0])}<span class="hl">{esc(op)}</span>{esc(t.split(op,1)[1])}'
                  if op and op in t else esc(t))
        kick = f'<div class="k" id="{sid}-hk">{esc(d["kicker"])}</div>' if d.get("kicker") else ""
        frag.append(f'<div class="cmp-htitle">{kick}<div class="t" id="{sid}-ht">{html_t}</div></div>')
        if d.get("kicker"):
            tl.append(f'tl.fromTo("#{sid}-hk",{{opacity:0,y:-6}},{{opacity:1,y:0,duration:0.45}},{start+0.15});')
        if d.get("title"):
            tl.append(f'tl.fromTo("#{sid}-ht",{{opacity:0,y:-8}},{{opacity:1,y:0,duration:0.55,ease:"power3.out"}},{start+0.3});')
    frag.append('</div>')
    return frag, tl

def _gallery_cells(n, cols, gx, gy, gw, gh, gap, masonry):
    """[(x,y,w,h)] for n items. grid: uniform cells, partial last row centered. masonry:
    round-robin column packing with a deterministic height pattern, vertically fit-scaled."""
    rows = max(1, math.ceil(n / cols))
    cw = (gw - (cols - 1) * gap) / cols
    if not masonry:
        ch = (gh - (rows - 1) * gap) / rows
        out = []
        for i in range(n):
            r, c = divmod(i, cols)
            cnt = min(cols, n - r * cols)
            row_w = cnt * cw + (cnt - 1) * gap
            sx = gx + (gw - row_w) / 2
            out.append((sx + c * (cw + gap), gy + r * (ch + gap), cw, ch))
        return out
    base = (gh - (rows - 1) * gap) / rows          # masonry: varied heights, column-packed
    pat = [1.0, 1.32, 0.8, 1.14, 0.92, 1.22]
    colY = [gy] * cols
    tmp = []
    for i in range(n):
        c = i % cols
        h = base * pat[i % len(pat)]
        tmp.append((gx + c * (cw + gap), c, h))
        colY[c] += h + gap
    used = max(colY) - gy - gap
    sf = min(1.0, gh / used) if used > 0 else 1.0   # fit tallest column into the grid box
    colY = [gy] * cols
    out = []
    for x, c, h in tmp:
        h2 = h * sf
        out.append((x, colY[c], cw, h2))
        colY[c] += h2 + gap * sf
    return out


def gallery(sid, sc):
    """Reusable BLOCK: a grid/masonry of framed images that reveal in a staggered cascade
    (center-out by default), then OPTIONALLY spotlight one image — it scales up + lifts while
    the others dim + blur (background-blur emphasis). Pure GSAP+CSS, seek-safe: reveal is
    transform/opacity only; the spotlight adds a deterministic filter:blur hold on the non-hero
    cards. Refs: gsapify masonry-cascade (035, de-randomized — NO Math.random / from:'random') +
    staggered-grid-reveal (center-out stagger).
    data: {images:[{src,caption?}|str], cols?, layout?:grid|masonry, gap?, frame?(bool),
           backdrop?, vignette?, from?:center|start|edges|end, title?, titleHi?, captions?(bool),
           highlight?:int(0-based), highlight_at?(s), highlight_caption?}."""
    # Deferred (build in-place when a beat asks, don't fork): highlight_zoom (Ken-Burns push
    # toward the hero via a world scale), polaroid per-card resting tilt, multi-spotlight swap.
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    imgs = [({"src": x} if isinstance(x, str) else x) for x in d.get("images", [])]
    n = max(1, len(imgs))
    W = 1920
    frame = d.get("frame", True)
    gap = float(d.get("gap", 24))
    cols = int(d.get("cols") or (n if n <= 3 else 3 if n <= 6 else 4))
    cols = max(1, min(cols, n))
    has_title = bool(d.get("title"))
    gx, gw = 168, W - 2 * 168
    gy = 196 if has_title else 132
    gy_bot = 884                                   # keep clear of the ~83% caption keep-out
    gh = gy_bot - gy
    cells = _gallery_cells(n, cols, gx, gy, gw, gh, gap, d.get("layout") == "masonry")

    frag, tl = [], []
    bg = d.get("backdrop", "#17181A")
    if bg and bg != "transparent":
        if isinstance(bg, str) and (bg.endswith((".png", ".jpg", ".jpeg", ".webp")) or "/" in bg):
            frag.append(f'<div class="clip galbg" data-start="{start}" data-duration="{dur}" data-track-index="0" '
                        f'style="background:#111;background-image:url(\'{esc(bg)}\');background-size:cover;background-position:center;"></div>')
        else:
            frag.append(f'<div class="clip galbg" data-start="{start}" data-duration="{dur}" data-track-index="0" style="background:{esc(bg)};"></div>')
    vig = float(d.get("vignette", 0))
    if vig > 0:
        frag.append(f'<div class="clip galvig" data-start="{start}" data-duration="{dur}" data-track-index="1" '
                    f'style="background:radial-gradient(125% 125% at 50% 45%,transparent 40%,rgba(0,0,0,{min(0.85,vig):.2f}));"></div>')

    hero = d.get("highlight")
    hero = int(hero) if isinstance(hero, (int, float)) and 0 <= int(hero) < n else None

    world = [f'<div id="{sid}-world" class="clip galworld" data-start="{start}" data-duration="{dur}" '
             f'data-track-index="2" data-layout-allow-overflow>']

    # reveal order — deterministic (NO random): center-out / start / edges / end
    cx, cy = gx + gw / 2, gy + gh / 2
    ctr = [(x + w / 2, y + h / 2) for (x, y, w, h) in cells]
    frm = d.get("from", "center")
    if frm == "center":
        order = sorted(range(n), key=lambda i: (ctr[i][0] - cx) ** 2 + (ctr[i][1] - cy) ** 2)
    elif frm == "edges":
        order = sorted(range(n), key=lambda i: -((ctr[i][0] - cx) ** 2 + (ctr[i][1] - cy) ** 2))
    elif frm == "end":
        order = list(reversed(range(n)))
    else:
        order = list(range(n))
    kpos = {idx: k for k, idx in enumerate(order)}

    lead = 0.4
    span = min(1.3, dur * 0.34)
    step = span / max(1, n - 1)
    reveal_end = lead + (n - 1) * step + 0.6
    show_caps = bool(d.get("captions"))
    for i, im in enumerate(imgs):
        x, y, w, h = cells[i]
        iid = f"{sid}-i{i}"
        z = 6 if i == hero else 1
        fcls = "galcard" + ("" if frame else " noframe")
        world.append(f'<div id="{iid}" class="{fcls}" style="left:{x:.0f}px;top:{y:.0f}px;width:{w:.0f}px;height:{h:.0f}px;z-index:{z};">'
                     f'<img src="{esc(im["src"])}" alt=""/></div>')
        rot = -8 if i % 2 == 0 else 8
        cue = start + lead + kpos[i] * step
        tl.append(f'tl.fromTo("#{iid}",{{opacity:0,scale:0.78,y:64,rotation:{rot}}},'
                  f'{{opacity:1,scale:1,y:0,rotation:0,duration:0.6,ease:"back.out(1.5)"}},{cue:.2f});')
        if show_caps and im.get("caption"):
            cid = f"{sid}-ic{i}"
            world.append(f'<div id="{cid}" class="galcap" style="left:{x:.0f}px;top:{y + h + 8:.0f}px;width:{w:.0f}px;z-index:{z};"></div>')
            tl.append(f'document.getElementById("{cid}").textContent={json.dumps(str(im["caption"]))};')
            tl.append(f'tl.fromTo("#{cid}",{{opacity:0}},{{opacity:0.85,duration:0.4}},{cue + 0.3:.2f});')

    if d.get("title"):
        t, op = d["title"], d.get("titleHi", "")
        html_t = (f'{esc(t.split(op, 1)[0])}<span class="hl">{esc(op)}</span>{esc(t.split(op, 1)[1])}'
                  if op and op in t else esc(t))
        world.append(f'<div id="{sid}-title" class="galtitle" style="z-index:8;">{html_t}</div>')
        tl.append(f'tl.fromTo("#{sid}-title",{{opacity:0,y:-12}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},{start + 0.2});')

    # spotlight one: hero scales up + lifts (raised z); others dim + blur = "background blurred"
    if hero is not None:
        hl_cue = start + float(d.get("highlight_at", reveal_end + 0.4))
        for i in range(n):
            if i == hero:
                continue
            tl.append(f'tl.to("#{sid}-i{i}",{{opacity:0.32,scale:0.93,filter:"blur(7px)",duration:0.6,ease:"power2.inOut"}},{hl_cue:.2f});')
        tl.append(f'tl.to("#{sid}-i{hero}",{{scale:1.16,duration:0.6,ease:"power3.out"}},{hl_cue:.2f});')
        if d.get("highlight_caption"):
            hx, hy, hw, hh = cells[hero]
            hcid = f"{sid}-hcap"
            cap_top = min(hy + hh / 2 + hh * 1.16 / 2 + 18, 900)
            world.append(f'<div id="{hcid}" class="galhcap" style="left:{hx + hw / 2 - 320:.0f}px;top:{cap_top:.0f}px;width:640px;z-index:9;">{esc(d["highlight_caption"])}</div>')
            tl.append(f'tl.fromTo("#{hcid}",{{opacity:0,y:8}},{{opacity:1,y:0,duration:0.5,ease:"power3.out"}},{hl_cue + 0.35:.2f});')

    world.append('</div>')  # close world
    return frag + world, tl


def carousel(sid, sc):
    """Reusable BLOCK: a TEMPORAL sequence of images, auto-advancing, one in focus — the moving
    cousin of `gallery` (which lays a grid out at once). Styles:
      style:"slider", layout:"full" (default) — full-bleed one-at-a-time; transition kenburns |
        crossfade (kenburns = crossfade + a slow per-slide scale drift, alternating zoom in/out).
      style:"slider", layout:"cards" — a horizontal CARD SCROLL: a row of framed cards, the track
        slides so the active card centres (neighbours peek at the edges); active scales up, rest dim.
      style:"coverflow" — a 3D coverflow: the centre card faces forward + scales up, neighbours angle
        back in Z and FADE out by distance. Card size / spacing / depth / vertical position are inputs.
    Pure GSAP+CSS, seek-safe: opacity + transforms only (coverflow uses rotateY/translateZ/scale in a
    perspective + preserve-3d stage; NO Math.random, NO repeat:-1). Refs: gsapify parallax-slider (037
    ken-burns, un-looped) + coverflow-3d + draggable-carousel (click/drag -> time-driven).
    data: {images:[{src,caption?}|str], style?:slider|coverflow, layout?:full|cards (slider),
           transition?:kenburns|crossfade (slider/full), hold?, backdrop?, vignette?, title?, titleHi?,
           captions?, card_w?, card_h?, gap?(cards), spacing?/depth?/fade?/y?(coverflow)}."""
    # Deferred (build in-place when a beat asks, don't fork): transition:"push"/parallax-bg, style:"strip"
    # (marquee — ONE linear x tween over a cloned track, NOT repeat:-1), style:"deck" (card toss),
    # focus/dwell (end on a chosen slide).  (HYPERFRAMES_HANDOFF §12)
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    imgs = [({"src": x} if isinstance(x, str) else x) for x in d.get("images", [])]
    n = max(1, len(imgs))
    style = d.get("style", "slider")
    frag, tl = [], []
    bg = d.get("backdrop", "#101014")
    if bg and bg != "transparent":
        if isinstance(bg, str) and (bg.endswith((".png", ".jpg", ".jpeg", ".webp")) or "/" in bg):
            frag.append(f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="0" '
                        f'style="position:absolute;inset:0;background:#000;background-image:url(\'{esc(bg)}\');background-size:cover;background-position:center;"></div>')
        else:
            frag.append(f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="0" style="position:absolute;inset:0;background:{esc(bg)};"></div>')
    vig = float(d.get("vignette", 0))
    if vig > 0:
        frag.append(f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="1" '
                    f'style="position:absolute;inset:0;pointer-events:none;background:radial-gradient(125% 125% at 50% 45%,transparent 40%,rgba(0,0,0,{min(0.85,vig):.2f}));"></div>')

    world = [f'<div id="{sid}-world" class="clip carworld" data-start="{start}" data-duration="{dur}" '
             f'data-track-index="2" data-layout-allow-overflow>']
    intro = 0.5
    hold = float(d.get("hold") or max(0.9, (dur - intro) / n))
    cap_in = lambda i: start + intro + i * hold
    show_caps = bool(d.get("captions"))

    W = 1920
    if style == "coverflow":
        # card size / spacing / depth / vertical position + fade are all inputs
        CW, CH = int(d.get("card_w", 700)), int(d.get("card_h", 480))
        spacing, depth = float(d.get("spacing", 330)), float(d.get("depth", 175))
        fade = float(d.get("fade", 0.32))         # opacity lost per step of distance (smooth edge fade)
        cyf = float(d.get("y", 0.5))              # vertical centre as a fraction of height
        world.append(f'<div class="carstage"><div id="{sid}-3d" class="car3d">')
        for i, im in enumerate(imgs):
            world.append(f'<div id="{sid}-c{i}" class="carcard" style="width:{CW}px;height:{CH}px;margin-left:{-CW // 2}px;margin-top:{-CH // 2}px;top:{cyf * 100:.1f}%;">'
                         f'<img src="{esc(im["src"])}" alt=""/></div>')
        world.append('</div></div>')

        def cf(off):                              # transform for a card `off` steps from focus
            x = off * spacing
            ry = max(-60, min(60, off * -34))
            z = depth * 0.4 if off == 0 else -abs(off) * depth
            scl = 1.14 if off == 0 else 0.82
            op = max(0.0, 1 - abs(off) * fade)    # smooth distance fade (no hard cut)
            return x, ry, z, scl, op
        for i in range(n):                        # initial arrangement (focus 0) + a scale-in reveal
            x, ry, z, scl, op = cf(i - 0)
            tl.append(f'tl.set("#{sid}-c{i}",{{xPercent:-50,yPercent:-50,x:{x},z:{z},rotationY:{ry},scale:{scl},opacity:0}},{start});')
            tl.append(f'tl.to("#{sid}-c{i}",{{opacity:{op:.3f},duration:0.6,ease:"power2.out"}},{start + 0.15 + abs(i) * 0.06:.2f});')
        for s in range(1, n):                     # advance focus one card at a time
            cue = cap_in(s)
            for i in range(n):
                x, ry, z, scl, op = cf(i - s)
                tl.append(f'tl.to("#{sid}-c{i}",{{x:{x},z:{z},rotationY:{ry},scale:{scl},opacity:{op:.3f},duration:0.6,ease:"power2.inOut"}},{cue:.2f});')
    elif style == "slider" and d.get("layout") == "cards":
        # CARD SCROLL: a row of framed cards; the track slides so the active card centres
        # (neighbours peek at the edges); active scales up, the rest dim.
        CW, CH = int(d.get("card_w", 820)), int(d.get("card_h", 500))
        cgap, cyf = float(d.get("gap", 60)), float(d.get("y", 0.5))
        world.append(f'<div id="{sid}-track" class="cartrack" style="top:{cyf * 100:.1f}%;height:{CH}px;">')
        for i, im in enumerate(imgs):
            world.append(f'<div id="{sid}-k{i}" class="carcarditem" style="left:{i * (CW + cgap)}px;top:{-CH // 2}px;width:{CW}px;height:{CH}px;">'
                         f'<img src="{esc(im["src"])}" alt=""/></div>')
        world.append('</div>')
        trackx = lambda a: W / 2 - (a * (CW + cgap) + CW / 2)
        tl.append(f'tl.set("#{sid}-track",{{x:{trackx(0):.0f}}},{start});')
        for i in range(n):                        # staggered reveal at resting emphasis (card 0 active)
            act = (i == 0)
            rest = 1.0 if act else 0.86
            tl.append(f'tl.fromTo("#{sid}-k{i}",{{opacity:0,y:44,scale:{rest}}},'
                      f'{{opacity:{1 if act else 0.5},y:0,scale:{rest},duration:0.55,ease:"power3.out"}},{start + 0.15 + i * 0.08:.2f});')
        for a in range(1, n):                     # scroll the track + swap emphasis
            cue = cap_in(a)
            tl.append(f'tl.to("#{sid}-track",{{x:{trackx(a):.0f},duration:0.75,ease:"power3.inOut"}},{cue:.2f});')
            tl.append(f'tl.to("#{sid}-k{a}",{{scale:1.0,opacity:1,duration:0.6,ease:"power2.out"}},{cue:.2f});')
            tl.append(f'tl.to("#{sid}-k{a - 1}",{{scale:0.86,opacity:0.5,duration:0.6,ease:"power2.inOut"}},{cue:.2f});')
    else:                                         # slider — full-bleed, one at a time
        transition = d.get("transition", "kenburns")
        for i, im in enumerate(imgs):
            sidk = f"{sid}-s{i}"
            world.append(f'<div id="{sidk}" class="carslide" style="z-index:{i + 1};"><img src="{esc(im["src"])}" alt=""/></div>')
            cin = cap_in(i)
            tl.append(f'tl.fromTo("#{sidk}",{{opacity:0}},{{opacity:1,duration:0.7,ease:"power2.out"}},{cin:.2f});')
            if transition == "kenburns":
                z0, z1 = (1.05, 1.14) if i % 2 == 0 else (1.13, 1.04)   # alternate slow zoom in / out
                tl.append(f'tl.fromTo("#{sidk} img",{{scale:{z0}}},{{scale:{z1},duration:{hold + 0.9:.2f},ease:"none"}},{cin:.2f});')
            if i < n - 1:                          # crossfade out as the next fades in
                tl.append(f'tl.to("#{sidk}",{{opacity:0,duration:0.7,ease:"power2.in"}},{cap_in(i + 1):.2f});')

    if show_caps:                                 # per-slide caption, tied to when its slide is focused
        for i, im in enumerate(imgs):
            if not im.get("caption"):
                continue
            cid = f"{sid}-cap{i}"
            world.append(f'<div id="{cid}" class="carcap"></div>')
            tl.append(f'document.getElementById("{cid}").textContent={json.dumps(str(im["caption"]))};')
            tl.append(f'tl.fromTo("#{cid}",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5,ease:"power3.out"}},{cap_in(i) + 0.15:.2f});')
            if i < n - 1:
                tl.append(f'tl.to("#{cid}",{{opacity:0,duration:0.4,ease:"power2.in"}},{cap_in(i + 1):.2f});')

    if d.get("title"):
        t, op = d["title"], d.get("titleHi", "")
        html_t = (f'{esc(t.split(op, 1)[0])}<span class="hl">{esc(op)}</span>{esc(t.split(op, 1)[1])}'
                  if op and op in t else esc(t))
        world.append(f'<div id="{sid}-title" class="cartitle">{html_t}</div>')
        tl.append(f'tl.fromTo("#{sid}-title",{{opacity:0,y:-12}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},{start + 0.2});')

    world.append('</div>')
    return frag + world, tl


BLOCKS = {"stat": stat_lockup, "statement": highlight_statement, "geo": geo_map, "raw": raw_scene,
          "timeline": timeline, "newshead": newshead, "collage": collage,
          "diagram": diagram, "comparison": comparison, "gallery": gallery, "carousel": carousel}

def compose_frame(frame_id, dur, scenes):
    body, tl = [], []
    for sc in scenes:
        sc = {**sc, "id": _safe_sid(sc["id"])}   # digit-first ids break #selectors
        f, t = BLOCKS[sc["type"]](sc["id"], sc)
        body += f; tl += t
    # geo + diagram scenes need d3 loaded before the timeline script (which contains their setup
    # IIFE). Loaded next to GSAP — the assembler guarantees script order. geo also needs topojson +
    # the atlas; diagram needs d3 only (d3.hierarchy/tree is in the same bundle).
    geo = [sc for sc in scenes if sc["type"] == "geo"]
    diag = [sc for sc in scenes if sc["type"] == "diagram"]
    libs = ""
    if geo or diag:
        libs = '  <script src="vendor/d3.min.js"></script>\n'
    if geo:
        kinds = set(sc["data"].get("kind", "us") for sc in geo)
        libs += '  <script src="vendor/topojson-client.min.js"></script>\n'
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
