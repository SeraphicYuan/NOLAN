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
  font-family:var(--font-display-en);background:transparent;}
.gnd{position:absolute;inset:0;background-size:cover;background-position:center;transform-origin:50% 50%;will-change:transform;}
.paper-gnd{position:absolute;inset:0;}
.scrim{position:absolute;inset:0;pointer-events:none;}
.kick{position:absolute;top:6.4cqw;left:calc(5.5cqw*var(--density,1));font-family:var(--eyebrow-font,var(--font-body));
  font-weight:var(--eyebrow-weight,600);font-size:calc(var(--eyebrow-size,0.9cqw)*var(--type-scale,1));
  letter-spacing:var(--eyebrow-tracking,0.14em);text-transform:var(--eyebrow-transform,uppercase);opacity:0;}
/* accent-stub rule — the short accent bar in the kicker->headline beat (near-universal in the reference
   decks). Universal + theme-painted (var(--accent)); a theme opts out with --stub-w:0. */
.kick::after{content:"";display:block;width:var(--stub-w,2.6cqw);height:var(--stub-h,0.34cqh);
  background:var(--accent);margin-top:0.95cqh;border-radius:var(--stub-r,1px);}
.stmt{position:absolute;left:calc(5.5cqw*var(--density,1));bottom:16cqh;max-width:80cqw;font-weight:var(--display-weight,800);font-style:var(--display-style,normal);font-size:calc(4.6cqw*var(--type-scale,1));line-height:1.08;
  letter-spacing:-0.012em;}
.stmt .ln{display:block;opacity:0;}
.hlwrap{position:relative;display:inline-block;isolation:isolate;}
.hlblock{position:absolute;left:-0.08em;right:-0.08em;top:0.06em;bottom:0.08em;background:var(--accent);transform:scaleX(0);
  transform-origin:left center;z-index:-1;}
.capbar{position:absolute;left:5.5cqw;bottom:9cqh;background:var(--surface);color:var(--text);padding:0.5cqw 1.1cqw;
  font-family:var(--caption-font,var(--font-body));font-weight:var(--caption-weight,600);
  font-size:calc(var(--caption-size,0.82cqw)*var(--type-scale,1));letter-spacing:var(--caption-tracking,0.1em);
  text-transform:var(--caption-transform,uppercase);opacity:0;}
.slrow{position:absolute;left:5.5cqw;top:34cqh;display:flex;gap:4cqw;align-items:flex-start;}
.slitem{display:flex;flex-direction:column;min-width:18cqw;}
.slnumwrap{position:relative;display:inline-block;}
.slnum{font-family:var(--hero-num-font,var(--font-display-en));font-style:var(--hero-num-style,normal);
  font-weight:var(--hero-num-weight,900);letter-spacing:var(--hero-num-track,-0.03em);line-height:1;
  font-variant-numeric:tabular-nums;font-size:calc(6cqw*var(--type-scale,1));white-space:nowrap;opacity:0;}
.slpre{font-size:0.7em;}.slsuf{font-size:0.62em;}
.slul{position:absolute;left:0;right:0;bottom:-0.16em;height:0.14em;background:var(--accent);transform:scaleX(0);transform-origin:left center;}
.sllabel{margin-top:1.1cqw;font-family:var(--stat-label-font,var(--font-body));font-weight:var(--stat-label-weight,500);
  font-size:calc(var(--stat-label-size,0.85cqw)*var(--type-scale,1));letter-spacing:var(--stat-label-tracking,0.12em);
  text-transform:var(--stat-label-transform,uppercase);max-width:22cqw;line-height:1.45;opacity:0;}
