---
name: nolan-scene-edit
description: Rework ONE scene in a NOLAN scene_plan.json from a human note — route it to the right NOLAN capability (motion python/remotion, ComfyUI gen, library b-roll search, or layout_spec), apply the change, validate, and re-render only that scene. Use when asked to edit / rework / redo / regenerate / "use Remotion for" / "recreate this effect on" a specific scene. This is the agent (Claude Code) path for the /scenes iteration UI — for edits a plain LLM can't route correctly.
id: scene-edit
kind: contract
purpose: Route a single-scene edit to the right NOLAN capability, apply, validate, re-render only that scene.
status: active
version: 1
handoffs:
  - { process: scene-edit, stage: beat-edit, gate: B }
loaded_by: [src/nolan/fleet.py]
evals: []
---

# NOLAN scene edit (agent path)

You are reworking **one scene** of a NOLAN `scene_plan.json` to satisfy a human note,
using NOLAN's *actual* capabilities (not guesswork). A plain LLM can rewrite text fields
but can't reliably route to Remotion, recreate an effect, or validate a render — that's
why this runs as a Claude Code agent. Change **only the target scene**; re-render **only**
that scene; leave the rest of the plan untouched.

## Fleet mode (when dispatched from the /scenes dashboard)
If the task names a fleet agent id (e.g. "You are fleet agent 'nolan4'"), report your
status so the dashboard can track you. Use the shared helper (the hub reads the same file):

```bash
# at START — before any work:
/mnt/d/env/nolan/python.exe -X utf8 -c "from nolan.fleet import write_status; write_status('nolan4', state='working', message='starting', scene_ids=['b6b_title'])"
# on PROGRESS — short human-readable steps:
/mnt/d/env/nolan/python.exe -X utf8 -c "from nolan.fleet import write_status; write_status('nolan4', message='compiled remotion spec, re-rendering')"
# at END — done (with a result list) or error:
/mnt/d/env/nolan/python.exe -X utf8 -c "from nolan.fleet import write_status; write_status('nolan4', state='done', message='b6b -> motion:kinetic-text', result=[{'id':'b6b_title','resolved_source':'motion:kinetic-text','ok':True}])"
# on failure: write_status('nolan4', state='error', message='...', error='what went wrong')
```
Rules: write `working` first; if given **multiple scenes, do them one by one** and update
`message` between each; always finish with `done` or `error`. Keep going to the next scene
even if one fails (record it in `result` with `ok:false`).

## Environment (this project)
- Python: `/mnt/d/env/nolan/python.exe -X utf8` (Windows conda env `nolan`; NOT system python).
- **Run everything from the repo root** `D:\ClaudeProjects\NOLAN` — `segment_meta.json` and the
  index store repo-root-relative paths; a wrong cwd silently degrades to a card.
- Remotion effects need the render-service on `http://127.0.0.1:3010` (started with Windows node).
- ComfyUI (for generated scenes) is on `127.0.0.1:8080` (reachable from the Windows side).

## 1. Orient
Find the plan and read the target scene. The plan is `projects/<name>/scene_plan.json`
(linear/orchestrator) or `.../<segment>/scene_plan.json` (asset-first/segment).

```bash
# pipeline: "segment" (asset-first) or "orchestrator" (linear) — they edit/render differently
/mnt/d/env/nolan/python.exe -X utf8 -c "from nolan.iterate import detect_pipeline; print(detect_pipeline('<PLAN>'))"
# dump the one scene you're editing
/mnt/d/env/nolan/python.exe -X utf8 -c "import json;print(json.dumps([s for sec in json.load(open(r'<PLAN>',encoding='utf-8'))['sections'].values() for s in sec if s['id']=='<SCENE_ID>'][0],indent=2,default=str))"
```

Note the scene's `visual_type`, current `resolved_source`, and which asset field is populated
(`motion_spec` / `matched_clip` / `comfyui_prompt` / `layout_spec` / `rendered_clip`).

## 2. Classify the note → pick the capability

| The note wants… | Mechanism | Fields you set on the scene | Backend |
|---|---|---|---|
| An animated graphic / kinetic text / chart / annotation / premium card | **motion_spec** | `motion_spec` (validated dict), usually `visual_type:"graphic"` | python *or* remotion |
| "use Remotion" / a richer composition (kinetic, bar-compare, k-shape, annotate, route-map, premium-card) | **motion_spec (remotion)** | `motion_spec` with a remotion-backed effect | remotion |
| A photoreal / illustrative still (AI image) | **ComfyUI gen** | `visual_type:"generated-image"`, `comfyui_prompt` | — |
| Real archival/library footage | **segment search** | `visual_type:"b-roll"`, `search_query` | — |
| A static text card (orchestrator templates: quote/list/counter/…) | **layout_spec** | `layout_spec:{template,params}` | — |
| Just reword/retune existing copy or prompt | **direct field edit** | `comfyui_prompt` / `narration_excerpt` / `search_query` | — |

