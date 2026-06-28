# Feedback file: review_2.md

Consumed by clip_selector refine pass 1 at 2026-04-28T00:29:20+00:00.

---

Two changes based on the prior clip_selector report:

1. **Re-plan the genuinely thin beats as generated-image.** The prior report identified 7 scenes where the library has no archival equivalent (Angel Falls, Spanish galleon, 1920s oil gusher, Betancourt 1950s, Andes/Mérida contemplative, vintage 1900s coffee/cocoa farming, diverse Venezuelan portraits). For all 7, change visual_type from b-roll to generated-image. Clear any matched_clip on those scenes since library footage is no longer expected. Per scene IDs from the prior report:
   - Hook/scene_001 (Angel Falls)
   - Hook/scene_002 (Los Roques — also library-thin, redirect this one too)
   - Context/scene_003 (Spanish galleon / colonization)
   - Context/scene_006 (Vintage 1900s coffee/cocoa farming)
   - Evidence 1/scene_003 (1920s oil gusher / Gómez era)
   - Evidence 1/scene_005 (Betancourt 1950s archival)
   - Conclusion/scene_006 (Andes / Mérida contemplative)
   - Conclusion/scene_008 (Diverse Venezuelan portraits)

2. **Lower the similarity threshold for the unmatched-but-should-exist scenes.** The prior report listed 8 b-roll scenes where the matcher failed but coverage *should* exist (Caracas street, oil infrastructure, Maduro speeches, opposition protests, migration exodus, empty shelves, 1980s austerity, 1970s oil-boom). Re-run nolan match-clips with --min-similarity 0.4 and --candidates 8 with --skip-existing so my four prior approved matches are preserved. After re-running, re-evaluate any new matches against the style guide.

Out of scope for this refine: re-indexing the missing Hugo Chavez Savior or Destroyer documentary — that requires re-running nolan index, which is admin work. Note it in the report but don't try to do it.
