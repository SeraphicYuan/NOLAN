# HyperFrames edit-loop program — detailed plan

## Status — ALL PHASES SHIPPED (2026-07-15, full suite 1245 passed / 3 skipped)
- **Phase 1** ✅ 8 hardening fixes + `tests/test_hf_edit_loop_hardening.py` (7 tests).
- **Phase 2** ✅ click-scene → seek/play range + playhead/active-follow/keys/loop/stale-badge; real browser
  test `render-service/hf_edit_seek.test.cjs` (puppeteer, 6 assertions).
- **Phase 3** ✅ drag-drop → pool + per-scene shortlist (`add_scene_asset`/`remove_scene_asset`, block-aware
  "use as ground"); `tests/test_hf_scene_assets.py` + a TestClient route test.
- **Phase 4** ✅ scene-level staging + agent `<select>` + PROPOSAL store (`propose_scene_edit`/`accept_proposal`/
  `reject_proposal`, gated draft → human accept → canonical, provenance stamped) + Proposals review panel;
  `tests/test_hf_proposals.py` + route tests; batch brief instructs the agent to propose.
- **KNOWN ISSUE surfaced (not caused by this work), NOT yet fixed:** comparison-VIDEO sides render a BLACK
  panel in the *incremental* render. Fix #4 correctly positions the injected root video at the scene window
  (verified: `data-start`=scene-global, clip present + moving) and freeze-heals it — but the incremental
  renderer does not DRAW a rect-positioned root `<video>` sitting behind a sub-comp hole (full-bleed grounds
  render fine). Follow-up: investigate the hyperframes render's drawing of behind-sub-comp root videos, or
  render comparison-video sides as image/Ken-Burns sides (which draw directly, no root injection).

Turn `/hyperframes` into a real **review → edit → re-render** loop, and harden the
compose-first render pipeline underneath it. Derived from the `the-openai-debate` cold-author run
(2026-07-15) which surfaced the render bugs, and a close read of the edit page
(`templates/hf_scenes.html`, `webui/routes/hf_scenes.py`, `hyperframes/edit.py`, `hyperframes/batch.py`).

## Two settled decisions
- **Agent/batch edits are PROPOSALS, not direct mutations.** Agent does the work → lands a gated draft
  → human accepts per scene → canonical. Mechanical inspector edits stay direct. (CLAUDE.md agent contract:
  draft → validate → accept; no side-doors into canonical artifacts + provenance stamped.)
- **Drag-drop = shortlist (always) + block-aware "use as ground" (optional shortcut).** The shortlist is
  the scene's candidate bin (works for every block, zero data loss); set-as is the fast common-case place.

## Sequence (correctness first, then the loop)
1. **Phase 1 — #2 pipeline hardening + #1 caption default** (no UI; makes every render trustworthy)
2. **Phase 2 — #3 click-scene → seek + play** (small, front-end only; makes the page usable for review)
3. **Phase 3 — #5 drag-drop → pool + per-scene shortlist** (the input side of the loop)
4. **Phase 4 — #4 scene-level batch comments → proposals → selectable agent** (the biggest; has the proposal store)

---

## Phase 1 — Render/pipeline hardening (#2) + caption default (#1)

Move this run's ad-hoc fixes into the pipeline; each gets a test (docs claim, tests enforce).