Rules:
- Changing `search_query` or `visual_type` automatically re-runs asset selection on re-render.
- Editing any source field clears `rendered_clip` so the re-render rebuilds it.
- `layout_spec` exists only on orchestrator plans; ComfyUI gen + segment search assume a segment plan (needs `segment_meta.json`).

## 3. Ground yourself with LIVE data — don't invent effect names or params
```bash
# the full motion guide (effects, every param, shared params, themes/anchors) — source of truth
/mnt/d/env/nolan/python.exe -X utf8 -c "from nolan.motion import build_guide; print(build_guide())"
# effects + backends at a glance
/mnt/d/env/nolan/python.exe -X utf8 -c "from nolan.motion import REGISTRY;[print(e.id, e.backend, e.category, '->', e.target) for e in REGISTRY]"
# orchestrator layout templates available
/mnt/d/env/nolan/python.exe -X utf8 -c "from nolan.orchestrator.render import _build_renderer_registry as r;print(sorted(r().keys()))"
# ComfyUI image models: flux-dev | z-image (z-image-turbo)
```
Remotion-backed effects: `kinetic-text, bar-compare, k-shape, annotate-video, annotate-stat,
route-map, premium-card`. Python-backed: `counter, title, lower-third, comparison, line-chart,
loop-diagram`. `executor.render` dispatches on `spec["backend"]`.

## 4. Produce the change

### Motion (python OR remotion) — preferred for graphics/annotations
Write a precise natural-language brief, **compile it** (grounded + self-repairing), and
**validate** before applying. Compiling beats hand-writing a spec.
```bash
/mnt/d/env/nolan/python.exe -X utf8 - <<'PY'
import asyncio, json
from nolan.config import load_config
from nolan.llm import create_text_llm
from nolan.motion import compile_spec, validate
brief = "premium card: pull-quote '...'; accent amber; centered"   # be specific: what/where/accent/timing
spec, errors = asyncio.run(compile_spec(brief, create_text_llm(load_config())))
print("ERRORS:", errors); print(json.dumps(spec, indent=2))
PY
```
- To force Remotion, write a brief that names a remotion effect (e.g. "kinetic text…", "premium card…",
  "bar comparison…") — the compiled spec will have `backend:"remotion"`. Confirm `spec["backend"]`.
- If `errors` is non-empty, fix the brief and recompile; never apply an invalid spec.
- You can also hand-author a spec and just `validate(spec)` — but match the registry param names exactly.

### ComfyUI generated still
Set `visual_type:"generated-image"` + a strong `comfyui_prompt`. Choose the model at re-render
time (`--comfyui-model z-image` or `flux-dev`).

### Library b-roll
Set `visual_type:"b-roll"` + a `search_query` of plain visual keywords. Re-render re-resolves it
to a real clip (needs the project's `index_db` in `segment_meta.json`).

### layout_spec (orchestrator only)
Set `layout_spec:{ "template": "<one of the registry templates>", "params": {…} }`.

## 5. Apply the edit to the plan
Use the iteration engine so dirty-tracking + whitelist are handled. Two ways:
```bash
# direct field set (values parsed as JSON, else string). Good for motion_spec/comfyui_prompt/etc.
/mnt/d/env/nolan/python.exe -X utf8 -m nolan revise-scene "<PLAN>" <SCENE_ID> --set 'visual_type=graphic' --set 'motion_spec=<JSON>'
```
or programmatically when the patch is large:
```bash
/mnt/d/env/nolan/python.exe -X utf8 - <<'PY'
import asyncio
from nolan.iterate import apply_edit
asyncio.run(apply_edit(r"<PLAN>", "<SCENE_ID>", patch={"visual_type":"graphic","motion_spec":{...}}))
PY
```
`apply_edit` clears `rendered_clip` (and clears the cached match if you changed `search_query`/`visual_type`).

## 6. Re-render ONLY this scene, then verify
```bash
# from repo root. add --comfyui-model z-image for generated scenes.
/mnt/d/env/nolan/python.exe -X utf8 -m nolan rerender "<PLAN>" --scenes <SCENE_ID>
```
The CLI prints each re-rendered scene's `resolved_source` and flags `⚠ fell back` — a fallback
means the intended mechanism failed (e.g. Remotion service down, search miss). Then verify:
- `resolved_source` matches the intended mechanism (e.g. `motion:premium-card`, `search(0.74)`, `generated`).
- the clip is real video: `ffprobe clips/<id>.mp4` → 1920x1080, expected duration.
- neighbor clips' mtimes are unchanged (only this scene re-rendered).

## Guardrails
- Edit and re-render **only** the named scene. Never touch other scenes or their clips.
- Preserve `layout_spec` on orchestrator scenes (operate on the raw plan; don't round-trip through
  the `Scene` dataclass, which drops it — `nolan revise-scene` / `iterate.apply_edit` are safe).
- Run from the repo root; use the project's Windows python.
- Don't apply an unvalidated motion spec. Don't switch a scene's creative intent unless the note asks.
- If a Remotion render falls back, check the render-service on 3010 before retrying — don't silently ship a card.