.paper .slnum,.paper .sllead{color:var(--text);}.paper .kick{color:var(--text-2);}.paper .sllabel{color:var(--text-mute);}
.footage .slnum{color:#F6F7F6;text-shadow:0 2px 12px rgba(0,0,0,0.55),0 1px 3px rgba(0,0,0,0.5);}.footage .kick{color:#F6F7F6;text-shadow:0 1px 8px rgba(0,0,0,0.5);}.footage .sllabel{color:#E9EAE9;text-shadow:0 1px 6px rgba(0,0,0,0.5);}
.stmt.paper-t{color:var(--text);}
.stmt.footage-t{color:#F6F7F6;text-shadow:0 2px 14px rgba(0,0,0,0.55),0 1px 3px rgba(0,0,0,0.5);}
/* operative on a DARK footage ground: a PERSISTENT accent backing (dark ink on it), so the phrase is
   legible BEFORE the .hlblock sweep fires — the sweep is anchored to when the word is SPOKEN, so a
   late-spoken operative was dark-on-dark and invisible for most of the scene (homer F5/s3 flash). */
.stmt.footage-t .hlwrap{color:var(--accent-ink);text-shadow:none;background:var(--accent);
  border-radius:0.05em;padding:0 0.08em;-webkit-box-decoration-break:clone;box-decoration-break:clone;}
/* bullet_list: a titled list of key points, each led by the THEME's bullet marker (--bullet-marker:
   square / em-dash / chevron / dot per theme — Layer-4 component). Marker is a ::before content var. */
.bl-title{position:absolute;top:14cqh;left:calc(5.5cqw*var(--density,1));right:calc(5.5cqw*var(--density,1));
  font-family:var(--font-display-en);font-style:var(--display-style,normal);font-weight:var(--display-weight,800);
  font-size:calc(3.6cqw*var(--type-scale,1));line-height:1.1;color:var(--text);opacity:0;}
.bl-title .hl{background:var(--accent);color:var(--accent-ink);padding:0 0.12em;-webkit-box-decoration-break:clone;box-decoration-break:clone;}
.bl-wrap{position:absolute;top:34cqh;left:calc(5.5cqw*var(--density,1));right:calc(8cqw*var(--density,1));
  display:flex;flex-direction:column;gap:calc(2.4cqh*var(--density,1));}
.bl-item{display:flex;align-items:baseline;gap:1.4cqw;opacity:0;}
.bl-mark{flex:none;color:var(--accent);font-weight:800;font-size:1.7cqw;line-height:1;font-family:var(--font-display-en);}
.bl-mark::before{content:var(--bullet-marker,"\\2022");}
.bl-num{flex:none;font-family:var(--hero-num-font,var(--font-display-en));font-style:var(--hero-num-style,normal);
  font-weight:var(--hero-num-weight,800);font-variant-numeric:tabular-nums;font-size:1.55cqw;line-height:1.15;
  letter-spacing:var(--hero-num-track,-0.01em);color:var(--accent);min-width:2.8cqw;}
.bl-text{font-family:var(--font-display-en);font-style:var(--display-style,normal);font-weight:var(--display-weight,600);
  font-size:calc(2.1cqw*var(--type-scale,1));line-height:1.25;color:var(--text);}
.bl-sub{display:block;font-family:var(--font-body);font-weight:400;font-size:1.02cqw;line-height:1.4;color:var(--text-2);margin-top:0.4cqh;}
.footage .bl-title,.footage .bl-text{color:#F6F7F6;text-shadow:0 2px 12px rgba(0,0,0,0.55);}
.footage .bl-sub{color:#E4E5E4;}
/* pull_quote: an oversized decorative quote-mark glyph + the quote (display type) + attribution — the
   attributed pull-quote `statement` doesn't cover. Universal + theme-painted (accent glyph, display face). */
.pq-wrap{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;
  padding:0 calc(9cqw*var(--density,1));color:var(--text);}
.pq-mark{font-family:var(--font-display-en);font-style:var(--display-style,normal);font-weight:900;
  font-size:20cqw;line-height:0.66;color:var(--accent);opacity:0;height:8.5cqh;overflow:visible;}
.pq-body{font-family:var(--font-display-en);font-style:var(--display-style,normal);
  font-weight:var(--display-weight,600);font-size:calc(4cqw*var(--type-scale,1));line-height:1.22;
  max-width:78cqw;opacity:0;}
.pq-body .hl{background:var(--accent);color:var(--accent-ink);padding:0 0.1em;
  -webkit-box-decoration-break:clone;box-decoration-break:clone;}
.pq-cite{margin-top:3.2cqh;font-family:var(--font-mono),ui-monospace;font-weight:600;font-size:1cqw;
  letter-spacing:.14em;text-transform:uppercase;color:var(--text-2);opacity:0;}
.footage .pq-body{color:#F6F7F6;text-shadow:0 2px 14px rgba(0,0,0,0.5);}
.footage .pq-cite{color:#E4E5E4;}
/* comparison_table: a real header-row x row-label x cell MATRIX with state chips + a highlighted "ours"
   column — the `comparison` block is a 2-panel split, not a data table. Universal + theme-painted. */
.ct-wrap{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;padding:0 calc(6cqw*var(--density,1));color:var(--text);}
.ct-grid{display:grid;align-items:stretch;opacity:0;}
.ct-hcell{padding:1.4cqh 0.8cqw;font-family:var(--eyebrow-font,var(--font-mono)),ui-monospace;font-weight:700;font-size:0.96cqw;letter-spacing:.08em;text-transform:uppercase;color:var(--text-2);border-bottom:var(--bw,2px) solid var(--accent);text-align:center;align-self:end;}
.ct-hcell.hi{color:var(--accent);}
.ct-corner{border-bottom:var(--bw,2px) solid var(--accent);}
.ct-rlabel{padding:1.7cqh 1.2cqw 1.7cqh 0;font-family:var(--font-display-en);font-style:var(--display-style,normal);font-weight:var(--display-weight,600);font-size:1.5cqw;line-height:1.15;border-bottom:1px solid var(--rule);display:flex;align-items:center;}
.ct-cell{padding:1.7cqh 0.8cqw;text-align:center;border-bottom:1px solid var(--rule);display:flex;align-items:center;justify-content:center;font-family:var(--font-body);font-size:1.2cqw;}
.ct-col-hi{background:var(--surface-3);}
.chip{display:inline-flex;align-items:center;justify-content:center;width:2.4cqw;height:2.4cqw;border-radius:50%;font-weight:800;font-size:1.15cqw;line-height:1;}
.chip.yes{background:var(--accent);color:var(--accent-ink);}
.chip.no{background:transparent;border:0.16cqw solid var(--rule);color:var(--text-mute);}
.chip.partial{background:var(--accent-soft);color:var(--accent);border:0.16cqw solid var(--accent);}
.footage .ct-rlabel,.footage .ct-cell{color:#F6F7F6;}
/* ledger_list: a dense hairline-separated row-list (ordinal + title + description + meta) — TOC / index /
   agenda / catalogue. Distinct from bullet_list (flat) + swiss-grid (2D cards). Universal + theme-painted. */
.lg-wrap{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;padding:0 calc(6cqw*var(--density,1));color:var(--text);}
.lg-row{display:grid;grid-template-columns:3.4cqw 1fr 2fr auto;gap:1.6cqw;align-items:baseline;padding:1.85cqh 0;border-bottom:1px solid var(--rule);opacity:0;}
.lg-row.first{border-top:var(--bw,2px) solid var(--accent);}
.lg-num{font-family:var(--hero-num-font,var(--font-display-en));font-style:var(--hero-num-style,normal);font-weight:var(--hero-num-weight,800);font-variant-numeric:tabular-nums;font-size:1.4cqw;color:var(--accent);}
.lg-title{font-family:var(--font-display-en);font-style:var(--display-style,normal);font-weight:var(--display-weight,600);font-size:1.7cqw;line-height:1.1;}
.lg-desc{font-family:var(--font-body);font-size:1.02cqw;line-height:1.35;color:var(--text-2);}
.lg-meta{font-family:var(--font-mono),ui-monospace;font-size:0.88cqw;letter-spacing:.1em;text-transform:uppercase;color:var(--text-mute);white-space:nowrap;}
.footage .lg-title{color:#F6F7F6;}
/* prop-cutout: object-as-evidence photo card (Vox), stacked ON TOP of the scene */
.prop{position:absolute;background:#fff;padding:0.5cqw;box-shadow:0 0.5cqw 1.8cqw rgba(0,0,0,0.38);opacity:0;transform-origin:center;}
.prop img{display:block;width:100%;height:auto;}
.prop-cap{margin-top:0.4cqw;font-family:"Lora",serif;font-style:italic;font-size:0.72cqw;color:var(--text);text-align:center;}
/* geo-map: d3 choropleth (US states / world countries), one region highlighted + annotated */
.geomap{will-change:transform;}
.geomap svg{width:100%;height:100%;display:block;}
.gstate{fill:var(--surface-3);stroke:var(--surface);stroke-width:1.0;}
.ghl{fill:var(--accent);stroke:var(--text);stroke-width:1.3;opacity:0;transform-box:fill-box;transform-origin:center;}
.geoleader{position:absolute;inset:0;pointer-events:none;}
.geoleader path{fill:none;stroke:var(--text);stroke-width:2;}
.geopin{position:absolute;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;background:var(--text);opacity:0;}
.geopin::after{content:"";position:absolute;inset:-9px;border:2px solid var(--text);border-radius:50%;opacity:0.4;}
.geolabel{position:absolute;left:8cqw;top:20cqh;max-width:32cqw;}
.glab-k{font-family:var(--font-body);font-weight:600;font-size:0.9cqw;letter-spacing:0.14em;text-transform:uppercase;color:var(--text-2);opacity:0;}
.glab-t{font-weight:900;font-size:5.4cqw;line-height:1;letter-spacing:-0.02em;color:var(--text);margin:0.6cqw 0;opacity:0;}
.glab-t .gmark{background:var(--accent);box-decoration-break:clone;padding:0 0.1em;}
.glab-s{font-family:"Lora",serif;font-style:italic;font-size:1.3cqw;line-height:1.4;color:var(--text-2);max-width:28cqw;opacity:0;}
/* timeline: Vox stylized horizontal timeline — drawing spine + camera pan + alternating circular callouts */
.tlbg{position:absolute;inset:0;background:radial-gradient(120% 120% at 50% 42%,#101210,#070807);}
.tlworld{position:absolute;top:0;left:0;height:100%;will-change:transform;}
.tlspine{position:absolute;height:8px;background:var(--accent);border-radius:4px;transform-origin:left center;transform:scaleX(0);box-shadow:0 0 22px var(--accent-glow);}
.tlnode{position:absolute;width:28px;height:28px;margin:-14px 0 0 -14px;border-radius:50%;background:#0a0b0a;border:5px solid var(--accent);transform:scale(0);z-index:3;}
.tlnode::after{content:"";position:absolute;inset:5px;border-radius:50%;background:var(--accent);}
.tlv{position:absolute;width:2px;background:#EDEFEC;transform:scaleY(0);}
.tlh{position:absolute;height:2px;background:#EDEFEC;transform-origin:left center;transform:scaleX(0);}
.tlcirc{position:absolute;border-radius:50%;overflow:hidden;background:#181a18;transform:scale(0);will-change:transform;box-shadow:0 12px 40px rgba(0,0,0,0.5);}
.tlcirc img{width:100%;height:100%;object-fit:cover;filter:grayscale(1) contrast(1.06) brightness(1.08);display:block;}
.tlph{position:absolute;inset:0;background:linear-gradient(135deg,#2b2d2b,#141513);}
.tlph::after{content:"";position:absolute;inset:22% 22%;border:3px solid rgba(237,239,236,0.14);border-radius:50%;}
.tlring{position:absolute;overflow:visible;pointer-events:none;}
.tlring circle{fill:none;stroke:#EDEFEC;stroke-width:2.5;}
.tlyear{position:absolute;font-weight:900;font-size:2.4cqw;letter-spacing:-0.01em;color:#EDEFEC;opacity:0;white-space:nowrap;font-variant-numeric:tabular-nums;}
.tllbl{position:absolute;font-family:var(--font-body);font-weight:600;font-size:0.82cqw;letter-spacing:0.1em;text-transform:uppercase;color:#9a9c99;opacity:0;white-space:nowrap;}
.tltitle{position:absolute;top:7cqh;left:5.5cqw;font-weight:900;font-size:2.6cqw;letter-spacing:-0.01em;color:#F6F7F6;opacity:0;}
.tltitle .hl{background:var(--accent);color:var(--accent-ink);padding:0 0.12em;box-decoration-break:clone;}
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
.nhhl{position:absolute;left:-0.05em;right:-0.05em;top:0.12em;bottom:0.16em;background:var(--accent);transform:scaleX(0);transform-origin:left center;z-index:-1;}
.nhsub{position:absolute;font-family:"Lora",serif;font-weight:400;color:#38362d;font-size:23px;line-height:1.5;opacity:0;}
.nhsub .subhl{background:var(--accent);-webkit-box-decoration-break:clone;box-decoration-break:clone;padding:0 2px;}
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
/* dark-register newshead (⑥): an aged DARK-newsprint card so it doesn't punch a bright hole in a dark
   theme; light ink; the highlighted phrase keeps a PERSISTENT accent backing with dark ink (same
   fix as the footage operative — the swept bar alone left it dark-on-dark before the sweep). */
.nh-dark .nhcard{background:#211f1b;}
.nh-dark .nhcard .tex{background-image:radial-gradient(circle,rgba(240,238,230,0.06) 1.1px,transparent 1.4px);}
.nh-dark .nhcard .vig{box-shadow:inset 0 0 150px rgba(0,0,0,0.42);}
.nh-dark .nhhead{color:#EDEBE4;}.nh-dark .nhsub{color:#b9b6ab;}.nh-dark .nhcap{color:#8f8c83;}
.nh-dark .nhhl-wrap{background:var(--accent);border-radius:0.05em;}
.nh-dark .nhhl-wrap .w{color:var(--accent-ink);}
.nh-dark .nhsub .subhl{color:var(--accent-ink);}      /* subhead highlight: dark ink on the accent too */
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
  border:2px solid #2B2D2C;border-radius:var(--r-card,12px);padding:0.85cqw 1.2cqw;text-align:center;
  box-shadow:0 0.4cqw 1.1cqw rgba(0,0,0,0.13);}
.dgnode.pill{border-radius:999px;}
.dgnode .lab{font-weight:800;font-size:1.15cqw;line-height:1.14;letter-spacing:-0.01em;color:#2B2D2C;}
.dgnode .sub{font-family:"Inter",sans-serif;font-weight:500;font-size:0.78cqw;line-height:1.3;color:#6b6d6a;margin-top:0.28cqw;}
.dgnode.hl{background:var(--accent);border-color:var(--accent-ink);}
.dgnode.hl .sub{color:#4C4E4D;}
.dgnode.root{background:#2B2D2C;border-color:#2B2D2C;}
.dgnode.root .lab{color:#F6F7F6;}.dgnode.root .sub{color:#c9ccc9;}
/* dark register: the node-container clip carries .dg-dark; nodes are its descendants */
.dg-dark .dgnode{background:#191c1f;border-color:#EDEFEC;box-shadow:0 0.5cqw 1.5cqw rgba(0,0,0,0.5);}
.dg-dark .dgnode .lab{color:#F6F7F6;}.dg-dark .dgnode .sub{color:#9a9c99;}
.dg-dark .dgnode.hl{background:var(--accent);border-color:var(--accent);}
.dg-dark .dgnode.hl .lab{color:#0a0b0a;}.dg-dark .dgnode.hl .sub{color:#3a3a2a;}
.dg-dark .dgnode.root{background:#0a0b0a;border-color:#EDEFEC;}
/* a HIGHLIGHTED root: .root forces a dark bg but .hl .lab forces dark ink → the label went dark-on-dark
   (homer F6 'HOMER' center node vanished). Keep the dark node, signal the highlight with an accent BORDER,
   and restore light ink. */
.dg-dark .dgnode.root.hl{background:#0a0b0a;border-color:var(--accent);}
.dg-dark .dgnode.root.hl .lab{color:#F6F7F6;}.dg-dark .dgnode.root.hl .sub{color:#c9ccc9;}
.dgkick{position:absolute;top:6.2cqw;left:5.5cqw;font-family:"Inter",sans-serif;font-weight:600;font-size:0.9cqw;
  letter-spacing:0.14em;text-transform:uppercase;color:#4C4E4D;opacity:0;}
.dgkick.on-dark{color:#9a9c99;}
.dgtitle{position:absolute;top:8.0cqw;left:5.5cqw;max-width:82cqw;font-weight:900;font-size:2.6cqw;line-height:1.06;
  letter-spacing:-0.015em;color:#2B2D2C;opacity:0;}
.dgtitle.on-dark{color:#F6F7F6;}
.dgtitle .hl{background:var(--accent);color:var(--accent-ink);padding:0 0.1em;box-decoration-break:clone;}
/* comparison: split A-vs-B; each panel hosts a typed content (image/text/stat/video) + per-side effects */
.cmp-panel{position:absolute;overflow:hidden;background:#0d0f11;will-change:transform;}
.cmp-media{position:absolute;inset:0;background-size:cover;background-position:center;transform-origin:50% 50%;will-change:transform;}
.cmp-media video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block;}
.cmp-scrim{position:absolute;inset:0;pointer-events:none;background:linear-gradient(rgba(10,11,12,0) 42%,rgba(10,11,12,0.72));}
.cmp-vig{position:absolute;inset:0;pointer-events:none;}
.cmp-tint{position:absolute;inset:0;pointer-events:none;mix-blend-mode:multiply;}
.cmp-paper{position:absolute;inset:0;}
.cmp-label{position:absolute;left:1.6cqw;top:1.4cqw;background:var(--accent);color:var(--accent-ink);font-family:"Inter",sans-serif;
  font-weight:700;font-size:0.8cqw;letter-spacing:0.1em;text-transform:uppercase;padding:0.4cqw 0.9cqw;border-radius:6px;opacity:0;z-index:4;}
.cmp-txt{position:absolute;left:2.4cqw;right:2.4cqw;bottom:6.5cqh;z-index:3;}
.cmp-txt.mid{top:50%;bottom:auto;transform:translateY(-50%);}
/* bottom title over media = a localized lower-third scrim (bound to the panel) so the overlay reads on ANY footage */
.cmp-txt:not(.mid)::before{content:"";position:absolute;left:-2.4cqw;right:-2.4cqw;top:-1.8cqh;bottom:-6.5cqh;
  background:linear-gradient(transparent,rgba(8,9,10,0.88));z-index:-1;pointer-events:none;}
.cmp-txt .k{font-family:"Inter",sans-serif;font-weight:600;font-size:0.82cqw;letter-spacing:0.13em;text-transform:uppercase;opacity:0;margin-bottom:0.5cqw;}
.cmp-txt .t{font-weight:800;font-size:2.1cqw;line-height:1.1;letter-spacing:-0.012em;}
.cmp-txt .t .ln{display:block;opacity:0;}
.cmp-txt .t .mark{background:var(--accent);color:var(--accent-ink);padding:0 0.08em;box-decoration-break:clone;}
.cmp-txt.paper .k{color:var(--text-mute);}.cmp-txt.paper .t{color:var(--text);}
.cmp-txt.footage .k{color:#EDEFEC;text-shadow:0 1px 6px rgba(0,0,0,0.6);}.cmp-txt.footage .t{color:#F6F7F6;text-shadow:0 2px 12px rgba(0,0,0,0.6);}
.cmp-num{position:absolute;left:0;right:0;top:50%;transform:translateY(-50%);text-align:center;z-index:3;padding:0 2cqw;}
.cmp-num .v{font-weight:900;font-size:5.6cqw;line-height:1;letter-spacing:-0.03em;font-variant-numeric:tabular-nums;opacity:0;}
.cmp-num .l{font-family:"Inter",sans-serif;font-weight:500;font-size:0.9cqw;letter-spacing:0.12em;text-transform:uppercase;margin-top:0.8cqw;opacity:0;}
.cmp-num.paper .v{color:var(--text);}.cmp-num.paper .l{color:var(--text-mute);}
.cmp-num.footage .v{color:#F6F7F6;}.cmp-num.footage .l{color:#d6d9d6;}
.cmp-div{position:absolute;background:#0a0b0c;z-index:5;}
.cmp-vs-w{position:absolute;transform:translate(-50%,-50%);z-index:6;}
.cmp-vs{width:5.2cqw;height:5.2cqw;border-radius:50%;background:var(--accent);color:var(--accent-ink);display:flex;align-items:center;
  justify-content:center;font-weight:900;font-size:1.5cqw;letter-spacing:-0.02em;transform-origin:center;transform:scale(0);box-shadow:0 0.4cqw 1.4cqw rgba(0,0,0,0.42);}
.cmp-htitle{position:absolute;left:0;right:0;top:0;height:150px;display:flex;flex-direction:column;justify-content:center;
  align-items:center;text-align:center;z-index:7;background:linear-gradient(#0a0b0c,rgba(10,11,12,0));}
.cmp-htitle .k{font-family:"Inter",sans-serif;font-weight:600;font-size:0.82cqw;letter-spacing:0.14em;text-transform:uppercase;color:#c9ccc9;opacity:0;margin-bottom:0.4cqw;}
.cmp-htitle .t{font-weight:900;font-size:1.9cqw;letter-spacing:-0.015em;color:#F6F7F6;opacity:0;}
.cmp-htitle .t .hl{background:var(--accent);color:var(--accent-ink);padding:0 0.1em;box-decoration-break:clone;}
.cmp-htitle.light{background:linear-gradient(var(--surface),rgba(0,0,0,0));}
.cmp-htitle.light .k{color:var(--text-mute);}.cmp-htitle.light .t{color:var(--text);}
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
.galcard{position:absolute;box-sizing:border-box;overflow:hidden;background:var(--surface);padding:0.42cqw;
  box-shadow:0 0.8cqw 2.2cqw rgba(0,0,0,0.44);transform-origin:center;will-change:transform,opacity,filter;filter:blur(0px);}
.galcard.noframe{padding:0;background:transparent;box-shadow:0 0.6cqw 1.7cqw rgba(0,0,0,0.4);}
.galcard img{width:100%;height:100%;object-fit:cover;display:block;}
.galcap{position:absolute;font-family:var(--font-body);font-weight:600;font-size:0.72cqw;letter-spacing:0.08em;
  text-transform:uppercase;color:var(--text-2);opacity:0;text-align:center;}
.galhcap{position:absolute;font-family:"Lora",serif;font-style:italic;font-size:1.15cqw;color:var(--text);opacity:0;
  text-align:center;text-shadow:0 2px 12px rgba(0,0,0,0.65);}
.galtitle{position:absolute;top:5.5cqh;left:0;width:100%;text-align:center;font-weight:900;font-size:2.4cqw;
  letter-spacing:-0.01em;color:var(--text);opacity:0;}
.galtitle .hl{background:var(--accent);color:var(--accent-ink);padding:0 0.12em;box-decoration-break:clone;}
/* carousel: a temporal image sequence — full-bleed slider (crossfade/kenburns) OR 3D coverflow */
.carworld{position:absolute;inset:0;}
.carslide{position:absolute;inset:0;opacity:0;overflow:hidden;will-change:opacity;}
.carslide.sized{inset:auto;transform-origin:center;border-radius:var(--r-card,16px);background:var(--shell);box-shadow:0 30px 90px rgba(0,0,0,0.6);}
.carslide img{width:100%;height:100%;object-fit:cover;display:block;will-change:transform;}
.caredge{position:absolute;inset:0;pointer-events:none;z-index:5;}
.carstage{position:absolute;inset:0;perspective:1600px;}
.car3d{position:absolute;inset:0;transform-style:preserve-3d;}
.carcard{position:absolute;left:50%;top:50%;overflow:hidden;border-radius:var(--r-card,10px);background:var(--shell);
  box-shadow:0 30px 90px rgba(0,0,0,0.62);backface-visibility:hidden;will-change:transform,opacity;}
.carcard img{width:100%;height:100%;object-fit:cover;display:block;}
.carcap{position:absolute;left:0;width:100%;bottom:19cqh;text-align:center;font-family:"Lora",serif;z-index:7;
  font-style:italic;font-size:1.35cqw;color:var(--text);opacity:0;text-shadow:0 2px 14px rgba(0,0,0,0.7);}
.cartitle{position:absolute;top:5.5cqh;left:0;width:100%;text-align:center;font-weight:900;font-size:2.4cqw;
  letter-spacing:-0.01em;color:var(--text);opacity:0;z-index:8;text-shadow:0 2px 16px rgba(0,0,0,0.6),0 1px 3px rgba(0,0,0,0.5);}
.cartitle .hl{background:var(--accent);color:var(--accent-ink);padding:0 0.12em;box-decoration-break:clone;text-shadow:none;}
/* carousel cards layout: a horizontal track of framed cards that scrolls (style:slider, layout:cards) */
.cartrack{position:absolute;left:0;will-change:transform;}
.carcarditem{position:absolute;overflow:hidden;border-radius:var(--r-card,14px);background:#000;transform-origin:center;
  box-shadow:0 24px 70px rgba(0,0,0,0.55);will-change:transform,opacity;}
.carcarditem img{width:100%;height:100%;object-fit:cover;display:block;}
/* linedraw: a self-drawing line-art SVG. draw mode forces a uniform stroke + no fill and animates
   each stroke's dashoffset length->0 (seek-safe); keep mode respects the SVG's own styling. */
.ld-bg{position:absolute;inset:0;}
.ld-wrap{position:absolute;inset:0;padding:7cqh 7cqw;box-sizing:border-box;}
.ld-wrap svg{width:100%;height:100%;display:block;overflow:visible;}
.ld-draw path,.ld-draw line,.ld-draw polyline,.ld-draw polygon,.ld-draw circle,.ld-draw ellipse,.ld-draw rect{
  fill:none !important;stroke:var(--ld-stroke,#2B2D2C) !important;
  stroke-linecap:round;stroke-linejoin:round;}
/* document: a page/sheet (doc / article / letter) as subject — reveal/stack/artifact + highlighter/underline/callout/label/caption annotations */
.doc-bg{position:absolute;inset:0;}
.doc-vig{position:absolute;inset:0;pointer-events:none;}
.doc-world{position:absolute;inset:0;transform-origin:50% 46%;will-change:transform;}
.doc-sheet{position:absolute;background:#fff;background-size:cover;background-position:top center;overflow:hidden;opacity:0;
  box-shadow:0 1.4cqw 3.4cqw rgba(0,0,0,0.42);will-change:transform,opacity;}
.doc-sheet.contain{background-size:contain;background-repeat:no-repeat;background-position:center;}
.doc-sheet.aged{filter:sepia(0.34) contrast(1.02) brightness(1.02);}
.doc-grain{position:absolute;inset:0;pointer-events:none;background-image:radial-gradient(circle,rgba(20,18,12,0.05) 1px,transparent 1.4px);background-size:16px 16px;}
.doc-hl{position:absolute;background:#FFF23B;mix-blend-mode:multiply;transform:scaleX(0);transform-origin:left center;border-radius:2px;pointer-events:none;}
.doc-underline{position:absolute;height:0.42cqh;background:#C8232C;transform:scaleX(0);transform-origin:left center;border-radius:2px;pointer-events:none;}
.doc-label{position:absolute;transform:translate(-50%,-50%) scale(0);background:#C8232C;color:#F7F3EA;font-family:"Inter",sans-serif;
  font-weight:700;font-size:1.0cqw;letter-spacing:0.02em;padding:0.3cqw 0.72cqw;border-radius:6px;white-space:nowrap;
  box-shadow:0 0.3cqw 0.9cqw rgba(0,0,0,0.35);transform-origin:center;}
.doc-callout{position:absolute;background:#fff;box-shadow:0 1cqw 2.6cqw rgba(0,0,0,0.3);border-radius:var(--r-card,12px);padding:1.1cqw 1.4cqw;
  opacity:0;max-width:27cqw;border-left:0.4cqw solid var(--accent);}
.doc-callout .ck{font-family:"Inter",sans-serif;font-weight:600;font-size:0.78cqw;letter-spacing:0.1em;text-transform:uppercase;color:#8a8a80;margin-bottom:0.4cqw;}
.doc-callout .ct{font-weight:800;font-size:1.35cqw;line-height:1.22;letter-spacing:-0.01em;color:#1c1c19;}
.doc-callout .ct .ln{display:block;}
.doc-caption{position:absolute;left:6cqw;right:6cqw;bottom:6cqh;text-align:center;font-family:"Lora",serif;font-style:italic;
  font-size:1.7cqw;line-height:1.3;color:#F3ECDD;opacity:0;text-shadow:0 2px 14px rgba(0,0,0,0.55);}
.doc-caption .uw{position:relative;white-space:nowrap;}
.doc-caption .ul{position:absolute;left:0;right:0;bottom:-0.05em;height:2px;background:#C8232C;transform:scaleX(0);transform-origin:left center;}
.doc-caption::before{content:"";position:absolute;left:-6cqw;right:-6cqw;top:-1.4cqh;bottom:-2.4cqh;z-index:-1;pointer-events:none;background:radial-gradient(62% 150% at 50% 55%,rgba(8,7,5,0.62),transparent 72%);}
.doc-kick{position:absolute;top:5.4cqw;left:5.5cqw;font-family:"Inter",sans-serif;font-weight:600;font-size:0.9cqw;letter-spacing:0.14em;text-transform:uppercase;color:#F1EFE9;opacity:0;text-shadow:0 2px 10px rgba(0,0,0,0.5);}
.doc-title{position:absolute;top:6.9cqw;left:5.5cqw;max-width:72cqw;font-weight:900;font-size:2.4cqw;line-height:1.05;letter-spacing:-0.015em;color:#fff;opacity:0;text-shadow:0 2px 16px rgba(0,0,0,0.5);}
.doc-title .hl{background:var(--accent);color:var(--accent-ink);padding:0 0.1em;box-decoration-break:clone;text-shadow:none;}
/* diagram space:"3d" — the 2D network laid on a tilted, receding grid plane; cards stand up (billboard); camera glides. CSS-3D + GSAP, seek-safe. */
.dg3-bg{position:absolute;inset:0;background:radial-gradient(130% 120% at 50% 30%,#141922,#05070c);}
.dg3-view{position:absolute;inset:0;overflow:hidden;perspective:1700px;perspective-origin:50% 46%;}
.dg3-stage{position:absolute;inset:0;transform-style:preserve-3d;transform-origin:50% 58%;transform:rotateX(56deg);}
.dg3-plane{position:absolute;transform-style:preserve-3d;transform-origin:50% 50%;will-change:transform;
  background-image:linear-gradient(rgba(122,196,255,0.12) 2px,transparent 2px),linear-gradient(90deg,rgba(122,196,255,0.12) 2px,transparent 2px);background-size:120px 120px;}
.dg3-links{position:absolute;left:0;top:0;overflow:visible;pointer-events:none;}
.dg3-link{fill:none;stroke:#FFC63A;stroke-width:4;stroke-linecap:round;stroke-dasharray:1;stroke-dashoffset:1;opacity:0;filter:drop-shadow(0 0 7px rgba(255,190,40,0.55));}
.dg3-card{position:absolute;transform-origin:50% 100%;transform-style:preserve-3d;will-change:transform;}
.dg3-card .cd{position:absolute;left:0;top:0;transform:translate(-50%,-100%);min-width:150px;max-width:280px;background:#141a22;border:2px solid #33404f;border-radius:13px;padding:13px 18px;
  box-shadow:0 22px 50px rgba(0,0,0,0.7);text-align:center;opacity:0;white-space:nowrap;}
.dg3-card.root .cd{background:#0a0d12;border-color:#5b6b7e;}
.dg3-card.hl .cd{background:var(--accent);border-color:var(--accent);box-shadow:0 20px 46px rgba(0,0,0,0.6),0 0 40px var(--accent-glow);}
.dg3-card .cd .lab{font-weight:800;font-size:20px;line-height:1.1;letter-spacing:-0.01em;color:#EAF0F6;}
.dg3-card.hl .cd .lab{color:#0a0b0a;}
.dg3-card .cd .sub{font-family:"Inter",sans-serif;font-weight:600;font-size:12px;letter-spacing:0.02em;color:#8fa2b6;margin-top:4px;}
.dg3-card.hl .cd .sub{color:#4a4a2a;}
.dg3-kick{position:absolute;top:5.0cqw;left:5.5cqw;font-family:"Inter",sans-serif;font-weight:600;font-size:0.9cqw;letter-spacing:0.14em;text-transform:uppercase;color:#8fa2b6;opacity:0;}
.dg3-title{position:absolute;top:6.4cqw;left:5.5cqw;max-width:72cqw;font-weight:900;font-size:2.5cqw;line-height:1.05;letter-spacing:-0.015em;color:#F3F7FB;opacity:0;text-shadow:0 2px 18px rgba(0,0,0,0.6);}
.dg3-title .hl{background:var(--accent);color:var(--accent-ink);padding:0 0.1em;box-decoration-break:clone;text-shadow:none;}
/* lower_third: name + role identifier for footage — theme-driven, one block × a `style` param */
.ltwrap{position:absolute;}
.lt-name{font-weight:900;font-size:2.6cqw;letter-spacing:-0.01em;line-height:1.02;color:var(--text);}
.lt-role{font-family:var(--font-body);font-weight:600;font-size:0.95cqw;letter-spacing:0.08em;text-transform:uppercase;color:var(--text-2);margin-top:0.55cqw;opacity:0;}
.lt-kicker{font-family:var(--font-body);font-weight:700;font-size:0.78cqw;letter-spacing:0.16em;text-transform:uppercase;color:var(--accent);margin-bottom:0.45cqw;}
.lt-bar{display:inline-flex;align-items:stretch;gap:1cqw;background:var(--surface);border-radius:var(--r-card,10px);padding:1cqw 1.5cqw;box-shadow:var(--card-shadow,0 0.8cqw 2.6cqw rgba(0,0,0,0.32));}
.lt-tab{width:0.45cqw;background:var(--accent);border-radius:3px;}
.lt-txt{display:flex;flex-direction:column;justify-content:center;}
.lt-card{display:inline-block;background:var(--surface);border-radius:var(--r-card,12px);padding:1.2cqw 1.8cqw;box-shadow:var(--card-shadow,0 0.8cqw 2.6cqw rgba(0,0,0,0.34));}
.lt-cardless{display:inline-block;}
.lt-cardless .lt-name{text-shadow:0 2px 14px rgba(0,0,0,0.6);}
.lt-cardless .lt-role{text-shadow:0 2px 10px rgba(0,0,0,0.6);}
.lt-underline-rule{display:block;width:100%;height:0.3cqw;background:var(--accent);transform-origin:left center;transform:scaleX(0);margin-top:0.7cqw;border-radius:2px;}
.lt-block{display:inline-block;background:var(--accent);padding:1cqw 1.6cqw;transform-origin:left center;}
.lt-block .lt-name{color:var(--accent-ink);text-transform:uppercase;}
.lt-block .lt-role{color:var(--accent-ink);opacity:0.85;}
.lt-block .lt-kicker{color:var(--accent-ink);opacity:0.9;}
/* chart: animated bar/line — GSAP+SVG/CSS, theme-driven (accent bars/line, text/rule tokens) */
.ch-kicker{position:absolute;top:6cqh;left:11cqw;font-family:var(--font-body);font-weight:700;font-size:0.85cqw;letter-spacing:0.14em;text-transform:uppercase;color:var(--accent);opacity:0;}
.ch-title{position:absolute;top:9cqh;left:11cqw;max-width:78cqw;font-weight:900;font-size:2.6cqw;letter-spacing:-0.01em;color:var(--text);opacity:0;}
.ch-title .hl{background:var(--accent);color:var(--accent-ink);padding:0 0.1em;box-decoration-break:clone;}
.ch-base{position:absolute;height:2px;background:var(--rule);}
.ch-grid{position:absolute;height:1px;background:var(--rule);opacity:0.45;}
.ch-bar{position:absolute;transform-origin:bottom center;border-radius:var(--r-card,5px) var(--r-card,5px) 0 0;will-change:transform;}
.ch-val{position:absolute;text-align:center;font-weight:800;font-size:1.15cqw;color:var(--text);opacity:0;font-variant-numeric:tabular-nums;white-space:nowrap;}
.ch-xlab{position:absolute;text-align:center;font-family:var(--font-body);font-weight:600;font-size:0.82cqw;letter-spacing:0.04em;color:var(--text-2);white-space:nowrap;}
.ch-svg{position:absolute;inset:0;width:100%;height:100%;}
.ch-svg path{stroke:var(--accent);stroke-width:5;stroke-linecap:round;stroke-linejoin:round;}
.ch-dot{position:absolute;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;background:var(--accent);border:3px solid var(--shell);}
/* code: syntax-highlighted editor window. Syntax colours = a fixed code `theme` (inline); backdrop/title = NOLAN tokens */
.cd-kicker{position:absolute;top:6cqh;left:16cqw;font-family:var(--font-body);font-weight:700;font-size:0.85cqw;letter-spacing:0.14em;text-transform:uppercase;color:var(--accent);opacity:0;}
.cd-title{position:absolute;top:9.5cqh;left:16cqw;max-width:68cqw;font-weight:900;font-size:2.3cqw;letter-spacing:-0.01em;color:var(--text);opacity:0;}
.cd-title .hl{background:var(--accent);color:var(--accent-ink);padding:0 0.1em;box-decoration-break:clone;}
.cd-win{position:absolute;left:16cqw;width:68cqw;border-radius:var(--r-card,14px);overflow:hidden;box-shadow:0 2cqw 6cqw rgba(0,0,0,0.5);will-change:transform,opacity;}
.cd-bar{display:flex;align-items:center;gap:0.55cqw;padding:0.85cqw 1.2cqw;border-bottom:1px solid;}
.cd-dot{width:0.7cqw;height:0.7cqw;border-radius:50%;display:inline-block;flex:0 0 auto;}
.cd-fname{margin-left:0.7cqw;font-family:var(--font-mono),monospace;font-size:0.82cqw;}
.cd-code{padding:1.3cqw 1.7cqw;font-family:var(--font-mono),"JetBrains Mono",monospace;font-size:1.05cqw;line-height:1.7;}
.cd-line{display:flex;gap:1cqw;border-radius:4px;padding:0 0.4cqw;margin:0 -0.4cqw;will-change:transform,opacity;}
.cd-gut{opacity:0.65;user-select:none;min-width:1.5cqw;text-align:right;flex:0 0 auto;}
.cd-lt{white-space:pre;}
.cd-hl{background:rgba(255,255,255,0.08);}
/* social_card — BRAND-FIXED palettes (identity, not NOLAN tokens). Only the scene backdrop is themed. */
.soc-wrap{position:absolute;}
.soc-card{border-radius:16px;overflow:hidden;box-shadow:0 2cqw 6cqw rgba(0,0,0,0.42);will-change:transform,opacity;font-family:-apple-system,"Segoe UI",Roboto,var(--font-body),sans-serif;}
.soc-x{background:#fff;color:#0f1419;width:36cqw;padding:1.9cqw 2.1cqw;}
.soc-head{display:flex;align-items:center;gap:0.9cqw;}
.soc-av{width:3.1cqw;height:3.1cqw;border-radius:50%;background:linear-gradient(135deg,#1d9bf0,#8ecdf5);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1.15cqw;flex:0 0 auto;overflow:hidden;}
.soc-av img{width:100%;height:100%;object-fit:cover;}
.soc-name{font-weight:800;font-size:1.25cqw;display:flex;align-items:center;gap:0.4cqw;}
.soc-vf{width:1.25cqw;height:1.25cqw;border-radius:50%;background:#1d9bf0;color:#fff;font-size:0.8cqw;line-height:1;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;}
.soc-handle{color:#536471;font-size:1.05cqw;margin-top:0.1cqw;}
.soc-logo{margin-left:auto;font-weight:900;font-size:1.7cqw;color:#0f1419;}
.soc-text{margin-top:1.1cqw;font-size:1.5cqw;line-height:1.42;color:#0f1419;}
.soc-metrics{margin-top:1.3cqw;display:flex;gap:2.2cqw;color:#536471;font-size:1.05cqw;}
.soc-metrics b{color:#0f1419;font-weight:800;}
.soc-heart b{color:#f91880;}
.soc-reddit{background:#fff;color:#1a1a1b;width:36cqw;display:flex;}
.soc-votes{background:#f8f9fa;padding:1.5cqw 1.1cqw;display:flex;flex-direction:column;align-items:center;gap:0.55cqw;flex:0 0 auto;}
.soc-up{width:0;height:0;border-left:0.75cqw solid transparent;border-right:0.75cqw solid transparent;border-bottom:0.95cqw solid #ff4500;}
.soc-dn{width:0;height:0;border-left:0.75cqw solid transparent;border-right:0.75cqw solid transparent;border-top:0.95cqw solid #b8bbbf;}
.soc-votes .n{font-weight:800;font-size:1.05cqw;color:#ff4500;}
.soc-rbody{padding:1.5cqw 1.7cqw;}
.soc-sub{color:#ff4500;font-weight:800;font-size:1cqw;}
.soc-rtitle{margin-top:0.55cqw;font-weight:700;font-size:1.55cqw;line-height:1.32;color:#1a1a1b;}
.soc-rmeta{margin-top:1.1cqw;color:#787c7e;font-size:0.95cqw;font-weight:600;}
.soc-spotify{background:#121212;color:#fff;width:34cqw;padding:1.7cqw;display:flex;align-items:center;gap:1.5cqw;}
.soc-art{width:6.4cqw;height:6.4cqw;border-radius:8px;background:linear-gradient(135deg,#1db954,#0a5c2a);color:#0a2e17;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:2cqw;flex:0 0 auto;overflow:hidden;}
.soc-art img{width:100%;height:100%;object-fit:cover;}
.soc-sbody{flex:1 1 auto;min-width:0;}
.soc-track{font-weight:800;font-size:1.45cqw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.soc-artist{color:#b3b3b3;font-size:1.1cqw;margin-top:0.3cqw;}
.soc-prog{margin-top:1cqw;height:0.4cqw;background:#4d4d4d;border-radius:3px;position:relative;overflow:hidden;}
.soc-prog-fill{position:absolute;left:0;top:0;bottom:0;background:#1db954;border-radius:3px;transform-origin:left center;will-change:transform;}
.soc-splay{margin-left:1cqw;color:#1db954;font-size:2.2cqw;line-height:1;flex:0 0 auto;}
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


def _is_video_bg(bg):
    """True when a scene `backdrop` value is a VIDEO path. A video backdrop can't be a CSS background-image
    (it won't play) — the block emits NOTHING for it (a transparent scene) and the video is root-injected
    behind the scene by incremental.frame_grounds (the same proven path as a media_ground video)."""
    return isinstance(bg, str) and bg.lower().endswith((".mp4", ".mov", ".webm"))

def _safe_sid(sid):
    """CSS-safe id prefix. Element ids/selectors can't start with a digit, but faceless frame
    ids are NN-title (e.g. 01-power) and scenes inherit them → '#01-power-s1-k' throws in
    querySelectorAll. Prepend a letter when digit-first and replace invalid chars."""
    s = re.sub(r"[^0-9A-Za-z_-]", "-", str(sid))
    if s and s[0].isdigit():
        s = "s" + s
    return s or "s"

# ground.grade — the GENERIC answer to visual-treatment notes ("cool it down / warm / darken / desaturate …"):
# a gated CSS `filter` applied to any image ground, block-agnostic. This dict IS the registry of valid values
# (the author gate should reject an unknown grade — see _lint / catalog). Give a note like "cool it down" a
# landing spot instead of a "no gated field" dead end.
GRADES = {
    "warm": "sepia(0.32) saturate(1.18) brightness(1.02)",
    "cool": "sepia(0.25) hue-rotate(155deg) saturate(1.15)",
    "darken": "brightness(0.68)",
    "brighten": "brightness(1.2)",
    "contrast": "contrast(1.28)",
    "desaturate": "saturate(0.42)",
    "mute": "saturate(0.72) brightness(0.95)",
    "noir": "grayscale(1) contrast(1.2)",
}

# effects umbrella (nolan.effects) SUPERSEDES this bare GRADES map: colour treatments compose into the
# ground's CSS filter and blend_overlay treatments (grain/scanlines/fire/rain) become stacked layers.
# Guarded so a bare `python compose.py` outside the venv still imports.
try:
    from nolan.effects.render import filter_chain as _fx_filter, overlay_layers as _fx_overlays
except Exception:  # pragma: no cover - nolan not importable in a bare compose context
    def _fx_filter(_t): return ""
    def _fx_overlays(*_a, **_k): return []


def media_ground(sid, ground, start, dur):
    """Reusable BLOCK: full-bleed ground. image -> dimmed image + scrim + Ken-Burns;
    paper -> flat mist/parchment; transparent -> scrim only (root video shows through).
    An optional `ground.grade` (see GRADES) applies a CSS filter — the gated visual-treatment lever."""
    frag, tl = [], []
    kind = ground.get("kind", "paper")
    # ground filter = legacy single `grade` + the colour treatments (effects umbrella), composed.
    _treat = ground.get("treatments")
    _gf = GRADES.get(ground.get("grade"))
    _filter = " ".join(x for x in (_gf, _fx_filter(_treat)) if x)
    _gsty = f"filter:{_filter};" if _filter else ""
    if kind == "image":
        scr = "linear-gradient(90deg,rgba(20,21,20,0.72),rgba(20,21,20,0.30) 55%,rgba(20,21,20,0.45))," \
              "linear-gradient(rgba(20,21,20,0) 45%,rgba(20,21,20,0.62))"
        frag.append(f'<div id="{sid}-gnd" class="clip gnd" data-start="{start}" data-duration="{dur}" '
                    f'data-track-index="0" data-layout-allow-overflow style="background-image:url(\'{esc(ground["src"])}\');{_gsty}"></div>')
        frag.append(f'<div class="clip scrim" data-start="{start}" data-duration="{dur}" data-track-index="1" '
                    f'style="background:{scr};"></div>')
        frag += _fx_overlays(_treat, sid, start, dur)   # blend_overlay treatments (grain/scanlines) over the image
        f0, f1 = ground.get("kb", [1.03, 1.08])
        tl.append(f'tl.fromTo("#{sid}-gnd",{{scale:{f0}}},{{scale:{f1},duration:{dur},ease:"none"}},{start});')
    elif kind in ("transparent", "video"):  # root video behind; scrim only.
        # kind=="video" ALSO carries a `src`: the composer leaves a transparent hole here and the
        # assemble step (collect_video_grounds -> inject_root_video.py) mounts the pool clip at the
        # index ROOT on a track BELOW the frame (archetype B) so it shows through. Same scrim either
        # way (darkens the footage so footage-t text stays legible).
        scr = "linear-gradient(90deg,rgba(20,21,20,0.66),rgba(20,21,20,0.18) 55%,rgba(20,21,20,0.42))," \
              "linear-gradient(rgba(20,21,20,0) 50%,rgba(20,21,20,0.6))"
        frag.append(f'<div class="clip scrim" data-start="{start}" data-duration="{dur}" data-track-index="1" '
                    f'style="background:{scr};"></div>')
    else:  # paper / parchment
        # a FULL-BLEED statement ground is the theme's CANVAS, not the raised panel: --shell is what
        # every other block's ground uses (2225/2322/1732/1835/2387), so --surface here made the
        # statement the lone odd-one-out — a theme whose identity IS its canvas colour (blue-professional:
        # cream --shell vs white --surface) lost it on this one block. But the inverted-card themes
        # (dark --shell + light --surface) tune --text to --surface, so there --shell would go dark-on-dark
        # → fall back to --surface for them. Parchment stays an explicit warm variant.
        canvas = "var(--shell)" if _SHELL_TEXTSAFE else "var(--surface)"
        col = "var(--surface-2)" if ground.get("parchment") else canvas
        frag.append(f'<div class="clip paper-gnd" data-start="{start}" data-duration="{dur}" data-track-index="1" '
                    f'style="background:{col};"></div>')
    return frag, tl

def _register(sid): return "paper" if False else ""

def _grounded(d):
    """True iff a scene has REAL footage (image/video) behind it — the only case the dark 'footage'
    register (light ink + scrim) is legible. Over a paper/transparent ground, text must use the PAPER
    register (var(--text) on var(--surface)), which is correct on BOTH light and dark themes. This is the
    rule nolan4 hand-applied per scene on the aeneid (light theme); deriving it stops a bare statement
    from rendering near-white ink on a cream surface."""
    return (d.get("ground") or {}).get("kind") in ("image", "video")

def stat_lockup(sid, sc):
    """Reusable BLOCK: 1-3 count-up numerals + labels + one underline sweep."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    reg = d.get("register") or ("footage" if _grounded(d) else "paper")   # dark ink only over real footage
    g, tl = media_ground(sid, d.get("ground", {"kind": "paper", "parchment": d.get("parchment")}), start, dur)
    frag = [f'<section class="scene clip {reg}" data-start="{start}" data-duration="{dur}" data-track-index="2">']
    frag.append(f'<div id="{sid}-k" class="kick">{esc(d.get("kicker",""))}</div>')
    frag.append(f'<div class="slrow" data-fit data-fit-w="89cqw" data-fit-origin="left top">')
    tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start+0.1});')
    reveal = d.get("reveal")
    lbase = "var(--text)" if reg == "paper" else "#F6F7F6"   # paper ink follows the theme (was cold #2B2D2C)
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

def reveal_text(el, text, style, start, cue, dur, operative=None, base="var(--text)"):
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
        cls, attr = "rv-grad", f' style="--rv-c1:{base};--rv-c2:var(--accent);"'
    elif style in _RV_PERSPECTIVE:
        attr = ' style="perspective:600px;"'
    if style == "typewriter":
        inner += f'<span class="rv-caret" id="{el}-cr">▌</span>'
    tl = list(_rv_entrance(el, style, reals, start, cue, dur))
    if opw:
        sweep = cue + _rv_dur(style, len(reals) or 1, dur) + 0.05
        tl.append(f'tl.fromTo("#{el}-hb",{{scaleX:0}},{{scaleX:1,duration:0.4,ease:"power2.out"}},{sweep:.2f});')
        tgt = f"#{el}-opw .rv-op" if split == "line" else f"#{el}-opw .rv-u"
        tl.append(f'tl.set("{tgt}",{{color:"var(--accent-ink)"}},{sweep+0.05:.2f});')
    return inner, cls, attr, tl

def highlight_statement(sid, sc):
    """Reusable BLOCK: a statement with ONE yellow-block sweep + optional caption-bar.
    data.reveal (default "rise") selects a text-entrance style from REVEALS (char/word/flip/
    typewriter/scramble/decode/gradient/glitch); the operative sweep still fires after the text lands."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    reg = d.get("register") or ("footage" if _grounded(d) else "paper")   # was hardcoded "footage" -> light ink on a light theme = invisible
    tcls = "paper-t" if reg == "paper" else "footage-t"
    # a type-only (paper) statement has NO media to darken — default to a clean paper ground, not the
    # transparent+dark-scrim (which smears a hardcoded rgba(20,21,20) gradient over a LIGHT theme). An
    # explicit ground:{kind:transparent} still scrims a root video (grounded/footage keeps that default).
    default_ground = {"kind": "transparent"} if reg == "footage" else {"kind": "paper"}
    g, tl = media_ground(sid, d.get("ground", default_ground), start, dur)
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
                tl.append(f'tl.set("#{sid}-op{li}",{{color:"var(--accent-ink)"}},{cue+0.05});')
            else:
                frag.append(f'<span class="ln" id="{lid}">{esc(line)}</span>')
            tl.append(f'tl.fromTo("#{lid}",{{opacity:0,yPercent:60}},{{opacity:1,yPercent:0,duration:0.6,ease:"power3.out"}},{start+0.4+li*0.35});')
    else:
        # ── reveal-vocabulary path: delegate each line to reveal_text (the shared entry point) ──
        base = "var(--text)" if reg == "paper" else "#F6F7F6"
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

def bullet_list(sid, sc):
    """Reusable BLOCK: a titled list of key points, each led by the theme's bullet marker and staggered
    in. The marker glyph is the theme's --bullet-marker (square / em-dash / chevron / dot — a real per-theme
    choice; Layer-4 `bullet-marker` component), so a brutalist list reads differently from an editorial one.
    data: {kicker?, title?, titleHi?, items:[str | {text, sub?}], register?, ground?}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    reg = d.get("register") or ("footage" if _grounded(d) else "paper")
    default_ground = {"kind": "transparent"} if reg == "footage" else {"kind": "paper"}
    g, tl = media_ground(sid, d.get("ground", default_ground), start, dur)
    frag = [f'<section class="scene clip {reg}" data-start="{start}" data-duration="{dur}" data-track-index="2">']
    if d.get("kicker"):
        frag.append(f'<div id="{sid}-k" class="kick">{esc(d["kicker"])}</div>')
        tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start+0.15});')
    if d.get("title"):
        t, op = d["title"], d.get("titleHi", "")
        html_t = (f'{esc(t.split(op,1)[0])}<span class="hl">{esc(op)}</span>{esc(t.split(op,1)[1])}'
                  if op and op in t else esc(t))
        frag.append(f'<div id="{sid}-t" class="bl-title">{html_t}</div>')
        tl.append(f'tl.fromTo("#{sid}-t",{{opacity:0,y:12}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},{start+0.3});')
    numbered = bool(d.get("numbered"))
    frag.append('<div class="bl-wrap">')
    for i, it in enumerate(d.get("items", [])):
        text = it if isinstance(it, str) else it.get("text", "")
        sub = "" if isinstance(it, str) else it.get("sub", "")
        iid = f"{sid}-i{i}"
        subhtml = f'<span class="bl-sub">{esc(sub)}</span>' if sub else ""
        mark = f'<span class="bl-num">{i+1:02d}</span>' if numbered else '<span class="bl-mark"></span>'
        frag.append(f'<div class="bl-item" id="{iid}">{mark}'
                    f'<span class="bl-text">{esc(text)}{subhtml}</span></div>')
        tl.append(f'tl.fromTo("#{iid}",{{opacity:0,x:-14}},{{opacity:1,x:0,duration:0.5,ease:"power2.out"}},{start+0.6+i*0.32});')
    frag.append('</div></section>')
    pf, pt = _props_of(sid, sc)
    return g + frag + pf, tl + pt

def pull_quote(sid, sc):
    """Reusable BLOCK: an attributed pull-quote — an oversized decorative quote-mark glyph, the quote in
    the theme's display type (optional `hi` substring highlighted), and a mono attribution. The reference
    decks' near-universal quote element that `statement` (a manifesto) doesn't cover. data: {quote, cite?,
    hi?, kicker?, register?, ground?}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    reg = d.get("register") or ("footage" if _grounded(d) else "paper")
    default_ground = {"kind": "transparent"} if reg == "footage" else {"kind": "paper"}
    g, tl = media_ground(sid, d.get("ground", default_ground), start, dur)
    frag = [f'<section class="scene clip {reg}" data-start="{start}" data-duration="{dur}" data-track-index="2">']
    if d.get("kicker"):
        frag.append(f'<div id="{sid}-k" class="kick">{esc(d["kicker"])}</div>')
        tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start+0.15});')
    q, hi = d.get("quote", ""), d.get("hi", "")
    qhtml = (f'{esc(q.split(hi,1)[0])}<span class="hl">{esc(hi)}</span>{esc(q.split(hi,1)[1])}'
             if hi and hi in q else esc(q))
    frag.append('<div class="pq-wrap">')
    frag.append(f'<div id="{sid}-qm" class="pq-mark">“</div>')
    frag.append(f'<div id="{sid}-q" class="pq-body">{qhtml}</div>')
    if d.get("cite"):
        frag.append(f'<div id="{sid}-c" class="pq-cite">{esc(d["cite"])}</div>')
    frag.append('</div></section>')
    tl.append(f'tl.fromTo("#{sid}-qm",{{opacity:0,scale:0.72,y:8}},{{opacity:1,scale:1,y:0,duration:0.6,ease:"power3.out"}},{start+0.3});')
    tl.append(f'tl.fromTo("#{sid}-q",{{opacity:0,y:16}},{{opacity:1,y:0,duration:0.7,ease:"power3.out"}},{start+0.5});')
    if d.get("cite"):
        tl.append(f'tl.fromTo("#{sid}-c",{{opacity:0,y:8}},{{opacity:1,y:0,duration:0.5}},{start+1.2});')
    pf, pt = _props_of(sid, sc)
    return g + frag + pf, tl + pt

_CHIP_GLYPH = {"yes": "✓", "no": "–", "partial": "◐"}

def _chip(v):
    s = str(v).strip().lower()
    if s in _CHIP_GLYPH:
        return f'<span class="chip {s}">{_CHIP_GLYPH[s]}</span>'
    return esc(str(v))

def comparison_table(sid, sc):
    """Reusable BLOCK: a real header-row x row-label x cell MATRIX with state chips (yes/partial/no) + an
    optional highlighted 'ours' column. The `comparison` block is a 2-panel split — this is the tabular
    matrix. data: {kicker?, title?, columns:[{label, highlight?}], rows:[{label, cells:[state|text]}]}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    reg = d.get("register") or ("footage" if _grounded(d) else "paper")
    default_ground = {"kind": "transparent"} if reg == "footage" else {"kind": "paper"}
    g, tl = media_ground(sid, d.get("ground", default_ground), start, dur)
    cols, rows = d.get("columns", []), d.get("rows", [])
    n = max(1, len(cols))
    frag = [f'<section class="scene clip {reg}" data-start="{start}" data-duration="{dur}" data-track-index="2">']
    if d.get("kicker"):
        frag.append(f'<div id="{sid}-k" class="kick">{esc(d["kicker"])}</div>')
        tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start+0.15});')
    frag.append(f'<div class="ct-wrap"><div id="{sid}-g" class="ct-grid" '
                f'style="grid-template-columns:1.6fr repeat({n},1fr)">')
    frag.append('<div class="ct-corner"></div>')
    for c in cols:
        hi = " hi" if c.get("highlight") else ""
        frag.append(f'<div class="ct-hcell{hi}">{esc(c.get("label", ""))}</div>')
    for row in rows:
        frag.append(f'<div class="ct-rlabel">{esc(row.get("label", ""))}</div>')
        for j, cell in enumerate(row.get("cells", [])):
            hi = " ct-col-hi" if j < len(cols) and cols[j].get("highlight") else ""
            frag.append(f'<div class="ct-cell{hi}">{_chip(cell)}</div>')
    frag.append('</div></div></section>')
    tl.append(f'tl.fromTo("#{sid}-g",{{opacity:0,y:16}},{{opacity:1,y:0,duration:0.7,ease:"power3.out"}},{start+0.4});')
    pf, pt = _props_of(sid, sc)
    return g + frag + pf, tl + pt

def ledger_list(sid, sc):
    """Reusable BLOCK: a dense hairline-separated row-list — ordinal + title + optional description + meta.
    A TOC / index / agenda / catalogue. Distinct from bullet_list (flat) and swiss-grid (2D cards). data:
    {kicker?, rows:[{title, desc?, meta?, num?}]}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    reg = d.get("register") or ("footage" if _grounded(d) else "paper")
    default_ground = {"kind": "transparent"} if reg == "footage" else {"kind": "paper"}
    g, tl = media_ground(sid, d.get("ground", default_ground), start, dur)
    frag = [f'<section class="scene clip {reg}" data-start="{start}" data-duration="{dur}" data-track-index="2">']
    if d.get("kicker"):
        frag.append(f'<div id="{sid}-k" class="kick">{esc(d["kicker"])}</div>')
        tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start+0.15});')
    frag.append('<div class="lg-wrap">')
    for i, row in enumerate(d.get("rows", [])):
        rid = f"{sid}-r{i}"
        num = row.get("num", f"{i+1:02d}")
        first = " first" if i == 0 else ""
        frag.append(f'<div class="lg-row{first}" id="{rid}"><div class="lg-num">{esc(str(num))}</div>'
                    f'<div class="lg-title">{esc(row.get("title", ""))}</div>'
                    f'<div class="lg-desc">{esc(row.get("desc", ""))}</div>'
                    f'<div class="lg-meta">{esc(row.get("meta", ""))}</div></div>')
        tl.append(f'tl.fromTo("#{rid}",{{opacity:0,x:-12}},{{opacity:1,x:0,duration:0.5,ease:"power2.out"}},{start+0.5+i*0.18});')
    frag.append('</div></section>')
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
        f'style="position:absolute;inset:0;background:var(--surface);"></div>',
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

    nhdark = " nh-dark" if _POLARITY == "dark" else ""      # aged dark-newsprint variant on dark themes
    frag = [f'<div id="{sid}-bg" class="clip nhbg" data-start="{start}" data-duration="{dur}" data-track-index="0"></div>',
            f'<section id="{sid}-scene" class="clip{nhdark}" data-start="{start}" data-duration="{dur}" data-track-index="2" style="position:absolute;inset:0;">',
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
            inner, cls, attr, tll = reveal_text(lid, line, reveal, start, cue, dur, operative=op, base="var(--text)")
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
    bg = d.get("backdrop", "var(--surface)")      # color | image path | "transparent" (theme default)
    if bg and bg != "transparent" and not _is_video_bg(bg):
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

def _diagram_3d(sid, sc):
    """diagram space:"3d" — the network on a receding perspective grid floor with a gliding camera
    (clip_08ba2177 look). Simple tidy layout in Python -> billboarded cards on the floor (X across,
    Z into depth), glowing connectors on the floor, camera dolly-in + gentle orbit. Pure CSS-3D +
    GSAP transforms (translateZ/rotateY/scaleX/opacity) -> seek-safe. data: same tree as diagram +
    space:"3d", kicker?, title?, titleHi?; node.hl highlights, node.sub subtitle."""
    import math
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    root = d["root"]
    nodes, kids = [], {}
    def walk(nd, depth, par):
        i = len(nodes); nodes.append((i, nd, depth, par)); kids[i] = []
        if par >= 0:
            kids[par].append(i)
        for ch in (nd.get("children") or []):
            walk(ch, depth + 1, i)
    walk(root, 0, -1)
    depth_of = {i: dep for i, nd, dep, par in nodes}
    maxd = max(depth_of.values()) if depth_of else 0
    px, cnt = {}, [0]            # tidy X: leaves sequential, parents centered over their children
    def assign(i):
        if not kids[i]:
            px[i] = cnt[0]; cnt[0] += 1
        else:
            for k in kids[i]:
                assign(k)
            px[i] = sum(px[k] for k in kids[i]) / len(kids[i])
    assign(0)
    xs = list(px.values()); lo, hi = (min(xs), max(xs)) if xs else (0, 0); midx = (lo + hi) / 2
    XS, ROWH, MARG, tilt = 360, 300, 260, 56
    PW = int((hi - lo) * XS) + 2 * MARG
    PH = maxd * ROWH + 2 * MARG
    POS = {i: ((px[i] - midx) * XS + PW / 2, depth_of[i] * ROWH + MARG) for i in px}
    left0, top0 = (1920 - PW) // 2, (1080 - PH) // 2
    frag = [f'<div class="clip dg3-bg" data-start="{start}" data-duration="{dur}" data-track-index="0"></div>',
            f'<div class="clip dg3-view" data-start="{start}" data-duration="{dur}" data-track-index="1" data-layout-allow-overflow>',
            f'<div class="dg3-stage"><div id="{sid}-plane" class="dg3-plane" '
            f'style="left:{left0}px;top:{top0}px;width:{PW}px;height:{PH}px;">']
    tl = []
    # connectors — reliable 2D SVG on the tilted plane; pathLength=1 normalises the draw (no getTotalLength)
    paths = []
    for i, nd, depth, par in nodes:
        if par < 0:
            continue
        ax, ay = POS[par]; bx, by = POS[i]; my = (ay + by) / 2
        paths.append(f'<path id="{sid}-c{i}" class="dg3-link" pathLength="1" '
                     f'd="M{ax:.0f},{ay:.0f} C{ax:.0f},{my:.0f} {bx:.0f},{my:.0f} {bx:.0f},{by:.0f}"/>')
    frag.append(f'<svg class="dg3-links" viewBox="0 0 {PW} {PH}" style="width:{PW}px;height:{PH}px;">{"".join(paths)}</svg>')
    for i, nd, depth, par in nodes:   # cards counter-rotated to STAND UP off the tilted plane (billboards)
        X, Y = POS[i]
        cls = "dg3-card" + (" root" if i == 0 else "") + (" hl" if nd.get("hl") else "")
        sub = f'<div class="sub">{esc(nd["sub"])}</div>' if nd.get("sub") else ""
        frag.append(f'<div class="{cls}" style="left:{X:.0f}px;top:{Y:.0f}px;transform:rotateX(-{tilt}deg);">'
                    f'<div class="cd" id="{sid}-cd{i}"><div class="lab">{esc(nd.get("label",""))}</div>{sub}</div></div>')
    frag.append('</div></div>')       # close plane + stage
    frag.append('</div>')             # close view
    if d.get("camera") == "tour":
        # FUSION: fly the 3D camera node-to-node (DFS pre-order) — frame a node, its children branch
        # out, then dive into a child. The plane's translate/scale is the camera; centering the family
        # on the plane centre lands it near screen centre through the tilt.
        focus = [i for i, nd, depth, par in nodes if kids[i]]     # internal nodes, DFS pre-order
        lead = 0.6
        stepdur = max(1.1, (dur - lead - 0.6) / max(1, len(focus)))
        FZ = 1.5
        def frame_of(i):
            fam = [i] + kids[i]
            cx = sum(POS[k][0] for k in fam) / len(fam)
            cy = sum(POS[k][1] for k in fam) / len(fam)
            return (PW / 2 - cx) * FZ, (PH / 2 - cy) * FZ + 110
        tl.append(f'tl.to("#{sid}-cd0",{{opacity:1,duration:0.5,ease:"power2.out"}},{start+0.15});')  # to (not fromTo): CSS holds the hidden state, so nothing leaks before its cue
        for s, fi in enumerate(focus):
            cs = start + lead + s * stepdur
            tx, ty = frame_of(fi)
            if s == 0:
                tl.append(f'tl.set("#{sid}-plane",{{x:{tx:.0f},y:{ty:.0f},scale:{FZ}}},{start});')
            else:
                tl.append(f'tl.to("#{sid}-plane",{{x:{tx:.0f},y:{ty:.0f},scale:{FZ},duration:0.95,ease:"power2.inOut"}},{cs-0.95:.2f});')
            for ci, j in enumerate(kids[fi]):   # this focus node's children branch out (only when its parent is focused)
                rc = cs + 0.2 + ci * 0.16
                tl.append(f'tl.to("#{sid}-c{j}",{{strokeDashoffset:0,opacity:1,duration:0.5,ease:"power2.inOut"}},{rc:.2f});')
                tl.append(f'tl.to("#{sid}-cd{j}",{{opacity:1,duration:0.45,ease:"power2.out"}},{rc+0.12:.2f});')
    else:
        # steady fly-over glide + front-to-back reveal
        tl.append(f'tl.fromTo("#{sid}-plane",{{scale:0.9,y:70}},{{scale:1.06,y:-40,duration:{dur},ease:"sine.inOut"}},{start});')
        lead = 0.4
        span = max(0.2, dur - lead - 1.0)
        def cue_of(i):
            return start + lead + (depth_of[i] / max(1, maxd)) * span * 0.78 + px[i] * 0.02
        for i, nd, depth, par in nodes:
            c = cue_of(i)
            tl.append(f'tl.to("#{sid}-cd{i}",{{opacity:1,duration:0.5,ease:"power2.out"}},{c:.2f});')
            if par >= 0:
                tl.append(f'tl.to("#{sid}-c{i}",{{strokeDashoffset:0,opacity:1,duration:0.55,ease:"power2.inOut"}},{max(cue_of(par), c - 0.2):.2f});')
    if d.get("kicker"):
        frag.append(f'<div id="{sid}-k" class="clip dg3-kick" data-start="{start}" data-duration="{dur}" data-track-index="2">{esc(d["kicker"])}</div>')
        tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:8}},{{opacity:1,y:0,duration:0.5}},{start+0.2});')
    if d.get("title"):
        t2, op = d["title"], d.get("titleHi", "")
        html_t = (f'{esc(t2.split(op,1)[0])}<span class="hl">{esc(op)}</span>{esc(t2.split(op,1)[1])}' if op and op in t2 else esc(t2))
        frag.append(f'<div id="{sid}-title" class="clip dg3-title" data-start="{start}" data-duration="{dur}" data-track-index="3">{html_t}</div>')
        tl.append(f'tl.fromTo("#{sid}-title",{{opacity:0,y:-10}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},{start+0.35});')
    return frag, tl


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
           titleHi?, register?:paper|dark, shape?:pill, dx?, dy?, rstep?, box?}.
      space:"3d" → the network on a receding perspective grid floor with a gliding camera (see _diagram_3d)."""
    if sc["data"].get("space") == "3d":
        return _diagram_3d(sid, sc)
    import copy
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    dark = (d.get("register") or ("dark" if _POLARITY == "dark" else "paper")) == "dark"   # diagram has a full dark variant; use it on dark themes
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
        rbase = "var(--text)" if reg == "paper" else "#F6F7F6"
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
    bg = spec.get("bg", "var(--surface-2)" if reg == "paper" else "#111417")   # paper side follows the theme; explicit dark side stays dark (self-lit, light ink)
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
    backdrop = d.get("backdrop") or ("#0a0b0c" if _POLARITY == "dark" else "var(--shell)")   # dark gaps only on dark themes
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
                      f'data-cmp-sstart="{start}" data-cmp-sdur="{dur}" '   # SCENE-local window → the injector
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
        # the title scrim is DARK (light text) so it reads over media panels; over text/stat panels on a
        # light theme that dark band clashes → flip to a theme-surface scrim + theme ink.
        light_title = _POLARITY == "light" and not any(s.get("type") in ("image", "video") for s in sides)
        frag.append(f'<div class="cmp-htitle{" light" if light_title else ""}">{kick}<div class="t" id="{sid}-ht">{html_t}</div></div>')
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
    bg = d.get("backdrop", "var(--shell)")
    if bg and bg != "transparent" and not _is_video_bg(bg):
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
      style:"slider", layout:"full" (default) — one at a time; full-bleed, OR set card_w/card_h to
        crossfade a CENTERED SIZED CARD (not full-screen). transition kenburns | crossfade.
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
    bg = d.get("backdrop", "var(--shell)")
    if bg and bg != "transparent" and not _is_video_bg(bg):
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
    cap_override = ""                             # caption placement; sized slider drops it below the card

    W = 1920
    if style == "coverflow":
        # card size / spacing / depth / vertical position + fade are all inputs
        CW, CH = int(d.get("card_w", 700)), int(d.get("card_h", 480))
        spacing, depth = float(d.get("spacing", 330)), float(d.get("depth", 175))
        fade = float(d.get("fade", 0.32))         # opacity lost per step of distance (smooth edge fade)
        cyf = float(d.get("y", 0.5))              # vertical centre as a fraction of height
        cap_override = f'top:{min(int(cyf * 1080 + CH * 0.58) + 16, 1032)}px;bottom:auto;'   # under the scaled centre card
        world.append(f'<div class="carstage"><div id="{sid}-3d" class="car3d">')
        for i, im in enumerate(imgs):
            # centre with GSAP xPercent/yPercent:-50 ONLY (no margins) — margins + yPercent double-shifted
            # the card up by a full card-height, pushing its top off-screen.
            world.append(f'<div id="{sid}-c{i}" class="carcard" style="width:{CW}px;height:{CH}px;left:50%;top:{cyf * 100:.1f}%;">'
                         f'<img src="{esc(im["src"])}" alt=""/></div>')
        world.append('</div></div>')
        # edge fade: dissolve the fanned side cards into the backdrop at the screen edges (so they
        # never hard-clip at the canvas border) — a gradient of the backdrop colour over left/right.
        edge_col = bg if isinstance(bg, str) and bg.startswith(("#", "rgb", "var(")) else "var(--shell)"
        world.append(f'<div class="caredge" style="background:linear-gradient(90deg,{edge_col} 0%,'
                     f'transparent 16%,transparent 84%,{edge_col} 100%);"></div>')

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
    else:                                         # slider — one at a time (full-bleed OR a sized card)
        transition = d.get("transition", "kenburns")
        sized = ("card_w" in d) or ("card_h" in d)   # give a size → a centred card, not full-screen
        if sized:
            CW, CH = int(d.get("card_w", 1200)), int(d.get("card_h", 675))
            cyf = float(d.get("y", 0.5))
            box = f'left:50%;top:{cyf * 100:.1f}%;margin-left:{-CW // 2}px;margin-top:{-CH // 2}px;width:{CW}px;height:{CH}px;'
            scls = "carslide sized"
            cap_override = f'top:{min(int(cyf * 1080 + CH / 2) + 20, 1028)}px;bottom:auto;'   # just under the card
        else:
            box, scls = "", "carslide"            # full-bleed (default)
        for i, im in enumerate(imgs):
            sidk = f"{sid}-s{i}"
            world.append(f'<div id="{sidk}" class="{scls}" style="{box}z-index:{i + 1};"><img src="{esc(im["src"])}" alt=""/></div>')
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
            world.append(f'<div id="{cid}" class="carcap" style="{cap_override}"></div>')
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


# linedraw measures each stroke ONCE at load (getTotalLength) and adds the seek-safe draw tweens
# (strokeDashoffset length->0, constant pen speed: per-path time proportional to its length). No lib.
_LINEDRAW_SETUP = r'''(function(){
  var CFG=@CFG@, root=document.getElementById("@SID@-svg"); if(!root) return;
  var svg=root.querySelector("svg"); if(!svg) return;
  var els=[].slice.call(svg.querySelectorAll("path,line,polyline,polygon,circle,ellipse,rect"));
  els=els.filter(function(e){ try{ return e.getTotalLength && e.getTotalLength()>0.5; }catch(x){ return false; } });
  if(CFG.order==="length-desc") els.sort(function(a,b){ return b.getTotalLength()-a.getTotalLength(); });
  else if(CFG.order==="length-asc") els.sort(function(a,b){ return a.getTotalLength()-b.getTotalLength(); });
  var lens=els.map(function(e){ return e.getTotalLength(); });
  var total=lens.reduce(function(a,b){ return a+b; },0)||1;
  var vb=svg.viewBox&&svg.viewBox.baseVal, r=svg.getBoundingClientRect();
  var scale=(vb&&vb.width&&r.width)?Math.min(r.width/vb.width, r.height/vb.height):1;
  var swU=CFG.strokePx/(scale||1);   // desired screen px -> user units (so dasharray stays in user units)
  els.forEach(function(e,i){ var L=lens[i]; e.style.strokeDasharray=L; e.style.strokeDashoffset=L;
    if(CFG.setWidth) e.style.strokeWidth=swU; e.style.willChange="stroke-dashoffset"; if(CFG.ink) e.style.fillOpacity=0; });
  var t=CFG.start+CFG.lead;
  els.forEach(function(e,i){ var L=lens[i], d=Math.max(0.16,(L/total)*CFG.drawDur);
    tl.to(e,{strokeDashoffset:0,duration:d,ease:"none"},t);
    if(CFG.ink) tl.to(e,{fillOpacity:1,duration:0.35,ease:"power1.out"},t+d);
    t+=d+CFG.gap; });
})();'''

def linedraw(sid, sc):
    """Reusable BLOCK: a self-drawing LINE-ART SVG. Each drawable element's stroke-dashoffset animates
    length->0 in order at a constant pen speed (per-path time proportional to its length), so the whole
    picture draws itself. A setup IIFE measures each path once at load (getTotalLength) and adds the
    seek-safe draw tweens; CSS themes the stroke. Vector line-art in; for a RASTER, centerline-trace it
    to SVG first, then feed it here.
    data: {svg | paths[+viewBox] | src, stroke?, strokeWidth?, order?:dom|length-asc|length-desc,
           register?:paper|footage, background?, keepStyle?, ink?, lead?, gap?, kicker?}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    if d.get("src"):
        svg_markup = Path(d["src"]).read_text(encoding="utf-8")
    elif d.get("paths"):
        vb = d.get("viewBox", "0 0 100 100")
        svg_markup = (f'<svg viewBox="{esc(vb)}" preserveAspectRatio="xMidYMid meet">'
                      + "".join(f'<path d="{esc(p)}"/>' for p in d["paths"]) + '</svg>')
    else:
        svg_markup = d.get("svg", "")
    reg = d.get("register", "paper")
    stroke = str(d.get("stroke", "var(--text)" if reg == "paper" else "#F6F7F6"))   # paper stroke/bg follow the theme
    keep = bool(d.get("keepStyle"))
    cls = "ld-keep" if keep else "ld-draw"
    bg = str(d.get("background", "var(--surface-2)" if reg == "paper" else "#0d0f11"))
    frag = [f'<div class="clip ld-bg" data-start="{start}" data-duration="{dur}" data-track-index="0" style="background:{esc(bg)};"></div>',
            f'<div id="{sid}-svg" class="clip ld-wrap {cls}" data-start="{start}" data-duration="{dur}" data-track-index="1" '
            f'data-layout-allow-overflow style="--ld-stroke:{esc(stroke)};">{svg_markup}</div>']
    lead = float(d.get("lead", 0.4))
    cfg = {"order": d.get("order", "dom"), "start": start, "lead": lead,
           "drawDur": max(1.0, dur - lead - 0.5), "gap": float(d.get("gap", 0.04)), "ink": bool(d.get("ink", False)),
           "strokePx": float(d.get("strokeWidth", 4)), "setWidth": not keep}
    tl = [_LINEDRAW_SETUP.replace("@SID@", sid).replace("@CFG@", json.dumps(cfg, ensure_ascii=False))]
    if d.get("kicker"):
        frag.append(f'<div id="{sid}-k" class="clip kick" data-start="{start}" data-duration="{dur}" data-track-index="2" '
                    f'style="color:{esc(stroke)};">{esc(d["kicker"])}</div>')
        tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start+0.2});')
    return frag, tl

def document(sid, sc):
    """Reusable BLOCK: a PAGE / SHEET (document · article · letter) as the subject, with reveal/stack/
    artifact motion + an annotations layer (highlighter sweep · underline · summary callout card · pinned
    label · handwritten caption). Distilled from Vox-style document beats. Pure GSAP+CSS, seek-safe.
      mode:"page"(default) full-bleed sheet · "stack" several pages cascade/fan · "artifact" sheet(s) on a
        backdrop (e.g. velvet) with a cinematic push. camera:"push"(Ken-Burns)|"scroll"|"static".
      Annotations are GLUED to the page (highlight/underline/label ride the camera); callouts + caption are
        screen-fixed. highlight/underline rect = [fx,fy,fw,fh|fw] and label at = [fx,fy] are FRACTIONS of the page.
    data: {source:str|[str], mode?, fit?:cover|contain, backdrop?, vignette?, aged?, tilt?, camera?,
           kicker?, title?, titleHi?, annotations?:[{type:highlight|underline|label|callout|caption, ...}]}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    mode = d.get("mode", "page")
    fit = d.get("fit", "contain" if mode == "artifact" else "cover")
    src = d.get("source"); pages = list(src) if isinstance(src, list) else [src]
    W, H = 1920, 1080
    backdrop = d.get("backdrop") or (("#2a1013" if mode == "artifact" else "#17181b") if _POLARITY == "dark" else "var(--surface)")
    agedc = " aged" if d.get("aged") else ""
    tilt = float(d.get("tilt", 0))
    # page_size [w,h] (set by resolve_doc_annotations.py) sizes the sheet to the page's aspect so the
    # image fills it exactly (no crop) → annotation fractions map 1:1 to the page. Absent → full-bleed cover.
    psize = d.get("page_size"); aspect = (psize[0] / psize[1]) if psize else None
    frag = [f'<div class="clip doc-bg" data-start="{start}" data-duration="{dur}" data-track-index="0" style="background:{esc(backdrop)};"></div>']
    tl = []
    vig = float(d.get("vignette", 0.42 if mode == "artifact" else 0) or 0)
    if vig > 0:
        frag.append(f'<div class="clip doc-vig" data-start="{start}" data-duration="{dur}" data-track-index="1" '
                    f'style="box-shadow:inset 0 0 26cqw rgba(0,0,0,{min(0.9,vig):.2f});"></div>')
    if mode == "artifact":
        pw, ph = (int(930 * aspect), 930) if aspect else (700, 930)
        rects = ([(W//2 - pw + 60, (H-ph)//2 + 14, pw, ph, tilt - 4), (W//2 - 60, (H-ph)//2 - 22, pw, ph, tilt + 3)]
                 if len(pages) >= 2 else [((W-pw)//2, (H-ph)//2 - 6, pw, ph, tilt or -2)])
    elif mode == "stack":
        pw, ph = (int(1000 * aspect), 1000) if aspect else (880, 1000); n = len(pages)
        rects = [(int(W/2 - pw/2 + (i-(n-1)/2)*76), int(H/2 - ph/2 + (i-(n-1)/2)*24), pw, ph, tilt + (i-(n-1)/2)*3) for i in range(n)]
    else:  # page — fit the page below the title band; aspect-fit when known so annotation coords map 1:1
        m = 44; top = 156 if (d.get("title") or d.get("kicker")) else m
        bw, bh = W - 2*m, H - top - m
        if aspect:
            w = int(bh * aspect) if (bw / bh) > aspect else bw
            h = bh if (bw / bh) > aspect else int(bw / aspect)
            rects = [(int(m + (bw - w) / 2), int(top + (bh - h) / 2), w, h, tilt)]
        else:
            rects = [(m, top, bw, bh, tilt)]
        pages = pages[:1]
    npg = min(len(pages), len(rects))
    frag.append(f'<div id="{sid}-world" class="clip doc-world" data-start="{start}" data-duration="{dur}" data-track-index="2" data-layout-allow-overflow>')
    for i in range(npg):
        rx, ry, rw, rh, rot = rects[i]; pid = f"{sid}-pg{i}"
        frag.append(f'<div id="{pid}" class="doc-sheet{" contain" if fit=="contain" else ""}{agedc}" '
                    f'style="left:{rx}px;top:{ry}px;width:{rw}px;height:{rh}px;background-image:url(\'{esc(pages[i])}\');'
                    f'transform:rotate({rot:.2f}deg);"><div class="doc-grain"></div></div>')
        if mode == "stack":
            cue = start + 0.2 + i * 0.3
            tl.append(f'tl.fromTo("#{pid}",{{opacity:0,y:70,rotation:{rot-7:.2f}}},{{opacity:1,y:0,rotation:{rot:.2f},duration:0.6,ease:"power3.out"}},{cue:.2f});')
        else:
            cue = start + 0.15 + i * 0.22
            tl.append(f'tl.fromTo("#{pid}",{{opacity:0,scale:1.03,y:26,rotation:{rot:.2f}}},{{opacity:1,scale:1,y:0,rotation:{rot:.2f},duration:0.7,ease:"power3.out"}},{cue:.2f});')
    prx, pry, prw, prh, _ = rects[0]
    def fx(v): return prx + v * prw
    def fy(v): return pry + v * prh
    overlay, ai = [], 0
    for an in d.get("annotations", []):
        t = an.get("type"); ai += 1
        cue = start + float(an.get("cue", 1.0 + ai * 0.5))
        # Skip an annotation missing the geometry its type needs — e.g. a `find`-annotation that
        # resolve_doc_annotations.py never resolved to a `rect` (no text layer / no match). Warn and
        # continue instead of KeyError'ing the whole compose (holbein POST_MORTEM #6).
        _need = {"highlight": ("rect",), "underline": ("rect",), "label": ("at", "text")}.get(t, ())
        _missing = [k for k in _need if k not in an]
        if _missing:
            print(f"  ⚠ document {sid}: {t} annotation missing {_missing} "
                  f"(unresolved find={an.get('find')!r}?) — skipped")
            continue
        if t == "highlight":
            x, y, w, h = an["rect"]; hid = f"{sid}-hl{ai}"
            frag.append(f'<div id="{hid}" class="doc-hl" style="left:{fx(x):.0f}px;top:{fy(y):.0f}px;width:{w*prw:.0f}px;'
                        f'height:{h*prh:.0f}px;background:{esc(an.get("color","#FFF23B"))};"></div>')
            tl.append(f'tl.fromTo("#{hid}",{{scaleX:0}},{{scaleX:1,duration:0.5,ease:"power2.out"}},{cue:.2f});')
        elif t == "underline":
            r = list(an["rect"]) + [0, 0, 0]; x, y, w = r[0], r[1], r[2]; uid = f"{sid}-ul{ai}"
            frag.append(f'<div id="{uid}" class="doc-underline" style="left:{fx(x):.0f}px;top:{fy(y):.0f}px;width:{w*prw:.0f}px;'
                        f'background:{esc(an.get("color","#C8232C"))};"></div>')
            tl.append(f'tl.fromTo("#{uid}",{{scaleX:0}},{{scaleX:1,duration:0.4,ease:"power2.out"}},{cue:.2f});')
        elif t == "label":
            x, y = an["at"]; lid = f"{sid}-lb{ai}"
            frag.append(f'<div id="{lid}" class="doc-label" style="left:{fx(x):.0f}px;top:{fy(y):.0f}px;background:{esc(an.get("color","#C8232C"))};">{esc(an["text"])}</div>')
            tl.append(f'tl.fromTo("#{lid}",{{scale:0}},{{scale:1,duration:0.45,ease:"back.out(2.2)"}},{cue:.2f});')
        elif t in ("callout", "caption"):
            overlay.append((t, an, cue, ai))
    frag.append('</div>')  # close world
    cam = d.get("camera", "static")
    if cam == "push":
        tl.append(f'tl.fromTo("#{sid}-world",{{scale:1}},{{scale:1.07,duration:{dur},ease:"none"}},{start});')
    elif cam == "scroll":
        tl.append(f'tl.fromTo("#{sid}-world",{{yPercent:0}},{{yPercent:-9,duration:{dur},ease:"none"}},{start});')
    frag.append(f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="3" style="position:absolute;inset:0;pointer-events:none;">')
    for (t, an, cue, ai) in overlay:
        if t == "callout":
            side = an.get("side", "right"); yy = float(an.get("y", 0.5)); cid = f"{sid}-co{ai}"
            lines = an.get("text"); lines = lines if isinstance(lines, list) else [lines]
            kick = f'<div class="ck">{esc(an["title"])}</div>' if an.get("title") else ""
            body = "".join(f'<span class="ln">{esc(x)}</span>' for x in lines)
            pos = "right:4.5cqw;" if side == "right" else "left:4.5cqw;"
            frag.append(f'<div id="{cid}" class="doc-callout" style="{pos}top:{yy*100:.0f}%;transform:translateY(-50%);">{kick}<div class="ct">{body}</div></div>')
            tl.append(f'tl.fromTo("#{cid}",{{opacity:0,x:{60 if side=="right" else -60}}},{{opacity:1,x:0,duration:0.55,ease:"power3.out"}},{cue:.2f});')
        else:  # caption
            txt = an["text"]; u = an.get("underline", ""); cid = f"{sid}-cap{ai}"
            if u and u in txt:
                b, a = txt.split(u, 1)
                inner = f'{esc(b)}<span class="uw">{esc(u)}<span class="ul" id="{cid}-u"></span></span>{esc(a)}'
            else:
                inner = esc(txt)
            frag.append(f'<div id="{cid}" class="doc-caption">{inner}</div>')
            tl.append(f'tl.fromTo("#{cid}",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},{cue:.2f});')
            if u and u in txt:
                tl.append(f'tl.fromTo("#{cid}-u",{{scaleX:0}},{{scaleX:1,duration:0.5,ease:"power2.out"}},{cue+0.5:.2f});')
    if d.get("kicker"):
        frag.append(f'<div id="{sid}-k" class="doc-kick">{esc(d["kicker"])}</div>')
        tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:8}},{{opacity:1,y:0,duration:0.5}},{start+0.2});')
    if d.get("title"):
        t2, op = d["title"], d.get("titleHi", "")
        html_t = (f'{esc(t2.split(op,1)[0])}<span class="hl">{esc(op)}</span>{esc(t2.split(op,1)[1])}' if op and op in t2 else esc(t2))
        frag.append(f'<div id="{sid}-title" class="doc-title">{html_t}</div>')
        tl.append(f'tl.fromTo("#{sid}-title",{{opacity:0,y:-10}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},{start+0.35});')
    frag.append('</div>')  # close overlay
    return frag, tl

def lower_third(sid, sc):
    """Reusable BLOCK: a lower-third identifier (name + role, optional kicker) — the on-screen caption
    for talking-head / interview / podcast footage. Collapses the registry's ~12 lt-* variants into ONE
    theme-driven block + a `style` param. Seek-safe (transform/opacity), theme-driven (accent/text/
    surface/accent-ink tokens), font-body typography.
    styles: bar (surface card + accent tab, slides in) · card (surface card + a drawn accent underline,
            rises) · underline (cardless: name rises, accent rule draws L->R; text-shadowed for footage) ·
            block (a bold accent-colour block wipes in, ink name slams up).
    data: {name, role?, kicker?, style?, position?(bl|bc|br), backdrop?(demo/standalone only — normally
           transparent over footage)}."""
    # Deferred styles (add in-place when a beat asks): side-rule · soft-pill · mask-reveal · stack-bars ·
    # news-ticker (scrolling crawl). All the same block + a style branch.
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    name, role, kicker = d.get("name", ""), d.get("role", ""), d.get("kicker", "")
    style, posn = d.get("style", "bar"), d.get("position", "bl")
    frag, tl = [], []
    bg = d.get("backdrop")                         # normally transparent (over footage); demo can set it
    if bg and not _is_video_bg(bg):
        if isinstance(bg, str) and (bg.endswith((".png", ".jpg", ".jpeg", ".webp")) or "/" in bg):
            frag.append(f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="0" '
                        f'style="position:absolute;inset:0;background:#111;background-image:url(\'{esc(bg)}\');background-size:cover;background-position:center;"></div>')
        else:
            frag.append(f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="0" style="position:absolute;inset:0;background:{esc(bg)};"></div>')
    anchor = {"bl": "left:5.5cqw;", "bc": "left:50%;transform:translateX(-50%);text-align:center;",
              "br": "right:5.5cqw;text-align:right;"}.get(posn, "left:5.5cqw;")
    w = f"{sid}-lt"
    kick = f'<div class="lt-kicker">{esc(kicker)}</div>' if kicker else ""
    role_h = f'<div id="{w}-r" class="lt-role">{esc(role)}</div>' if role else ""

    if style == "block":
        inner = (f'<div id="{w}-box" class="lt-block">{kick}'
                 f'<div id="{w}-n" class="lt-name">{esc(name)}</div>{role_h}</div>')
        tl += [f'tl.fromTo("#{w}-box",{{scaleX:0}},{{scaleX:1,duration:0.5,ease:"power3.out"}},{start + 0.2});',
               f'tl.fromTo("#{w}-n",{{opacity:0,y:16}},{{opacity:1,y:0,duration:0.5,ease:"power3.out"}},{start + 0.45});']
        if role: tl.append(f'tl.fromTo("#{w}-r",{{opacity:0}},{{opacity:1,duration:0.4}},{start + 0.7});')
    elif style == "underline":
        inner = (f'<div class="lt-cardless">{kick}<div id="{w}-n" class="lt-name">{esc(name)}</div>'
                 f'<div id="{w}-u" class="lt-underline-rule"></div>{role_h}</div>')
        tl += [f'tl.fromTo("#{w}-n",{{opacity:0,y:18}},{{opacity:1,y:0,duration:0.55,ease:"power3.out"}},{start + 0.25});',
               f'tl.fromTo("#{w}-u",{{scaleX:0}},{{scaleX:1,duration:0.5,ease:"power2.out"}},{start + 0.55});']
        if role: tl.append(f'tl.fromTo("#{w}-r",{{opacity:0}},{{opacity:1,duration:0.4}},{start + 0.8});')
    elif style == "card":
        inner = (f'<div id="{w}-box" class="lt-card">{kick}<div id="{w}-n" class="lt-name">{esc(name)}</div>'
                 f'<div id="{w}-u" class="lt-underline-rule"></div>{role_h}</div>')
        tl += [f'tl.fromTo("#{w}-box",{{opacity:0,y:24}},{{opacity:1,y:0,duration:0.55,ease:"power3.out"}},{start + 0.2});',
               f'tl.fromTo("#{w}-u",{{scaleX:0}},{{scaleX:1,duration:0.5,ease:"power2.out"}},{start + 0.55});']
        if role: tl.append(f'tl.fromTo("#{w}-r",{{opacity:0}},{{opacity:1,duration:0.4}},{start + 0.75});')
    else:  # bar (default)
        inner = (f'<div id="{w}-box" class="lt-bar"><div class="lt-tab"></div>'
                 f'<div class="lt-txt">{kick}<div id="{w}-n" class="lt-name">{esc(name)}</div>{role_h}</div></div>')
        tl += [f'tl.fromTo("#{w}-box",{{opacity:0,x:-40}},{{opacity:1,x:0,duration:0.5,ease:"power3.out"}},{start + 0.2});',
               f'tl.fromTo("#{w}-n",{{opacity:0}},{{opacity:1,duration:0.4}},{start + 0.4});']
        if role: tl.append(f'tl.fromTo("#{w}-r",{{opacity:0}},{{opacity:1,duration:0.4}},{start + 0.55});')

    return frag + [f'<section class="clip" data-start="{start}" data-duration="{dur}" data-track-index="2" '
                   f'style="position:absolute;inset:0;pointer-events:none;">'
                   f'<div class="ltwrap" style="{anchor}bottom:13cqh;">{inner}</div></section>'], tl


def _num(v):
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:g}"


def chart(sid, sc):
    """Reusable BLOCK: an animated bar OR line chart — GSAP + SVG/CSS, NOT d3/Chart.js (the framework
    bans chart libs for seek-safety). Bars grow from the baseline staggered, or a line draws in; value
    labels + axis labels + gridlines reveal. Theme-driven (accent bars/line, text/rule/surface tokens).
    data: {type?(bar|line), series:[{label,value}], title?, titleHi?, kicker?, prefix?, suffix?, ymax?,
           highlight?(int index to emphasise; the rest mute)}."""
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    series = d.get("series", [])
    n = max(1, len(series))
    typ = d.get("type", "bar")
    vals = [float(s.get("value", 0)) for s in series] or [0.0]
    ymax = float(d.get("ymax") or (max(vals) * 1.18 or 1))
    pre, suf = d.get("prefix", ""), d.get("suffix", "")
    hl = d.get("highlight")
    hl = int(hl) if isinstance(hl, (int, float)) and 0 <= int(hl) < n else None
    PX, PW, BASE, PH = 210, 1500, 190, 600         # plot left, width, baseline (from bottom), max height
    frag = [f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="0" '
            f'style="position:absolute;inset:0;background:var(--shell);"></div>']
    world = [f'<section class="clip chart" data-start="{start}" data-duration="{dur}" data-track-index="2" '
             f'style="position:absolute;inset:0;">']
    tl = []
    if d.get("kicker"):
        world.append(f'<div id="{sid}-k" class="ch-kicker">{esc(d["kicker"])}</div>')
        tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.5}},{start + 0.1});')
    if d.get("title"):
        t, op = d["title"], d.get("titleHi", "")
        html_t = (f'{esc(t.split(op, 1)[0])}<span class="hl">{esc(op)}</span>{esc(t.split(op, 1)[1])}'
                  if op and op in t else esc(t))
        world.append(f'<div id="{sid}-t" class="ch-title">{html_t}</div>')
        tl.append(f'tl.fromTo("#{sid}-t",{{opacity:0,y:12}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},{start + 0.2});')
    world.append(f'<div class="ch-base" style="left:{PX - 20}px;bottom:{BASE}px;width:{PW + 40}px;"></div>')
    for g in range(1, 4):
        world.append(f'<div class="ch-grid" style="left:{PX - 20}px;bottom:{BASE + PH * g / 3:.0f}px;width:{PW + 40}px;"></div>')
    slot = PW / n

    if typ == "line":
        step = PW / max(1, n - 1)
        pts = [(PX + i * step, (1080 - BASE) - vals[i] / ymax * PH) for i in range(n)]
        dpath = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        world.append(f'<svg id="{sid}-svg" class="ch-svg" viewBox="0 0 1920 1080" preserveAspectRatio="none">'
                     f'<path id="{sid}-line" d="{dpath}" fill="none"/></svg>')
        tl.append(f'(function(){{var p=document.getElementById("{sid}-line"),L=p.getTotalLength();'
                  f'p.style.strokeDasharray=L;p.style.strokeDashoffset=L;'
                  f'tl.fromTo(p,{{strokeDashoffset:L}},{{strokeDashoffset:0,duration:1.5,ease:"power2.inOut"}},{start + 0.5});}})();')
        for i, (x, y) in enumerate(pts):
            world.append(f'<div id="{sid}-dot{i}" class="ch-dot" style="left:{x:.0f}px;top:{y:.0f}px;"></div>')
            world.append(f'<div id="{sid}-v{i}" class="ch-val" style="left:{x - slot / 2:.0f}px;top:{y - 60:.0f}px;width:{slot:.0f}px;">{esc(pre)}{_num(vals[i])}{esc(suf)}</div>')
            world.append(f'<div class="ch-xlab" style="left:{x - slot / 2:.0f}px;bottom:{BASE - 58:.0f}px;width:{slot:.0f}px;">{esc(series[i].get("label", ""))}</div>')
            cue = start + 0.6 + i * (1.3 / max(1, n - 1))
            tl.append(f'tl.fromTo("#{sid}-dot{i}",{{scale:0}},{{scale:1,duration:0.4,ease:"back.out(2)"}},{cue:.2f});')
            tl.append(f'tl.fromTo("#{sid}-v{i}",{{opacity:0,y:6}},{{opacity:1,y:0,duration:0.4}},{cue + 0.1:.2f});')
    else:  # bar
        bw = slot * 0.6
        for i, s in enumerate(series):
            h = vals[i] / ymax * PH
            x = PX + i * slot + (slot - bw) / 2
            fill = "var(--accent)" if (hl is None or i == hl) else "var(--text-faint)"
            world.append(f'<div id="{sid}-b{i}" class="ch-bar" style="left:{x:.0f}px;bottom:{BASE}px;width:{bw:.0f}px;height:{h:.0f}px;background:{fill};"></div>')
            world.append(f'<div id="{sid}-v{i}" class="ch-val" style="left:{x:.0f}px;bottom:{BASE + h + 14:.0f}px;width:{bw:.0f}px;">{esc(pre)}{_num(vals[i])}{esc(suf)}</div>')
            world.append(f'<div class="ch-xlab" style="left:{x:.0f}px;bottom:{BASE - 58:.0f}px;width:{bw:.0f}px;">{esc(s.get("label", ""))}</div>')
            cue = start + 0.5 + i * (1.3 / n)
            tl.append(f'tl.fromTo("#{sid}-b{i}",{{scaleY:0}},{{scaleY:1,duration:0.6,ease:"power3.out"}},{cue:.2f});')
            tl.append(f'tl.fromTo("#{sid}-v{i}",{{opacity:0,y:8}},{{opacity:1,y:0,duration:0.4}},{cue + 0.35:.2f});')
    world.append('</section>')
    return frag + world, tl


_CODE_KW = set(("const let var function return if else for while do class extends super import from export "
    "default new await async def print lambda pass raise try except finally with as in is not and or True "
    "False None this typeof void yield break continue switch case throw public private protected static final "
    "int float double string bool boolean char long func fn use pub mut struct enum interface type namespace").split())

_CODE_THEMES = {
    "monokai":     {"bg": "#272822", "fg": "#f8f8f2", "kw": "#f92672", "str": "#e6db74", "com": "#75715e", "num": "#ae81ff", "fn": "#a6e22e", "punct": "#f8f8f2", "gut": "#90908a"},
    "vs-dark":     {"bg": "#1e1e1e", "fg": "#d4d4d4", "kw": "#569cd6", "str": "#ce9178", "com": "#6a9955", "num": "#b5cea8", "fn": "#dcdcaa", "punct": "#d4d4d4", "gut": "#858585"},
    "vs-light":    {"bg": "#ffffff", "fg": "#1e1e1e", "kw": "#0000ff", "str": "#a31515", "com": "#008000", "num": "#098658", "fn": "#795e26", "punct": "#1e1e1e", "gut": "#237893"},
    "github-dark": {"bg": "#0d1117", "fg": "#c9d1d9", "kw": "#ff7b72", "str": "#a5d6ff", "com": "#8b949e", "num": "#79c0ff", "fn": "#d2a8ff", "punct": "#c9d1d9", "gut": "#6e7681"},
    "dracula":     {"bg": "#282a36", "fg": "#f8f8f2", "kw": "#ff79c6", "str": "#f1fa8c", "com": "#6272a4", "num": "#bd93f9", "fn": "#50fa7b", "punct": "#f8f8f2", "gut": "#6272a4"},
}


def _tok_line(line):
    out = []
    for m in re.finditer(r'(//[^\n]*|\#[^\n]*)|("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`[^`]*`)|(\b\d[\d._x]*\b)|([A-Za-z_$][\w$]*)|(\s+)|([^\w\s])', line):
        com, st, num, idt, ws, pu = m.groups()
        if com is not None:   out.append(("com", com))
        elif st is not None:  out.append(("str", st))
        elif num is not None: out.append(("num", num))
        elif idt is not None: out.append(("kw" if idt in _CODE_KW else ("fn" if line[m.end():m.end() + 1] == "(" else "var"), idt))
        elif ws is not None:  out.append(("ws", ws))
        else:                 out.append(("punct", pu))
    return out


def code(sid, sc):
    """Reusable BLOCK: a syntax-highlighted code window that types in / spotlights a line. Tokenised at
    BUILD time in Python (no browser highlighter) -> pre-coloured spans; reveal is transform/opacity
    (seek-safe). The SYNTAX palette is a fixed code `theme` (monokai/vs-dark/vs-light/github-dark/dracula)
    — its own identity, NOT the NOLAN video theme; the scene backdrop + title DO use NOLAN tokens (hybrid).
    modes: typing (lines reveal staggered) · highlight (spotlight one line, dim the rest).
    data: {code, theme?, mode?, highlight?(1-based line), highlight_at?, filename?, linenums?, title?,
           titleHi?, kicker?}."""
    # Deferred modes: diff (removed red / added green), scroll (camera to a line), char-level caret typing.
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    ct = _CODE_THEMES.get(d.get("theme", "monokai"), _CODE_THEMES["monokai"])
    mode = d.get("mode", "typing")
    lines = str(d.get("code", "")).replace("\t", "    ").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    n = max(1, len(lines))
    linenums = bool(d.get("linenums"))
    hl = d.get("highlight")
    hl = int(hl) if isinstance(hl, (int, float)) and 1 <= int(hl) <= n else None
    frag = [f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="0" '
            f'style="position:absolute;inset:0;background:var(--shell);"></div>']
    world = [f'<section class="clip codeblk" data-start="{start}" data-duration="{dur}" data-track-index="2" '
             f'style="position:absolute;inset:0;">']
    tl = []
    top = 9
    if d.get("kicker"):
        world.append(f'<div id="{sid}-k" class="cd-kicker">{esc(d["kicker"])}</div>')
        top = 13
        tl.append(f'tl.fromTo("#{sid}-k",{{opacity:0,y:8}},{{opacity:1,y:0,duration:0.5}},{start + 0.1});')
    if d.get("title"):
        t, op = d["title"], d.get("titleHi", "")
        ht = (f'{esc(t.split(op, 1)[0])}<span class="hl">{esc(op)}</span>{esc(t.split(op, 1)[1])}'
              if op and op in t else esc(t))
        world.append(f'<div id="{sid}-t" class="cd-title">{ht}</div>')
        top = 18
        tl.append(f'tl.fromTo("#{sid}-t",{{opacity:0,y:10}},{{opacity:1,y:0,duration:0.6,ease:"power3.out"}},{start + 0.2});')
    world.append(f'<div id="{sid}-win" class="cd-win" style="top:{top}cqh;background:{ct["bg"]};">')
    dots = ('<span class="cd-dot" style="background:#ff5f56"></span><span class="cd-dot" style="background:#ffbd2e">'
            '</span><span class="cd-dot" style="background:#27c93f"></span>')
    world.append(f'<div class="cd-bar" style="border-color:{ct["gut"]}44;">{dots}'
                 f'<span class="cd-fname" style="color:{ct["gut"]}">{esc(d.get("filename", ""))}</span></div>')
    world.append(f'<div class="cd-code" style="color:{ct["fg"]};">')
    for i, line in enumerate(lines):
        gut = f'<span class="cd-gut" style="color:{ct["gut"]}">{i + 1}</span>' if linenums else ""
        spans = ""
        for cls, txt in _tok_line(line):
            spans += esc(txt) if cls == "ws" else f'<span style="color:{ct.get(cls, ct["fg"])}">{esc(txt)}</span>'
        band = " cd-hl" if hl == i + 1 else ""
        world.append(f'<div id="{sid}-l{i}" class="cd-line{band}">{gut}<span class="cd-lt">{spans or "&nbsp;"}</span></div>')
    world.append('</div></div>')
    tl.append(f'tl.fromTo("#{sid}-win",{{opacity:0,y:26,scale:0.98}},{{opacity:1,y:0,scale:1,duration:0.6,ease:"power3.out"}},{start + 0.3});')
    if mode == "highlight":
        for i in range(n):
            tl.append(f'tl.fromTo("#{sid}-l{i}",{{opacity:0}},{{opacity:1,duration:0.3}},{start + 0.5 + i * 0.045:.2f});')
        hc = start + float(d.get("highlight_at", dur * 0.5))
        for i in range(n):
            if hl and i + 1 == hl:
                continue
            tl.append(f'tl.to("#{sid}-l{i}",{{opacity:0.3,duration:0.5,ease:"power2.inOut"}},{hc:.2f});')
    else:  # typing — lines reveal staggered
        span = min(dur * 0.62, 0.28 * n)
        step = span / max(1, n - 1) if n > 1 else 0
        for i in range(n):
            tl.append(f'tl.fromTo("#{sid}-l{i}",{{opacity:0,x:-12}},{{opacity:1,x:0,duration:0.35,ease:"power2.out"}},{start + 0.7 + i * step:.2f});')
    world.append('</section>')
    return frag + world, tl


def _initials(name):
    parts = [p for p in re.split(r"\s+", str(name).strip()) if p]
    return ((parts[0][:1] + (parts[-1][:1] if len(parts) > 1 else "")).upper() or "?") if parts else "?"


def social_card(sid, sc):
    """Reusable BLOCK: a social post / now-playing card overlay — X (Twitter), Reddit, or Spotify.
    Brand-FIXED palettes (each platform's own colours inline — a Reddit card is always Reddit orange,
    NOT the NOLAN video theme); only the scene backdrop uses a NOLAN token. Card slides + scales in;
    the Spotify progress bar fills. Seek-safe.
    data: {platform(x|reddit|spotify), name?, handle?, text?, avatar?, verified?, likes?, reposts?,
           replies?, upvotes?, comments?, subreddit?, track?, artist?, art?, progress?(0..1),
           position?(center|bl|br), backdrop?}."""
    # Deferred platforms (same block + branch): instagram/tiktok follow overlays, youtube subscribe.
    d, start, dur = sc["data"], sc["start"], sc["dur"]
    plat = d.get("platform", "x")
    frag, tl = [], []
    bg = d.get("backdrop", "var(--shell)")
    # a VIDEO backdrop (_is_video_bg) is left transparent here and root-injected behind the card by
    # incremental.frame_grounds (a CSS background-image can't play a video). image/colour render inline.
    if bg and bg != "transparent" and not _is_video_bg(bg):
        if isinstance(bg, str) and (bg.endswith((".png", ".jpg", ".jpeg", ".webp")) or "/" in bg):
            frag.append(f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="0" '
                        f'style="position:absolute;inset:0;background:#111;background-image:url(\'{esc(bg)}\');background-size:cover;background-position:center;"></div>')
        else:
            frag.append(f'<div class="clip" data-start="{start}" data-duration="{dur}" data-track-index="0" style="position:absolute;inset:0;background:{esc(bg)};"></div>')
    anchor = {"center": "left:50%;top:50%;transform:translate(-50%,-50%);", "bl": "left:6cqw;bottom:10cqh;",
              "br": "right:6cqw;bottom:10cqh;"}.get(d.get("position", "center"), "left:50%;top:50%;transform:translate(-50%,-50%);")
    w = f"{sid}-sc"

    def av(seed, img):
        return f'<img src="{esc(img)}" alt=""/>' if img else esc(_initials(seed))

    if plat == "reddit":
        inner = (f'<div class="soc-votes"><div class="soc-up"></div>'
                 f'<div class="n">{esc(str(d.get("upvotes", d.get("likes", ""))))}</div><div class="soc-dn"></div></div>'
                 f'<div class="soc-rbody"><div class="soc-sub">r/{esc(d.get("subreddit", d.get("handle", "")))}</div>'
                 f'<div class="soc-rtitle">{esc(d.get("text", d.get("name", "")))}</div>'
                 f'<div class="soc-rmeta">{esc(str(d.get("comments", d.get("replies", 0))))} comments · Share · Save</div></div>')
        cls = "soc-reddit"
    elif plat == "spotify":
        prog = max(0.0, min(1.0, float(d.get("progress", 0.4))))
        inner = (f'<div class="soc-art">{av(d.get("track", ""), d.get("art"))}</div>'
                 f'<div class="soc-sbody"><div class="soc-track">{esc(d.get("track", d.get("name", "")))}</div>'
                 f'<div class="soc-artist">{esc(d.get("artist", d.get("handle", "")))}</div>'
                 f'<div class="soc-prog"><div id="{w}-pf" class="soc-prog-fill" style="width:{prog * 100:.0f}%;"></div></div></div>'
                 f'<div class="soc-splay">&#9654;</div>')
        cls = "soc-spotify"
        tl.append(f'tl.fromTo("#{w}-pf",{{scaleX:0}},{{scaleX:1,duration:1.3,ease:"power2.out"}},{start + 0.6});')
    else:  # x
        vf = '<span class="soc-vf">&#10003;</span>' if d.get("verified") else ""
        inner = (f'<div class="soc-head"><div class="soc-av">{av(d.get("name", ""), d.get("avatar"))}</div>'
                 f'<div class="soc-id"><div class="soc-name">{esc(d.get("name", ""))}{vf}</div>'
                 f'<div class="soc-handle">@{esc(d.get("handle", ""))}</div></div><div class="soc-logo">X</div></div>'
                 f'<div class="soc-text">{esc(d.get("text", ""))}</div>'
                 f'<div class="soc-metrics"><span><b>{esc(str(d.get("replies", 0)))}</b> Replies</span>'
                 f'<span><b>{esc(str(d.get("reposts", 0)))}</b> Reposts</span>'
                 f'<span class="soc-heart"><b>{esc(str(d.get("likes", 0)))}</b> Likes</span></div>')
        cls = "soc-x"
    tl.insert(0, f'tl.fromTo("#{w}",{{opacity:0,y:30,scale:0.96}},{{opacity:1,y:0,scale:1,duration:0.6,ease:"power3.out"}},{start + 0.2});')
    return frag + [f'<section class="clip" data-start="{start}" data-duration="{dur}" data-track-index="2" '
                   f'style="position:absolute;inset:0;"><div class="soc-wrap" style="{anchor}">'
                   f'<div id="{w}" class="soc-card {cls}">{inner}</div></div></section>'], tl


BLOCKS = {"stat": stat_lockup, "statement": highlight_statement, "geo": geo_map, "raw": raw_scene,
          "bullet_list": bullet_list, "pull_quote": pull_quote,
          "comparison_table": comparison_table, "ledger": ledger_list,
          "timeline": timeline, "newshead": newshead, "collage": collage,
          "diagram": diagram, "comparison": comparison, "gallery": gallery, "carousel": carousel,
          "linedraw": linedraw, "document": document, "lower_third": lower_third, "chart": chart,
          "code": code, "social_card": social_card}

# Tier-2 extension blocks (kept out of this file's core registry; catalog.json documents them, so
# check_catalog.py still enforces BLOCKS<->catalog parity over the merged set). Imported LAST so the
# extension can reference compose's helpers (esc / _POLARITY / reveal_text) at call time.
try:
    from compose_extension import EXT_BLOCKS
    BLOCKS.update(EXT_BLOCKS)
except Exception as _ext_err:   # an extension import must never take the core composer down
    import sys as _sys
    print(f"[compose] extension blocks unavailable: {_ext_err}", file=_sys.stderr)

_FIT_SCRIPT = ("(function(){var W=1920;function fit(){"
  "Array.prototype.forEach.call(document.querySelectorAll('#root [data-fit]'),function(el){"
  "var raw=el.getAttribute('data-fit-w')||'',t;"
  "if(raw.slice(-3)==='cqw'){t=parseFloat(raw)/100*W;}else if(raw){t=parseFloat(raw);}"
  "else{t=el.parentElement?el.parentElement.clientWidth:W;}"
  "var sw=el.scrollWidth;"
  "if(t>0&&sw>t+0.5){el.style.transformOrigin=el.getAttribute('data-fit-origin')||'left top';"
  "el.style.transform='scale('+(t/sw)+')';}"
  "});}"
  "try{fit();}catch(e){}"
  "if(document.fonts&&document.fonts.ready){document.fonts.ready.then(fit);}"
  "})();")
# ^ THEME-FIT: font-robust layout. Any [data-fit] element is scaled (transform, seek-safe: set once
# on fonts.ready, not per-frame) so its content fits `data-fit-w` (a length, default parent width) —
# neutralises the one real theme risk: a wider theme font overflowing a fixed box. See the
# `themed-composer` bridge + kb/theme-style-pipelines.md.


_POLARITY = "light"                      # per-frame theme polarity; set by compose_frame (single-process, sequential)
_POLARITY_CACHE = {}

def _theme_polarity(theme):
    """'light' | 'dark' from the theme's --surface luminance — the composer's one polarity signal, so a
    block can keep a DRAMATIC dark stage on dark themes yet fall back to the theme surface on light ones.
    A hardcoded dark backdrop on a light theme (carousel, comparison) was the aeneid's polarity clash."""
    theme = str(theme)
    if theme in _POLARITY_CACHE:
        return _POLARITY_CACHE[theme]
    pol = "light"
    try:
        root = Path(__file__).resolve().parents[3] / "themes"
        p = root / theme / "tokens.css"
        if not p.exists():
            p = root / "highlighter-editorial" / "tokens.css"
        m = re.search(r"--surface\s*:\s*#([0-9a-fA-F]{3,6})", p.read_text(encoding="utf-8"))
        if m:
            h = m.group(1)
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            if len(h) == 6:
                r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
                def _ch(c): return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                lum = 0.2126 * _ch(r) + 0.7152 * _ch(g) + 0.0722 * _ch(b)
                pol = "dark" if lum < 0.4 else "light"
    except Exception:
        pol = "light"
    _POLARITY_CACHE[theme] = pol
    return pol


_SHELL_TEXTSAFE = True                   # per-frame: is --shell the same polarity as --surface (i.e. is
_SHELL_TEXTSAFE_CACHE = {}               # --text legible on it)? set by compose_frame alongside _POLARITY.

def _theme_shell_textsafe(theme):
    """True iff --shell shares --surface's light/dark polarity — i.e. --text (tuned to --surface, the
    composer's polarity signal) is legible on --shell. A full-bleed statement ground prefers --shell (the
    canvas) so a theme keeps its canvas colour (blue-professional: cream --shell), but the INVERTED-CARD
    themes (electric-studio/bauhaus-bold: dark --shell + light --surface, light content on dark frame) fail
    this — for them the statement must stay on --surface or the phrase goes dark-on-dark. Same formula as
    _theme_polarity; both cached, single-process."""
    theme = str(theme)
    if theme in _SHELL_TEXTSAFE_CACHE:
        return _SHELL_TEXTSAFE_CACHE[theme]
    def _lum(hexstr):
        h = hexstr
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            return None
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        def _ch(c): return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * _ch(r) + 0.7152 * _ch(g) + 0.0722 * _ch(b)
    safe = True
    try:
        root = Path(__file__).resolve().parents[3] / "themes"
        p = root / theme / "tokens.css"
        if not p.exists():
            p = root / "highlighter-editorial" / "tokens.css"
        css = p.read_text(encoding="utf-8")
        ms = re.search(r"--shell\s*:\s*#([0-9a-fA-F]{3,6})", css)
        mf = re.search(r"--surface\s*:\s*#([0-9a-fA-F]{3,6})", css)
        if ms and mf:
            ls, lf = _lum(ms.group(1)), _lum(mf.group(1))
            if ls is not None and lf is not None:
                safe = (ls < 0.4) == (lf < 0.4)   # same polarity → text legible on shell
    except Exception:
        safe = True
    _SHELL_TEXTSAFE_CACHE[theme] = safe
    return safe


# ── Per-theme font loader (audit F3) ────────────────────────────────────────
# The composer used to @import a FIXED 4 families (Inter/Libre Franklin/Lora/UnifrakturMaguntia), so
# ~22/26 themes rendered their declared display type in a system FALLBACK. This loads each theme's ACTUAL
# primary families. css2 is strict — requesting a weight a family doesn't ship 400s the WHOLE request —
# so we emit ONE @import per family with the weights it ships; a bad one isolates to that font falling
# back, not all of them. Non-Google families (Fontshare Satoshi/Clash Display, commercial GT Sectra) are
# not emitted → they fall back per the theme's CSS stack (recorded in docs/ENGINE_AUDIT.md, tier B/D).
_GF_WEIGHTS = {
    "VT323": "400", "Press Start 2P": "400",
    "Inter": "400;500;600;700;800;900", "Libre Franklin": "400;600;700;800;900",
    "Lora": "400;500;600;700", "Manrope": "400;500;600;700;800",
    "Source Serif 4": "400;500;600;700", "Source Serif Pro": "400;600;700",
    "IBM Plex Sans": "400;500;600;700", "IBM Plex Mono": "400;500;600;700",
    "Fraunces": "400;500;600;700;900", "Space Grotesk": "400;500;600;700",
    "Patrick Hand": "400", "Playfair Display": "400;500;600;700;800;900",
    "Archivo Black": "400", "Archivo": "400;500;600;700;800;900",
    "Space Mono": "400;700", "Instrument Serif": "400",
    "Plus Jakarta Sans": "400;500;600;700;800", "Outfit": "400;500;600;700;800;900",
    "Syne": "400;500;600;700;800", "Cormorant": "400;500;600;700",
    "Cormorant Garamond": "400;500;600;700", "Work Sans": "400;500;600;700;800;900",
    "EB Garamond": "400;500;600;700;800", "JetBrains Mono": "400;500;600;700;800",
    "Caveat": "400;500;600;700", "UnifrakturMaguntia": "400",
    "DM Sans": "400;500;600;700", "Courier Prime": "400;700",
    "Noto Sans SC": "400;500;700;900", "Noto Serif SC": "400;500;700;900",
}
_FONT_SUBSTITUTE = {  # Adobe Source Han == Google Noto CJK
    "Source Han Sans SC": "Noto Sans SC", "Source Han Serif SC": "Noto Serif SC",
    "Noto Sans Mono CJK SC": "Noto Sans SC",
}
_BASE_FONTS = ("Lora", "Inter", "Libre Franklin")  # families the composer CSS hardcodes → always load


def _theme_font_families(theme):
    """Ordered-unique PRIMARY families the theme declares — the first family of each
    --font-{display-en,display-cn,body,mono}. Excludes --font-features (OpenType tags, not families)."""
    root = Path(__file__).resolve().parents[3] / "themes"
    p = root / str(theme) / "tokens.css"
    if not p.exists():
        p = root / "highlighter-editorial" / "tokens.css"
    fams = []
    try:
        css = p.read_text(encoding="utf-8")
    except Exception:
        return fams
    for m in re.finditer(r"--font-(?:display-en|display-cn|body|mono)\s*:\s*([^;]+);", css):
        first = re.split(r",", m.group(1))[0].strip().strip('"').strip("'")
        if first and not first.startswith("var(") and first not in fams:
            fams.append(first)
    return fams


def _theme_fonts(theme):
    """Google-Fonts @import block for the theme's declared families + the composer's base fonts, so a
    theme renders in its ACTUAL type instead of a fallback. Replaces the fixed FONTS constant."""
    want = _theme_font_families(theme)
    want += [f for f in _BASE_FONTS if f not in want]
    seen, out = set(), []
    for fam in want:
        fam = _FONT_SUBSTITUTE.get(fam, fam)
        if fam in seen or fam not in _GF_WEIGHTS:   # not on Google Fonts → falls back per the CSS stack
            continue
        seen.add(fam)
        out.append(f"@import url('https://fonts.googleapis.com/css2?family={fam.replace(' ', '+')}:wght@{_GF_WEIGHTS[fam]}&display=swap');")
    return "".join(out)


# ── Signature decoration (composition-DNA lever #3) ─────────────────────────
# A theme declares `decoration: [<device-id>,...]` in theme.json; each id must exist in
# themes/composition/decorations.json AND have a renderer here (honesty-tested). Renderers return a
# token-driven, absolutely-positioned, pointer-events:none fragment; _theme_decorations wraps them in a
# canvas-wide overlay so a theme's furniture (texture / brackets / frame / rail) is part of every scene.
def _decor_graph_paper(p):
    return ('<div style="position:absolute;inset:0;background-image:'
            'linear-gradient(var(--rule,rgba(120,120,120,0.5)) 1px,transparent 1px),'
            'linear-gradient(90deg,var(--rule,rgba(120,120,120,0.5)) 1px,transparent 1px);'
            'background-size:3.2cqw 3.2cqw;opacity:0.5"></div>')


def _decor_dot_grid(p):
    return ('<div style="position:absolute;inset:0;background-image:'
            'radial-gradient(var(--rule,rgba(120,120,120,0.5)) 1px,transparent 1.4px);'
            'background-size:2.4cqw 2.4cqw;opacity:0.45"></div>')


def _decor_scanlines(p):
    return ('<div style="position:absolute;inset:0;background:repeating-linear-gradient('
            '0deg,transparent 0,transparent 2px,rgba(0,0,0,0.20) 3px,transparent 3.2px);opacity:0.6"></div>')


def _decor_grain(p):
    svg = ("url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E"
           "%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E"
           "%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")")
    return (f'<div style="position:absolute;inset:0;background-image:{svg};background-size:180px 180px;'
            'opacity:0.10;mix-blend-mode:multiply"></div>')


def _decor_corner_brackets(p):
    b = 'position:absolute;width:5cqw;height:5cqw;border:0.32cqw solid var(--text)'
    return ("".join([
        f'<div style="{b};top:3cqw;left:3cqw;border-right:none;border-bottom:none"></div>',
        f'<div style="{b};top:3cqw;right:3cqw;border-left:none;border-bottom:none"></div>',
        f'<div style="{b};bottom:3cqw;left:3cqw;border-right:none;border-top:none"></div>',
        f'<div style="{b};bottom:3cqw;right:3cqw;border-left:none;border-top:none"></div>']))


def _decor_interior_frame(p):
    return '<div style="position:absolute;inset:3.5cqw;border:0.18cqw solid var(--text);opacity:0.8"></div>'


def _decor_rail_label(p):
    txt = esc(str(p.get("text", "SECTION")))
    return ('<div style="position:absolute;left:2.2cqw;top:0;bottom:0;display:flex;align-items:center">'
            '<span style="writing-mode:vertical-rl;transform:rotate(180deg);'
            'font:700 0.95cqw/1 var(--font-mono),ui-monospace,monospace;letter-spacing:.34em;'
            f'text-transform:uppercase;color:var(--text-2);opacity:0.75">{txt}</span></div>')


def _decor_background_ordinal(p):
    txt = esc(str(p.get("text", "01")))
    return (f'<div style="position:absolute;right:1cqw;bottom:-6cqh;font:800 44cqw/0.8 var(--font-display-en);'
            f'color:var(--text);opacity:0.055;letter-spacing:-0.03em">{txt}</div>')


def _decor_blob(p):
    b = 'position:absolute;background:var(--accent);'
    return (f'<div style="{b};width:34cqw;height:34cqw;top:-9cqh;right:-6cqw;opacity:0.14;'
            'border-radius:42% 58% 55% 45%/48% 42% 58% 52%"></div>'
            f'<div style="{b};width:22cqw;height:22cqw;bottom:-6cqh;left:-4cqw;opacity:0.10;'
            'border-radius:56% 44% 48% 52%/52% 56% 44% 48%"></div>')


def _decor_ribbon(p):
    r = 'position:absolute;left:-12cqw;right:-12cqw;height:5cqh;transform:rotate(-18deg)'
    return (f'<div style="{r};top:19cqh;background:var(--accent);opacity:0.16"></div>'
            f'<div style="{r};top:33cqh;background:var(--text);opacity:0.08"></div>'
            f'<div style="{r};top:47cqh;background:var(--accent);opacity:0.12"></div>')


def _decor_glow(p):
    return ('<div style="position:absolute;inset:0;background:radial-gradient(ellipse 50% 45% at 68% 28%,'
            'var(--accent),transparent 62%);opacity:0.18;mix-blend-mode:screen"></div>')


def _decor_seal(p):
    txt = esc(str(p.get("text", "Est. 2026")))
    return ('<div style="position:absolute;top:6cqh;right:5cqw;width:11cqw;height:11cqw;'
            'border:0.3cqw solid var(--accent);border-radius:50%;display:flex;align-items:center;'
            'justify-content:center;transform:rotate(-12deg);opacity:0.7">'
            '<span style="font:700 1.1cqw/1.15 var(--font-mono),ui-monospace,monospace;letter-spacing:.1em;'
            f'text-transform:uppercase;color:var(--accent);text-align:center;max-width:9cqw">{txt}</span></div>')


# ── new-device backlog (THEME_DECORATION_MAP.md) — exact devices the mapping wanted ────────────────
def _decor_compass_rings(p):
    """Concentric + dashed drafting arcs in a corner — cartesian/blueprint drafting furniture."""
    c = 'position:absolute;border-radius:50%;border:0.14cqw dashed var(--rule,rgba(120,120,120,0.5));'
    ln = 'position:absolute;background:var(--rule,rgba(120,120,120,0.5));opacity:0.4;'
    return (f'<div style="{c}width:40cqw;height:40cqw;left:-12cqw;bottom:-16cqh;opacity:0.55"></div>'
            f'<div style="{c}width:27cqw;height:27cqw;left:-5.5cqw;bottom:-9.5cqh;opacity:0.45"></div>'
            f'<div style="{c}width:15cqw;height:15cqw;left:0.5cqw;bottom:-3.5cqh;opacity:0.4"></div>'
            f'<div style="{ln}left:2.5cqw;bottom:4cqh;width:11cqw;height:0.1cqw"></div>'
            f'<div style="{ln}left:8cqw;bottom:-1.5cqh;width:0.1cqw;height:11cqw"></div>')

def _decor_pillar_panels(p):
    """Vertical accent side-panels + hairlines — bauhaus/bold-poster architecture."""
    b = 'position:absolute;top:0;bottom:0;width:6cqw;background:var(--accent);opacity:0.10;'
    r = 'position:absolute;top:0;bottom:0;width:0.28cqw;background:var(--accent);opacity:0.45;'
    return (f'<div style="{b}left:0"></div><div style="{b}right:0"></div>'
            f'<div style="{r}left:6cqw"></div><div style="{r}right:6cqw"></div>')

def _decor_letterpress(p):
    """A giant faint background word with a stacked 3D offset shadow (letterpress/poster)."""
    txt = esc(str(p.get("text", "BOLD")))
    shadow = ",".join(f'{0.16*i:.2f}cqw {0.16*i:.2f}cqw 0 var(--accent)' for i in range(1, 6))
    return (f'<div style="position:absolute;left:3cqw;bottom:-3cqh;font:900 25cqw/0.85 var(--font-display-en);'
            f'color:var(--shell);text-shadow:{shadow};opacity:0.17;letter-spacing:-0.04em;white-space:nowrap">{txt}</div>')

def _decor_scribbles(p):
    """Hand-drawn squiggles + a star (SVG strokes) — playful/classroom."""
    sq = ('<svg viewBox="0 0 44 12" style="position:absolute;{pos}width:12cqw;height:3.3cqw;opacity:0.6">'
          '<path d="M2 6 q4 -6 8 0 t8 0 t8 0 t8 0" fill="none" stroke="var(--accent)" stroke-width="1.4" stroke-linecap="round"/></svg>')
    star = ('<svg viewBox="0 0 24 24" style="position:absolute;{pos}width:3.2cqw;height:3.2cqw;opacity:0.75">'
            '<path d="M12 2 l2.4 6.5 6.9 .4 -5.3 4.5 1.8 6.7 -5.8 -3.8 -5.8 3.8 1.8 -6.7 -5.3 -4.5 6.9 -.4z" fill="var(--accent)"/></svg>')
    return (sq.format(pos='left:4cqw;top:8cqh;') + sq.format(pos='right:5cqw;bottom:9cqh;')
            + star.format(pos='right:7cqw;top:11cqh;'))

def _decor_tape(p):
    """Semi-transparent collage tape strips at two corners — zine/kraft scrapbook."""
    t = 'position:absolute;width:14cqw;height:3.2cqw;background:var(--accent);opacity:0.20;'
    return (f'<div style="{t}top:-0.8cqh;left:6cqw;transform:rotate(-8deg)"></div>'
            f'<div style="{t}bottom:-0.8cqh;right:7cqw;transform:rotate(6deg)"></div>')

def _decor_starfield(p):
    """Deterministic scattered pixel stars (small squares) — 8-bit/cyber field."""
    pts = [(8, 14, .5), (22, 40, .3), (15, 70, .4), (34, 22, .6), (48, 58, .3), (61, 12, .5),
           (72, 44, .35), (83, 30, .55), (90, 66, .3), (55, 80, .45), (40, 88, .35), (67, 74, .5),
           (27, 9, .4), (88, 9, .55), (12, 46, .3)]
    d = 'position:absolute;width:0.5cqw;height:0.5cqw;background:var(--accent);'
    return "".join(f'<div style="{d}left:{x}%;top:{y}%;opacity:{o}"></div>' for x, y, o in pts)

def _decor_os_chrome(p):
    """A retro window title-bar with traffic-light dots — OS/terminal chrome."""
    txt = esc(str(p.get("text", "README.TXT")))
    dots = "".join('<div style="width:0.9cqw;height:0.9cqw;border-radius:50%;background:var(--accent);opacity:0.7"></div>'
                   for _ in range(3))
    return ('<div style="position:absolute;top:0;left:0;right:0;height:3.4cqh;background:var(--surface-2);'
            'border-bottom:0.14cqw solid var(--rule,rgba(120,120,120,0.5));display:flex;align-items:center;'
            f'gap:0.7cqw;padding:0 1.4cqw;opacity:0.92">{dots}'
            f'<span style="margin-left:0.7cqw;font:700 0.82cqw/1 var(--font-mono),ui-monospace,monospace;'
            f'letter-spacing:.12em;color:var(--text-2)">{txt}</span></div>')

def _decor_rosette_seal(p):
    """An ornate concentric stamp (solid + dashed + inner rings) — kraft/sakura seal."""
    txt = esc(str(p.get("text", "")))
    ring = 'position:absolute;border-radius:50%;'
    inner = (f'<span style="font:700 0.9cqw/1.1 var(--font-mono),ui-monospace,monospace;letter-spacing:.1em;'
             f'text-transform:uppercase;color:var(--accent);text-align:center;max-width:7.5cqw">{txt}</span>') if txt else ""
    return ('<div style="position:absolute;top:6cqh;right:5cqw;width:11cqw;height:11cqw;display:flex;'
            'align-items:center;justify-content:center;transform:rotate(-8deg);opacity:0.7">'
            f'<div style="{ring}inset:0;border:0.3cqw solid var(--accent)"></div>'
            f'<div style="{ring}inset:1cqw;border:0.14cqw dashed var(--accent)"></div>'
            f'<div style="{ring}inset:2cqw;border:0.14cqw solid var(--accent)"></div>{inner}</div>')

def _decor_double_rule(p):
    """A top + bottom pair of hairlines (a word bracketed by two rules) — editorial ornament."""
    r = 'position:absolute;left:8cqw;right:8cqw;height:0.14cqw;background:var(--text);opacity:0.5;'
    return (f'<div style="{r}top:6.5cqh"></div><div style="{r}top:7.7cqh"></div>'
            f'<div style="{r}bottom:6.5cqh"></div><div style="{r}bottom:7.7cqh"></div>')

def _decor_hatch(p):
    """45deg diagonal line texture — coral/split-canvas panel fill."""
    return ('<div style="position:absolute;inset:0;background:repeating-linear-gradient(45deg,'
            'var(--accent) 0,var(--accent) 0.4cqw,transparent 0.4cqw,transparent 2.4cqw);opacity:0.10"></div>')

def _decor_pixel_brackets(p):
    """Blocky stepped corner brackets (filled L's) — pixel-native marks."""
    px = 'position:absolute;background:var(--accent);opacity:0.85;'
    parts = []
    for vy, vx in (("top:3cqw", "left:3cqw"), ("top:3cqw", "right:3cqw"),
                   ("bottom:3cqw", "left:3cqw"), ("bottom:3cqw", "right:3cqw")):
        parts.append(f'<div style="{px}width:4cqw;height:1.1cqw;{vy};{vx}"></div>')
        parts.append(f'<div style="{px}width:1.1cqw;height:4cqw;{vy};{vx}"></div>')
    return "".join(parts)

def _decor_drop_cap(p):
    """An oversized decorative initial in the upper-left — zine/soft-editorial."""
    txt = esc(str(p.get("text", "A"))[:1])
    return (f'<div style="position:absolute;left:4cqw;top:7cqh;font:900 22cqw/0.78 var(--font-display-en);'
            f'font-style:var(--display-style,normal);color:var(--accent);opacity:0.16">{txt}</div>')

def _decor_window_bevel(p):
    """A raised 3D window bevel frame (Win9x): a light top/left + dark bottom/right double border, inset
    slightly, so the whole scene reads as a raised OS panel. Neutral highlight/shadow (a bevel is light+dark,
    not the accent) — pairs with os-chrome for the retro-windows look."""
    return ('<div style="position:absolute;inset:1.8cqw;pointer-events:none;'
            'border-top:0.3cqw solid #ffffff;border-left:0.3cqw solid #ffffff;'
            'border-right:0.3cqw solid #000000;border-bottom:0.3cqw solid #000000">'
            '<div style="position:absolute;inset:0;'
            'border-top:0.16cqw solid #dfdfdf;border-left:0.16cqw solid #dfdfdf;'
            'border-right:0.16cqw solid #808080;border-bottom:0.16cqw solid #808080"></div></div>')


_DECOR_RENDERERS = {
    "graph-paper": _decor_graph_paper, "dot-grid": _decor_dot_grid, "scanlines": _decor_scanlines,
    "grain": _decor_grain, "corner-brackets": _decor_corner_brackets,
    "interior-frame": _decor_interior_frame, "rail-label": _decor_rail_label,
    "background-ordinal": _decor_background_ordinal, "blob": _decor_blob, "ribbon": _decor_ribbon,
    "glow": _decor_glow, "seal": _decor_seal,
    # new-device backlog
    "compass-rings": _decor_compass_rings, "pillar-panels": _decor_pillar_panels,
    "letterpress": _decor_letterpress, "scribbles": _decor_scribbles, "tape": _decor_tape,
    "starfield": _decor_starfield, "os-chrome": _decor_os_chrome, "rosette-seal": _decor_rosette_seal,
    "double-rule": _decor_double_rule, "hatch": _decor_hatch, "pixel-brackets": _decor_pixel_brackets,
    "drop-cap": _decor_drop_cap, "window-bevel": _decor_window_bevel,
}


def _theme_decorations(theme):
    """Canvas-wide decoration overlay from the theme's declared `decoration` devices (theme.json), each
    rendered in the theme's own tokens. Empty string when a theme declares none."""
    root = Path(__file__).resolve().parents[3] / "themes"
    try:
        meta = json.loads((root / str(theme) / "theme.json").read_text(encoding="utf-8"))
    except Exception:
        return ""
    parts = []
    for d in (meta.get("decoration") or []):
        did = d if isinstance(d, str) else d.get("id")
        fn = _DECOR_RENDERERS.get(did)
        if fn:
            parts.append(fn(d if isinstance(d, dict) else {}))
    if not parts:
        return ""
    # track 12 = above content/props but < 14 (the renderer reassigns ≥14); a canvas-wide, always-on
    # furniture layer (the theme's constant identity across every scene in the frame).
    return ('<div class="decor clip" data-start="0" data-duration="1000000" data-track-index="12" '
            'style="position:absolute;inset:0;pointer-events:none;overflow:hidden">' + "".join(parts) + '</div>')


_TYPE_ROLES_CACHE = {}
_TYPE_ROLES_REGISTRY = None

def _load_type_roles():
    global _TYPE_ROLES_REGISTRY
    if _TYPE_ROLES_REGISTRY is None:
        try:
            p = Path(__file__).resolve().parents[3] / "themes" / "composition" / "type_roles.json"
            _TYPE_ROLES_REGISTRY = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _TYPE_ROLES_REGISTRY = {"slots": {}, "personalities": {}}
    return _TYPE_ROLES_REGISTRY

def _theme_type_roles(theme):
    """Emit a theme's Layer-1 type-role vars from its `typePersonality` recipe (themes/composition/
    type_roles.json). The recipe assigns each role (eyebrow/hero-num/display/stat-label/caption) a FONT
    SLOT (display|body|mono) + weight/size/tracking/etc.; the slot resolves against THIS theme's own font
    vars, so same-personality themes still differ by typeface. Each recipe property maps 1:1 to the var the
    block consumes (`--{role}-{prop}`, e.g. hero-num.track -> --hero-num-track). Emitted BEFORE _theme_vars
    so a theme's own tokens.css still overrides (the two ported exemplars keep their hand-tuned values).
    A theme with no/unknown personality emits nothing -> blocks fall back to their hardcoded defaults."""
    theme = str(theme)
    if theme in _TYPE_ROLES_CACHE:
        return _TYPE_ROLES_CACHE[theme]
    css = ""
    try:
        root = Path(__file__).resolve().parents[3] / "themes"
        tj = root / theme / "theme.json"
        pid = json.loads(tj.read_text(encoding="utf-8")).get("typePersonality") if tj.exists() else None
        reg = _load_type_roles()
        recipe = (reg.get("personalities") or {}).get(pid)
        if recipe:
            slots = reg.get("slots") or {}
            decls = []
            for role, props in recipe.items():
                if role == "desc" or not isinstance(props, dict):
                    continue
                for prop, val in props.items():
                    resolved = slots.get(val, val) if prop == "font" else val
                    decls.append(f"--{role}-{prop}: {resolved}")
            css = ("#root{" + ";".join(decls) + ";}") if decls else ""
    except Exception:
        css = ""
    _TYPE_ROLES_CACHE[theme] = css
    return css


def _theme_vars(theme):
    """Inject a NOLAN theme's tokens.css as scoped CSS custom properties on #root so the block CSS
    (which references var(--accent) etc.) resolves. Falls back to the Vox 'highlighter-editorial'
    house theme. This is the seam that makes the composer theme-driven instead of Vox-hardcoded."""
    root = Path(__file__).resolve().parents[3] / "themes"
    p = root / str(theme) / "tokens.css"
    if not p.exists():
        p = root / "highlighter-editorial" / "tokens.css"
    try:
        css = p.read_text(encoding="utf-8")
    except Exception:
        return ""
    # Extract each `--name: value` custom property. A value can legally contain `;` inside a quoted
    # string or url() (e.g. a `data:image/svg+xml;utf8,<svg…>` pattern), so terminate on a `;`/`{`/`}`
    # only at paren-depth 0 and OUTSIDE any quote — a naive `[^;{}]+` truncates the data-URI mid-string
    # and leaves an unclosed `url("` that swallows the rest of the CSS.
    decls, last = [], 0
    for m in re.finditer(r"(--[\w-]+)\s*:", css):
        if m.start() < last:
            continue                                   # inside a value we already consumed
        name, j, depth, quote, buf = m.group(1), m.end(), 0, "", []
        while j < len(css):
            c = css[j]
            if quote:
                buf.append(c)
                if c == quote:
                    quote = ""
            elif c in "\"'":
                quote = c; buf.append(c)
            elif c == "(":
                depth += 1; buf.append(c)
            elif c == ")":
                depth = max(0, depth - 1); buf.append(c)
            elif depth == 0 and c in ";{}":
                break
            else:
                buf.append(c)
            j += 1
        last = j
        val = "".join(buf).strip()
        if val:
            decls.append(f"{name}: {val}")
    return ("#root{" + ";".join(decls) + ";}") if decls else ""


# ---------------------------------------------------------------------------------------------
# SCENE-TRANSITION PRIMITIVE (the "CSS transitions" deferred track — HF cover/push/scale/dissolve
# family). NOT a block: a SEAM operator between two consecutive scenes in a frame. Authored as an
# optional `transition_out` on the DEPARTING scene: {kind, dur?, color?}. It is an OUTGOING effect
# over an overlap window [b, b+T] after the scene boundary b — the departing scene animates away
# (fade / slide / scale) on TOP while the next scene does its own normal block entrance UNDERNEATH.
# This composes without touching any block's internal choreography, and is SEEK-SAFE (transform/
# opacity only — literal CSS `transition:`/@keyframes are banned by the runtime, so it's GSAP).
# Registry-driven like REVEALS: keys MUST equal catalog['transitions'] (check_catalog.py enforces).

def _tr_crossfade(w, b, T, o):
    return [f'tl.to("#{w}",{{opacity:0,duration:{T},ease:"power1.inOut"}},{b});'], []


def _tr_slide_left(w, b, T, o):
    return [f'tl.to("#{w}",{{xPercent:-100,duration:{T},ease:"power2.inOut"}},{b});'], []


def _tr_slide_right(w, b, T, o):
    return [f'tl.to("#{w}",{{xPercent:100,duration:{T},ease:"power2.inOut"}},{b});'], []


def _tr_slide_up(w, b, T, o):
    return [f'tl.to("#{w}",{{yPercent:-100,duration:{T},ease:"power2.inOut"}},{b});'], []


def _tr_scale_out(w, b, T, o):
    return [f'tl.to("#{w}",{{scale:1.18,opacity:0,duration:{T},ease:"power2.in"}},{b});'], []


def _tr_fade_through(w, b, T, o):
    """Dip-to-colour (default black): departing scene fades to the colour, the colour clears to
    reveal the next scene. A separate full-frame overlay clip above everything does the dip."""
    color = o.get("color", "#000")
    pid, half = f"{w}-ft", T / 2.0
    overlay = [f'<div id="{pid}" class="clip" data-start="{b:g}" data-duration="{T:g}" data-track-index="9" '
               f'style="position:absolute;inset:0;background:{esc(color)};opacity:0;z-index:400;"></div>']
    return ([f'tl.to("#{w}",{{opacity:0,duration:{half:g},ease:"power1.in"}},{b:g});',
             f'tl.to("#{pid}",{{opacity:1,duration:{half:g},ease:"power1.in"}},{b:g});',
             f'tl.to("#{pid}",{{opacity:0,duration:{half:g},ease:"power1.out"}},{b + half:g});'], overlay)


TRANSITIONS = {
    "crossfade":    {"fn": _tr_crossfade,    "desc": "departing scene dissolves to reveal the next (HF dissolve)"},
    "slide_left":   {"fn": _tr_slide_left,   "desc": "departing scene slides off to the left, uncovering the next (cover/push)"},
    "slide_right":  {"fn": _tr_slide_right,  "desc": "departing scene slides off to the right, uncovering the next"},
    "slide_up":     {"fn": _tr_slide_up,     "desc": "departing scene slides up out of frame, uncovering the next"},
    "scale_out":    {"fn": _tr_scale_out,    "desc": "departing scene zooms up + fades (scale dissolve)"},
    "fade_through": {"fn": _tr_fade_through, "desc": "dip through a colour (default black) between scenes; data.color overrides"},
}


def _extend_clip_dur(frag, scene_end, extra, eps=0.05):
    """Bump the data-duration of any .clip in `frag` that ENDS at the scene boundary, so the
    departing scene stays mounted through the [b, b+T] transition overlap instead of hard-cutting."""
    def repl(m):
        s, d = float(m.group(1)), float(m.group(2))
        if abs(s + d - scene_end) <= eps:
            return f'data-start="{m.group(1)}" data-duration="{d + extra:g}"'
        return m.group(0)
    return re.sub(r'data-start="([\d.]+)"\s+data-duration="([\d.]+)"', repl, frag)


def _scene_archetype(sc):
    """The scene's composition archetype: an explicit meta.archetype, else derived from its block type
    (nolan.composition registry — the ONE source). None for the archetype-agnostic `raw` escape hatch."""
    arch = (sc.get("meta") or {}).get("archetype")
    if arch:
        return arch
    try:
        from nolan.composition import block_archetype
        return block_archetype(sc.get("type", ""))
    except Exception:
        return None


def _stamp_archetype(frags, arch):
    """Stamp `data-archetype` on the scene's CONTENT root (its track-2 element) so a composed frame
    carries its archetype as a first-class DOM fact — the real consumer is the layout linter (reads it
    to run anchor-drift on composed frames without a spec sidecar) + it's inspectable. Additive +
    idempotent: no-op when arch is falsy, lands exactly once on the track-2 element."""
    if not arch:
        return frags
    out, done = [], False
    for fr in frags:
        if not done and 'data-track-index="2"' in fr and "data-archetype=" not in fr:
            fr = fr.replace('data-track-index="2"', f'data-archetype="{arch}" data-track-index="2"', 1)
            done = True
        out.append(fr)
    return out


def compose_frame(frame_id, dur, scenes, theme="highlighter-editorial"):
    global _POLARITY, _SHELL_TEXTSAFE
    _POLARITY = _theme_polarity(theme)        # so blocks can pick theme-aware (not hardcoded-dark) defaults
    _SHELL_TEXTSAFE = _theme_shell_textsafe(theme)   # full-bleed grounds prefer --shell unless it's dark-on-dark
    body, tl = [], []
    # Scene transitions (optional): if ANY scene carries a `transition_out`, wrap every scene in a
    # z-ordered wrapper (earlier scene ON TOP, so a departing scene's exit uncovers the next
    # underneath) and apply the seam operator on the departing wrapper. No transitions -> emit
    # byte-identical to before (no wrappers), so existing frames are unaffected.
    has_trans = any((sc.get("transition_out") or {}).get("kind") in TRANSITIONS for sc in scenes)
    for i, sc in enumerate(scenes):
        sc = {**sc, "id": _safe_sid(sc["id"])}   # digit-first ids break #selectors
        f, t = BLOCKS[sc["type"]](sc["id"], sc)
        f = _stamp_archetype(f, _scene_archetype(sc))   # archetype-bias hook: DOM fact read by the layout linter
        if has_trans:
            sid = sc["id"]
            trans = sc.get("transition_out") or {}
            if trans.get("kind") in TRANSITIONS:
                T = float(trans.get("dur", 0.5))
                b = float(sc["start"]) + float(sc["dur"])
                f = [_extend_clip_dur(frag, b, T) for frag in f]   # keep departing scene mounted through overlap
                lines, overlay = TRANSITIONS[trans["kind"]]["fn"](f"{sid}-tw", b, T, trans)
                t = t + lines
                body += overlay
            body.append(f'<div id="{sid}-tw" class="scenewrap" style="position:absolute;inset:0;z-index:{100 - i};">')
            body += f
            body.append('</div>')
        else:
            body += f
        tl += t
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
  <style>{_theme_fonts(theme)}{_theme_type_roles(theme)}{_theme_vars(theme)}{CSS}</style>
  <div id="root" data-composition-id="{frame_id}" data-width="1920" data-height="1080">
    {chr(10).join('    '+b for b in body)}
    {_theme_decorations(theme)}
  </div>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
{libs}  <script>{_FIT_SCRIPT}</script>
  <script>
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
