# NOLAN Bottlenecks (v1)

Synthesis after one full benchmark run (script → scenes → assets → orchestrate → render) on the
"Football Beyond War" project. See [football_benchmark.md](../video_analysis/football_benchmark.md).
Date: 2026-06-15.

## Tier 1 — what blocks a finished, comparable video (the production layer)

**1. Asset sourcing is the hard ceiling — THE bottleneck.**
NOLAN can *plan* a 294-scene documentary well but can't *source* the footage:
- Stock b-roll: **0/122** matched (Wikimedia lacks this material; no Pexels/Pixabay keys; no-key sources are weak for documentary footage).
- Library clips: **127/294, but 125 were the source video itself** — semantic matching just re-retrieves a tiny 4-video library; no way to grow a broad, diverse library.
- Generated imagery: **57 scenes need ComfyUI**, not wired into the run.
- Planning is decoupled from a real asset supply → every plan renders mostly empty.

**2. No narration audio (no TTS).** `assemble` requires an external `--audio-file`. NOLAN can't voice its own script. *(Resolved operationally: user provides audio via ElevenLabs once a script exists.)*

**3. Rendering only covers a fraction.** Only **61/294** scenes rendered (graphics/host); b-roll and generated scenes have nothing to render. Gated entirely by #1.

## Tier 2 — performance & scale

**4. LLM round-trip count.** Design is multi-pass (beats → scenes → enrich) × every section. Serialization fixed (parallel + cache: 36 min → ~3 min; 261× on re-run); duplicate clip-selection removed (699s → seconds). Residual: high raw call count per section.

**5. The Claude-CLI orchestrator is heavy and fragile.** Director shells out to the Claude CLI per step (style 88s; clip-select *was* 699s); subject to version skew/auth; slowest, least observable layer.

**6. Caching is spotty.** Vision has `frame_cache`; design cache added. Matching, scoring, translation, orchestrate have none.

## Tier 3 — robustness & architecture

**7. Brittle LLM-output handling.** Pipeline assumes clean JSON. This run surfaced three breakages: `KeyError:'label'` (unescaped prompt brace), tencent single-quoted JSON, qwen numeric `duration` vs Gemini string. Every new model breaks something — no tolerant/validated parsing layer.

**8. Provider abstraction incomplete.** `GeminiClient` hardcoded in ~9 places (script conversion, scene design, clustering, indexer inference). OpenRouter added for vision + optional design LLM, but the text path is otherwise Gemini-locked. Swapping models is per-call surgery, not config.

**9. Sync I/O inside the async hub.** `ImageScorer` used blocking httpx in the event loop and froze the hub during matching (offloaded now); the sync-in-async pattern recurs across modules.

**10. Shallow i18n.** CJK can't render (Latin-only fonts); subtitle langs were English-only; cp1252 corrupted ffmpeg output (langs + UTF-8 fixed; renderer still can't draw Chinese).

**11. Weak observability.** Design was a black box (fixed); matching and orchestrate remain opaque/heavy.

## Verdict
NOLAN's "thinking" layer (script → scenes → style guide) is strong; its "supply" layer — sourcing footage, generating images, voicing narration — is the bottleneck between a great *plan* and a finished *video*.

**Priority:** (1) asset supply and (2) TTS unlock end-to-end output. Tier 2/3 are optimizations on a pipeline that otherwise can't reach the finish line.

## Work status
- Tier 2 #4, #5: **done** (parallel design, design cache).
- Tier 2 #5(orchestrator clip-select) / consolidation: **done** (vector matcher replaces the LLM pass).
- Tier 1 #2 (TTS): resolved via ElevenLabs (user-provided audio).
- **#8 (provider abstraction): done.** `create_text_llm(config)` factory; **qwen/qwen3.7-plus is now the
  default for every text task** Gemini did (script conversion, scene design, clustering, indexer
  inference, translation). Choosable three ways: `nolan.yaml` `llm:` block (global), the Settings page
  LLM section (`/api/settings`), and per-run override (webUI design `llm_provider`/`llm_model`).
  Verified: a design with no provider defaults to qwen3.7-plus.
- **#7 (robust LLM-output parsing): largely done** — scene-design fence-stripping, clustering
  bracket-extraction, `clip_matcher` numeric/string duration, ScriptConverter is plain text (no JSON).
  (tencent's single-quote JSON remains a model deficiency, not parseable safely.)
- #9 (sync-in-async): b-roll match offloaded to a worker thread + concurrent scoring.
- **#1 (asset sourcing): v1 done** — video/archival sourcing + ComfyUI generation. See
  [ASSET_SOURCING_v1.md](ASSET_SOURCING_v1.md). Search layer is now image/video-aware; Internet
  Archive (keyless archival video) + Pexels/Pixabay video providers; query-variant + multi-source
  b-roll matching (`broll-video`); ComfyUI generation wired into the hub/Studio. Remaining: render-time
  fetch+trim of external video, Pexels/Pixabay keys, fallback-to-graphics, library-growth (fetch-and-index).
