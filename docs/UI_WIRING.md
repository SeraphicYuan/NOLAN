# UI Wiring Manifest

Audit of every interactive control across the hub pages: what it writes, who
consumes it. The rule (CLAUDE.md): *a control that can't name its field and
consumer gets removed.* Full audit 2026-07-05; re-audit when pages change.

## Verdict summary

- **BROKEN: 0** — every fetch resolves to a live route; no legacy-prefix
  (`/library/api/…`) survivors after the canonical-URL migration.
- **DEAD (writes nothing anyone reads): 0**
- **WIRED: everything else** — with three *advisory dead-ends* (below).

## Advisory dead-ends (produced + viewable, but consumed by no pipeline step)

1. **clips.html "Analyze effect"** → `effect_analysis.md` — *RESOLVED
   2026-07-05*: analysis is now stage 1 of the **effect promotion pipeline**
   (proposal → gate → accept → motion registry). See `nolan/effect_promotion.py`.
2. **video_styles.html "Analyze"** → `video_styles/<id>/video_style_guide.md`
   — read only by the page itself; the Director's per-project style_guide.md
   is a different artifact. STATUS: *advisory/reference by design for now*;
   candidate: feed it into match_and_adapt_style as a style-template source.
3. **broll.html (the lab as a whole)** — evoke picks / split-screen /
   count-up / motion previews render to the page with **no persistence
   control**; results are throwaway. (Scene-scoped super-search on /scenes
   DOES attach.) Candidate: a "save pick → shortlist / scene" control.

## Page-by-page (controls that write; display/filter/nav excluded)

| Page | Control | Writes | Consumed by |
|---|---|---|---|
| clips | Save clip / Delete | saved_clips table | Clips list, shortlist, materialize |
| clips | Materialize file/frames | projects/_clips/<id>/ | previews, analyze-effect |
| clips | Analyze effect | effect_task.md + agent → effect_analysis.md + proposal/ | promotion pipeline (gate/accept) |
| clips | Gate / Accept (promotion) | gate_report.json / promoted comp + registry_custom.json | motion registry → specs |
| library | Save clip (cut) | saved_clips | Clips page |
| library | ± project chip | project associations | scoped search/matching |
| library | Embed / reconcile | vector index | semantic search, clip matcher |
| images | Add / Cutout / Promote / Reject | imagelib assets/status | engine library tier, art sourcing |
| extract | Extract & download | .scratch/extracted + imagelib ingest | picture library |
| ingest | Index video | library DB segments/transcripts | search, matching, deconstruct |
| deconstruct | Run / Export template / Clone / Send plan | recovered_plan, scene-plan templates, beatmaps, scene_plan.json | template_match, script projects, Director |
| script_projects | (all) | project manifest, sources, drafts, script.md | writer agents, Director |
| script_styles | (all) | corpus + style_guide.md | script writers (/process, projects) |
| video_styles | Create/Add/Pair | style manifest | (pairing stored; guide advisory — see above) |
| publish | Publish article | _published/<slug>/article | /publish viewer |
| lottie / comfyui / showcase | render/register/sample | previews; workflow registry | generation (workflows); previews ephemeral |
| settings | Save | nolan.yaml | load_config() everywhere |
| process | Generate project | project (script + plan) | the whole pipeline |
| scenes / studio / voices / agents / map | (rebuilt 2026-07-05 with consequence labels / step inspector / introspection) | see their commits | — |
