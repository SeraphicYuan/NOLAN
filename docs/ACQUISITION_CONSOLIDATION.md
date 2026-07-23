# Acquisition Consolidation — program plan

**Status:** in progress · started 2026-07-23 · derived from the key-assets build post-mortem.

The asset stack grew into **three pools with duplicated plumbing** — pipeline (`asset_pool.py`),
HyperFrames (`bridge/pool.py` → `pool.json`), and key-assets (`keyassets/`). The four organs (build
search client, download+validate, VLM verify, query-gen) are reimplemented 2–3× with drifting, sometimes
opposite behavior. This program back-ports the key-assets lessons and consolidates onto shared plumbing.

**Framing — two pools, one spine:** `acquire` = recall/atmosphere (junk-FLOOR verify); `keyassets` =
precision/heroes (positive-GATE verify). Keep the two philosophies; **share the plumbing**.

## The five steps (execute in order; test + commit each)

1. **Verify correctness fix (bug).** The bridge VLM cull (`bridge/pool.py:score_and_caption`) sends
   full-size stills to the vision model (no downscale) → multi-MB/>4k-px images ERROR → and the graceful
   default treats an error as KEEP → junk survives the floor. Back-port the key-assets fix: **downscale to
   1024px before the vision call.** (Error→keep stays correct FOR A FLOOR — don't empty on outage.)

2. **Extract shared organs (debt paydown; unlocks the rest).** One `valid_image()`, one
   `build_search_client(cfg)`, one provider-tier registry (currently 3 copies: `engine.TIERS`, bridge
   `_PROVIDER_TIERS`, `resolve._SOURCE_PREF`), and one **VLM-verify organ with a configurable posture**
   (`floor | gate`, mandatory downscale, explicit error-policy). Migrate acquire + keyassets onto it.

3. **Wire HF selection (highest /pool value).** The scored HF pool has NO selection channel, and the
   shortlist never reaches the HF author. Generalize the key-assets refine-scope pattern (verify/relevance
   badges + select-into-scope toggle **wired to the consumer**) so the HF pool gets selection and HF
   authoring consumes it.

4. **Concurrency in the acquire engine (speed).** `acquire/engine.py` is fully sequential; parallelize
   per-need acquisition (bounded pool) like keyassets' 10-way collect. Backoff already shared via
   `image_search`.

5. **Identifier query-gen for concrete needs (quality).** `derive_asset_needs` produces phrasings only;
   give concrete/named needs the key-assets identifier injection (world-knowledge/relationships).

## Discipline
- Each step: unit test where pure, integration-verify where live, commit surgically (shared tree).
- WIRING_CHECKLIST for anything newly wired (#3 esp.); honesty test the shared verify posture.
- Update IMPLEMENTATION_STATUS per step.
