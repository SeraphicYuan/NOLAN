# HyperFrames E2E Post-Mortem — Fix Backlog

**Source:** nolan6's review after a cold fleet run of `the-diamond-illusion-hf`
(2026-07-23) — the first full author → hf-finish → render done by a fresh agent.
**Status:** planning only (no code changed). Each item verified against the code
below; severity corrected where the field report overstated it.

## Verification + severity notes

- Claims cross-checked against source; file:line cited per item.
- **Corrected:** the "~88 orphaned chrome" (item R1) is overstated. Live
  monitoring showed only **2** procs were the render's headless puppeteer; ~80
  were the *user's own browser*, and the I/O saturation was the recurring WSL
  `/mnt/d` mount instability, not chrome. nolan6's own cleanup note agrees
  ("killed only the 2 --headless parents"). The **reap** bug is real but tiny;
  the **observability** half (empty log from Windows stdout buffering) is the
  valuable part.

## Meta-rule (per CLAUDE.md / WIRING_CHECKLIST)

Docs claim, tests enforce. Every item below names its **honesty test** — a fix
without one isn't done. Items that touch a gate or an authored field must add
the test in the same change.

---

## Tier 1 — quick, high-value, deterministic (do first)

### S1 · Sync LEAD gate (the systemic "text before voice")  ★ flagged by the user
- **Symptom:** ~30 of 68 scenes enter 2.7–12.4 s (avg ≈5.5) *before* their anchor
  phrase is spoken; the whole essay reads slightly ahead of the voice.
- **Root cause (verified):** `sync.py:812` `_visual_lag_flags` only flags
  `start - ct > min_lag` (visual **trails**) plus a mis-order check. There is
  **no symmetric lead check** (`ct - start > threshold`), so an early visual
  passes as "✓ ok."
- **Fix:** add a `kind: "lead"` flag when `ct - start > min_lead` (start a lead
  threshold ~4–6 s — a small lead is natural for a title; a big one is jarring).
  Surface it in `sync --report` and in the timing gate. Keep **soft by default**
  (leads are a taste call, unlike a hard lag); consider `hard` only for extreme
  leads on non-title blocks. Reuse the same `_topic_open_time` signal so lint and
  placement never disagree.
- **Files:** `src/nolan/hyperframes/sync.py` (`_visual_lag_flags`, the report,
  the gate wiring in `finish.py` scene-timing gate).
- **Systematic pairing:** S1 is the **symmetric detector / safety-net**; **S2 is
  the actual cure** (most leads come from multi-fact even-spread). Ship them
  together — a gate that only flags without S2 just moves the fix back onto the
  author by hand. Robustness = fix placement (S2) + catch residual drift both
  directions (S1).
- **Effort:** low. **Test:** extend the sync suite — a scene starting well before
  its content-time is flagged `lead`; a title with a small lead is not.

### L1 · Layout lint false-FAILs full-bleed scenes and shouts "FAIL" on a soft step
- **Symptom:** grounded full-bleed footage scenes get "0% of content mass in the
  editorial-column zone"; the run prints `FAIL — layout errors` then continues,
  training the author to ignore it.