| # | Fix | Where | Test |
|---|-----|-------|------|
| 1 | `ensure_storyboard` wrote a stringified dict as `src:` | ✅ done — `edit.py` extracts `fr["id"]` | cold `ensure_storyboard` → every `src:` resolves to a file |
| 2 | Last-frame render dies in audio-assemble (`audioPadTrim … audio.aac`) | `incremental.render_one`: on non-zero render **or** missing clip, auto-fallback to **video-only render + mux the section wav** (48kHz stereo). Any frame self-heals. | frame whose window ends at timeline end → clip has full-length audio |
| 3 | Concat silently DROPS a clip's audio on param mismatch | (a) render_one fallback muxes to the render's native params so all clips are uniform; (b) `concat_clips` asserts `audio_dur ≈ video_dur` post-concat, re-normalizes on mismatch | concat clips w/ 24k-mono + 48k-stereo → audio spans full duration |
| 4 | Comparison video SIDES never freeze-healed (only `ground:{kind:video}`) | Unify: run `heal_video_freezes` over comparison mounts too (in `assemble_media`, before `inject_comparison_videos`, using each mount's on-screen window) | comparison side shorter than its window → `.filled` produced + used |
| 5 | `.clip.mp4` (incremental) vs `.preview.mp4` (edit page) naming split | `list_frames.preview_mp4` + `/api/hf/frame-video` accept **either**, prefer newest. Incremental render becomes visible on the edit page with no copy step. | comp with only `.clip.mp4` → `preview_mp4=True`, route serves it |
| 6 | `renders/video.mp4` (finish) vs `renders/<comp>.mp4` (hub serves) | finish writes `renders/<comp>.mp4` (or route checks both) — one name | after finish, `/api/hf/video` finds the file |
| 7 | #1: caption burn is a 20-min un-chunked render, discarded (opaque webm) on this host | `finish` calls `render_incremental(captions=False)` by default; add `--burn-captions` opt-in. Reimplement burn later as **chunked/per-frame** or **ffmpeg ASS burn** (seconds) for muted-autoplay social cutdowns. | finish default produces no `.captions_overlay.*`; `--burn-captions` does |
| 8 | Number-anchors never match Whisper (digits) | `sync --report` lint: warn when an anchor contains digits/spelled numbers; suggest the nearest non-numeric verbatim span | anchor "nine hundred million" → flagged with a suggestion |

Effort: ~1–2 days. Files: `hyperframes/incremental.py`, `hyperframes/finish.py`, `bridge/assemble_media.py`,
`bridge/inject_comparison_videos.py`, `hyperframes/edit.py` (list_frames), `webui/routes/hf_scenes.py`,
`hyperframes/sync.py`; tests under `tests/`.

---

## Phase 2 — #3 Click scene → seek + play that range

Front-end only (`templates/hf_scenes.html`). Data is already present: `list_frames` returns each scene's
`start`/`dur`; the frame video is frame-local (scene.start is frame-relative).

1. Give `.frame-vid` a stable `id="frameVid"`; keep the current frame's scenes + `frameDur` in JS state.
2. `selectScene(fid, sid)` → `v.currentTime = scene.start; v.play()`; set `rangeStart/rangeEnd`.
3. One `timeupdate` listener: at `rangeEnd`, pause (play-once) or loop (toggle: "loop scene / play through").
4. **Live playhead + active-scene highlight:** on `timeupdate`, find the scene containing `currentTime`, add
   `.active` to its `.scene-row`/`.tl-seg`; draw a playhead line over the mini-timeline (`left = t/frameDur`).
5. Clicking a `.tl-seg` already calls `selectScene` → now also seeks. Keyboard: space=play/pause,
   ←/→=prev/next scene, L=loop.
6. Fallbacks: no `preview_mp4` → keep the still `#preview`. **Stale badge:** `list_frames` adds
   `stale = spec_mtime > clip_mtime`; show "edited — re-render to preview" so a seek can't mislead.

Effort: ~0.5 day. Test: assert the video element carries an id + scenes payload has start/dur (light).

---

## Phase 3 — #5 Drag-drop asset → pool + per-scene shortlist

### Data model
- Per-scene shortlist lives on the scene: `scene.meta.shortlist = [{name, path, media_type, ts, caption?}]`.
- Naming (your convention): `{scene_id}_edit_{vid|pic}{N}.{ext}` — scene ids are already `fFFsSS`
  (e.g. `f02s08_edit_vid1.mp4`, `f02s08_edit_pic1.jpg`). `N` = next index for that scene+type.
- Pool entry gains provenance: `{id: name, file, media_type, source:"manual-edit", frame_id, scene_id,
  license:"user-provided", caption}` (lossless — extra keys survive round-trips).

### Backend — `edit.py: add_scene_asset(comp, frame_id, scene_id, filename, data)`
1. media_type from ext; **validate** (decodable image via `_valid_image` / video has a real stream) — reject junk.
2. **dedup** by content hash against the scene's existing shortlist.
3. name = `{scene_id}_edit_{vid|pic}{N}.{ext}`; write to `assets/{name}` + `capture/assets/{name}`.
4. register in `pool.json` with scene/frame provenance (extend `_register_pool_asset`).
5. **caption** for pool searchability: MVP = filename; enrich via `judge.py`/VLM (deferred/async).
6. append to `scene.meta.shortlist`; save spec (no recompose — metadata only until wired).
7. `log_activity(kind="asset-add", scene_id=…)`.
- Route: `POST /api/hf/scene/add-asset` (multipart: comp, frame_id, scene_id, files).

### Frontend
- `dragover`/`drop` on `.scene-row` + the inspector (preventDefault, highlight drop target); on drop, POST files, refresh inspector.
- Shortlist strip in the inspector: thumbnails (`<img>` / video poster via frame-thumb), each with **remove** +
  block-aware **"use as ground"**.
- **Block-aware set-as** (`applyEdit` under the hood, gated + recomposed):
  statement/stat → `data.ground={kind,src}` (+`register:footage`); newshead → `data.image`;
  document → `data.source`; comparison → pick side → `side.src`+`type`; gallery/carousel → append to `images`;
  collage → append to `subjects` (needs a cutout — flag if not transparent-PNG).
- Video ground added this way still routes through the Phase-1 freeze-heal.

Effort: ~1–1.5 days. Tests: naming/provenance/shortlist append + junk-reject; block-aware set-as writes the
right field per block.

---

## Phase 4 — #4 Scene-level batch comments → proposals → selectable agent

Primitives already exist: `stage_comment(scene_id)` persists to `frames[i].meta.comments[]`; `list_changeset`
aggregates; `compile_batch_brief` groups by frame with scene tags; `dispatch_batch(session)` → tmux fleet;
Activity feed tracks outcomes. Gaps + the proposal model:

### 4a. Wire scene-level staging (small)
- Add "Stage for batch" in the **scene inspector** → `stageComment(fid, sid, text)` (backend already takes `scene_id`).
- Add a **staged-edits tray** (cart): pending comments grouped by scene, with edit/remove + a count badge.

### 4b. Agent picker (small)
- Replace the blind `prompt()` in `batchDispatch()` with a real `<select>` populated from `/api/hf/agents`
  (reuse `loadAgents()`; it already does this for New-Essay). Show session + idle/busy if available.
- "Who": tmux fleet (nolan1–6) for MVP; later also the `nolan-scene-edit` skill route.

### 4c. Proposal store + review/accept (the architecture)
- **New primitive** `edit.propose_scene_edit(comp, frame_id, scene_id, ops, rationale, provenance)`:
  gates the ops with `author.py --validate-only`, writes to a proposal store
  (`compositions/frames/<id>.proposed.spec.json` or `.hf_proposals.jsonl`: `{id, frame_id, scene_id, ops,
  rationale, provenance:{agent,model,skill@ver,ts,comment_id}, status:"proposed"}`). **Never touches canonical.**
- **Brief change** (`compile_batch_brief`): instruct the agent to call `propose_scene_edit` (NOT edit `*.spec.json`).
  This enforces the contract at the primitive layer, not by convention.
- **Review UI** — a "Proposals" panel (sibling of Activity/changeset): per proposal show the **diff**
  (old→new field values), the rationale, provenance, and **Accept / Reject**. Accept → `_apply_ops` on canonical
  + gate + recompose + stamp provenance + mark comment `applied`. Reject → discard + reopen/deny the comment.
- **Loop:** Activity gains `proposed/accepted/rejected`; "blocked" already = agent capability-gap (first-class).

Effort: ~2–3 days. Tests: `propose_scene_edit` gates without touching canonical; accept applies + stamps
provenance; reject discards; `compile_batch_brief` includes scene-scoped comments.

---

## Testing / verification strategy
- Unit/integration under `tests/` per the table above; run `tests/` (clean ~3 min) + `scripts/test_e2e_smoke.py`.
- **Route/UI coverage is currently MISSING** (a prior audit found IMPLEMENTATION_STATUS falsely claimed TestClient
  coverage). Add TestClient tests for the new routes (frame-video either-name, scene/add-asset, batch brief with
  scene comments, proposals accept/reject) so this program doesn't repeat that gap.
- After each phase: run it, LOOK (extract frames / drive the page), then report.

## Open forks (decide as we reach them)
- Phase-1 #7: keep the browser caption-overlay path at all, or replace with ffmpeg-ASS burn outright?
- Phase-4: proposal store as per-frame `.proposed.spec.json` (diff-friendly) vs a single `.hf_proposals.jsonl`
  (feed-friendly). Leaning `.proposed.spec.json` for clean diffs.
- Phase-3: auto-VLM-caption manual adds at drop time (slower drop) vs deferred/background (blank caption briefly).