- **Root cause (verified):** the zone-mass check is *already* archetype-driven
  (`layout_lint.py:6` "against the archetype registry's machine-readable safe-areas
  + anchor zone"; `_ANCHOR_DRIFT_FRAC = 0.60`). The real defect is that it treats a
  `data.ground` full-bleed scene's legitimate media mass (outside the text column)
  as drift — the check isn't **ground-aware**, and/or the full-bleed archetype's
  registered zone in `archetypes.json` doesn't declare full-canvas.
- **Fix (systematic, not an exemption list):** don't special-case "full-bleed" —
  make the mass check **ground-aware**: a scene carrying a `data.ground` counts the
  ground as content mass satisfying its zone (or, better, the full-bleed/media
  archetype declares a full-canvas zone in `themes/composition/archetypes.json` and
  the check simply reads it — one dialect, no exemptions). Separately, downgrade the
  soft-step wording from `FAIL` → `WARN`/`advisory` at `layout_lint.py:685`.
- **Files:** `src/nolan/hyperframes/layout_lint.py`,
  `themes/composition/archetypes.json` (zone declaration).
- **Effort:** low. **Test:** a full-bleed `data.ground` scene passes zone-mass via
  its archetype's declared zone (not a hardcoded skip); a genuinely crowded-left
  text scene still fails; assert the check reads the archetype zone, not a type list.

---

## Tier 2 — real, medium effort

### S2 · Multi-fact blocks don't track the spoken word
- **Symptom:** `bullet_list` / multi-item `stat` items carry no per-item `at:`
  anchor, so the reveal scheduler spreads them evenly across the window; when the
  narration is back-loaded (facts at 523/528/536), even-spread guarantees a lead.
- **Root cause (verified):** the reveal scheduler lives in `sync.py`
  (`_reveal_times`/`_retime_reveals`, see [[project_data_reveal_sync]]); items
  without an explicit `at` are spread, not word-anchored.
- **Fix:** when a multi-fact item's text has a confident spoken-word match,
  fire that item on the word (per-item `at`); fall back to spread only where
  timing carries no meaning. Partly an author-prompt reinforcement too.
- **Files:** `sync.py` (reveal scheduler), the AUTHOR_PROMPT/brief note.
- **Effort:** medium. **Test:** a back-loaded multi-item scene retimes each item
  to its word instead of even-spread.

### A1 · Manual `capture/ → assets/` staging is a whole failure class
- **Symptom:** `asset-descriptions.md` lists `assets/ka_…` paths, files live in
  `capture/assets/` + `capture/keyassets/`, and `assemble_media` reads `assets/`.
  Nothing bridges them — every hero/b-roll file was hand-copied; the kickoff even
  warns "copy clips into assets/ first." A forgotten copy = a silent black hole.
- **Root cause (verified):** `finish.py:260` runs `bridge/assemble_media.py`,
  which walks composed HTML for grounds but does **not** resolve a referenced
  `assets/x` from `capture/**` when it's missing.
- **Fix:** `assemble_media` resolves each referenced `assets/x` — if absent,
  find it under `capture/{assets,keyassets}{,/videos}/` by basename and copy it
  in. Turns the documented manual step into a deterministic one.
- **Files:** `render-service/_lab_hyperframes/bridge/assemble_media.py`; drop the
  manual-copy warning from the kickoff once done.
- **Effort:** medium. **Test:** a comp whose `asset-descriptions.md` references a
  basename present only in `capture/` assembles with the file staged (no drop).

### R1 · Render is an observability black hole + doesn't reap its 2 headless procs
- **Symptom:** detached `hf-finish` log stayed empty the whole ~30-min render
  (Windows python buffers stdout); the render exited without killing its
  puppeteer chrome (2 procs). *(Not 88 — see severity note.)*
- **Fix (two small):** (a) the render writes a heartbeat to a fast local path
  (`renders/.progress` frame N/total + an atomic `renders/.done` sentinel on
  success) so orchestrators key on a **file, not process death**; (b) wrap the
  browser launch in `try/finally` that kills the tracked browser PID on exit
  (even on crash).
- **Files:** the render entrypoint (`.agents/skills/hf-author/scripts/*` render
  path / the hyperframes render invocation in `finish.py:286`).
- **Effort:** medium. **Test:** a render writes `.progress` then `.done`; no
  headless proc with the render's profile survives the call.

---

## Tier 3 — enhancements / edge / minor

### S3 · Long ungrounded holds are diagnosed but not acted on
- `sync --report` flags ~7 statement/bullet beats holding 15–23 s on bare paper,
  but the author fixes them by hand. The system has the beat text, the frame, and
  the b-roll pool — the "deterministic where computable" case.
- **Fix:** auto-propose (or auto-apply-with-confirm) a pool ground for a long
  ungrounded hold. **Files:** `sync.py` report + `block_plan.py`/compose.
  **Test:** a >15 s ungrounded statement beat gets a proposed ground.

### F1 · `ensure_storyboard` maps frame↔section positionally
- **Verified:** `edit.py:146` instructs "exactly one frame per section (frame N ↔
  section N)". If a long section is split into two frames, caption text / BGM mood
  / section body silently misalign — no error.
- **Fix:** have each frame declare its section id explicitly instead of relying on
  index alignment. **Test:** a split section keeps per-frame caption/mood aligned.

### N1 · Number-provenance gate coverage is narrower than its docs imply
- **Verified:** the gate at `finish.py:185` (`HF_ALLOW_UNSOURCED` escape) fires on
  a fabrication set; nolan6 reports it only triggers on ≥3 numeric values and
  exempts ≤2-point charts, so a fabricated string number or a bogus 2-bar chart
  passes. **Fix (systematic, not a threshold tweak):** the count threshold is the
  band-aid — gate by **claim TYPE**, not token count: any value living in a
  structured data block / chart series must carry a `value_source`, regardless of
  how many there are (incidental numbers in prose stay exempt by being prose, not
  by a count). **Test:** a 2-point chart with an unsourced value is flagged; an
  incidental number in a statement is not.

### D1 · `sync --report` messaging sets a wrong expectation
- Sold as a "~2 s preview" but the first call pays full Whisper alignment
  (minutes) before it's cached. **Fix:** message the cold-cache cost. Trivial.

---

## Tier 4 — architectural (bigger, schedule deliberately)

### P1 · Make `block_plan` the fleet's default first step
- **Observation (not a bug):** hero placement + block variety are inherently
  **global** decisions; `block_plan.py` exists to compute the global skeleton then
  fan workers out to fill copy — but it's optional and easy to skip, so every
  orchestrator re-derives the global contract in its head (nolan6 did, and
  authored centrally rather than fan-out). Making `block_plan` the default first
  step would make the fleet path safe at scale (no 9 blind workers each dropping a
  logo at every mention).
- **Files:** `block_plan.py`, the fleet dispatch / kickoff. **Effort:** high.
  **Test:** the fleet path runs `block_plan` before dispatching frame workers.

---

## Deferred — needs its own strategy (not in this program)

### B1 · BGM offline strategy
BGM shipping silent offline (`bgm: retrieve requires a HeyGen credential —
skipped`, `finish.py:212`) is real, and a local-music organ exists
(`audio_mix.load_music_library` / `resolve_music_config`,
`projects/_library/music/`). **But the right answer is a broader BGM strategy
decision** (source/licensing, selection quality, HeyGen vs local vs generated,
per-essay mood matching) — deferred to a dedicated pass. Do NOT bolt on a quick
`if no-credential: local` fallback in the meantime.

## Recommended sequence

1. **Tier 1** (S1 sync-lead, L1 layout-lint) — highest value-to-effort, each
   independently testable, no architectural risk.
2. **Tier 2** (S2 per-item anchoring, A1 assemble-media auto-stage, R1
   render observability+reap) — remove failure classes.
3. **Tier 3** as opportunistic cleanups.
4. **Tier 4** (block_plan default) only if the fleet path is going to be used at
   scale — otherwise it's premature.
- **Deferred:** B1 BGM offline strategy — separate topic, its own pass.

S1 + S2 together close the "text arrives before voice" feel; A1 + R1 close the two
operational black holes. That's the 80/20.
