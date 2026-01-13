# Render Pipeline Architecture

**Date:** 2026-01-12
**Status:** Implementation

## Overview

Two-phase video assembly pipeline that separates complex animation rendering from final video stitching.

```
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 1: PRE-RENDER                          │
│                                                                 │
│  scene_plan.json                                                │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │ Infographics│     │ Sync-point  │     │    Text     │       │
│  │   (SVG)     │────▶│  Animations │────▶│  Overlays   │       │
│  └─────────────┘     └─────────────┘     └─────────────┘       │
│       │                    │                    │               │
│       └────────────────────┴────────────────────┘               │
│                            │                                    │
│                            ▼                                    │
│                   render-service (Remotion)                     │
│                            │                                    │
│                            ▼                                    │
│                   assets/clips/*.mp4                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 2: ASSEMBLY                            │
│                                                                 │
│  ┌──────────────────────────────────────────────────────┐      │
│  │                   scene_plan.json                     │      │
│  │                                                       │      │
│  │  scene_001: matched_asset (b-roll image)             │      │
│  │  scene_002: rendered_clip (animated infographic)     │      │
│  │  scene_003: generated_asset (AI image)               │      │
│  │  scene_004: rendered_clip (sync-point animation)     │      │
│  │  ...                                                  │      │
│  └──────────────────────────────────────────────────────┘      │
│                            │                                    │
│                            ▼                                    │
│                    FFmpeg Assembly                              │
│                            │                                    │
│         ┌──────────────────┼──────────────────┐                │
│         │                  │                  │                 │
│         ▼                  ▼                  ▼                 │
│    Scale images     Concat clips      Add voiceover            │
│    to 1920x1080     with transitions  audio track              │
│         │                  │                  │                 │
│         └──────────────────┼──────────────────┘                │
│                            │                                    │
│                            ▼                                    │
│                      final_video.mp4                            │
└─────────────────────────────────────────────────────────────────┘
```

## Scene Asset Priority

When assembling, use the first available asset in this order:

1. `rendered_clip` - Pre-rendered MP4 clip (highest priority)
2. `generated_asset` - AI-generated image
3. `matched_asset` - Downloaded b-roll image
4. `infographic_asset` - Static SVG (fallback, will be rendered to clip)

## Commands

### `nolan render-clips`

Pre-renders animated scenes to MP4 clips.

```bash
nolan render-clips scene_plan.json

# Options:
#   --force        Re-render even if clip exists
#   --parallel N   Render N clips concurrently (default: 4)
#   --resolution   Output resolution (default: 1920x1080)
```

**What gets rendered:**
- Scenes with `visual_type: graphics` and `infographic` spec
- Scenes with `sync_points` (word-triggered animations)
- Scenes with `animation_type` specified

**Output:**
- Clips saved to `assets/clips/{scene_id}.mp4`
- `scene_plan.json` updated with `rendered_clip` paths

### `nolan assemble`

Assembles final video using FFmpeg.

```bash
nolan assemble scene_plan.json voiceover.mp3 -o final_video.mp4

# Options:
#   --resolution   Output resolution (default: 1920x1080)
#   --fps          Frame rate (default: 30)
#   --transition   Transition type: cut, fade, crossfade (default: cut)
#   --transition-duration  Duration in seconds (default: 0.5)
```

**Process:**
1. Load scene_plan.json
2. For each scene:
   - Determine asset source (priority order above)
   - Calculate duration from `start_seconds` / `end_seconds`
   - Scale/pad to target resolution
3. Generate FFmpeg filter graph
4. Add voiceover audio
5. Export MP4

## Scene Data Model Updates

```python
@dataclass
class Scene:
    # ... existing fields ...

    # Asset fields (in priority order)
    rendered_clip: Optional[str] = None      # Pre-rendered MP4 clip
    generated_asset: Optional[str] = None    # AI-generated image
    matched_asset: Optional[str] = None      # Downloaded b-roll
    infographic_asset: Optional[str] = None  # Static SVG

    # Timing (set by alignment)
    start_seconds: Optional[float] = None
    end_seconds: Optional[float] = None

    # Animation spec (for render-clips)
    animation_type: Optional[str] = None     # fade, zoom, pan, kenburns
    animation_params: Optional[dict] = None  # type-specific params
    sync_points: List[SyncPoint] = field(default_factory=list)
```

## Render Service Integration

The render-service already supports:
- Infographic rendering (SVG/MP4)
- Remotion video composition
- Motion Canvas animations

For `render-clips`, we extend the render-service API:

```typescript
POST /render/clip
{
  "scene_id": "scene_006",
  "type": "infographic" | "sync_animation" | "text_overlay",
  "duration": 8.5,
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "spec": {
    // Type-specific specification
  }
}

Response:
{
  "job_id": "...",
  "status": "completed",
  "output": "scene_006.mp4"
}
```

## FFmpeg Assembly Strategy

### For Images (b-roll, generated)
```bash
# Scale and pad to 1920x1080, hold for duration
ffmpeg -loop 1 -t 5.5 -i scene_001.jpg \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" \
  -c:v libx264 -pix_fmt yuv420p scene_001_clip.mp4
```

### For Pre-rendered Clips
```bash
# Just trim to exact duration if needed
ffmpeg -i scene_006.mp4 -t 8.5 -c copy scene_006_trimmed.mp4
```

### Concatenation
```bash
# Create concat list
echo "file 'scene_001_clip.mp4'" >> concat.txt
echo "file 'scene_002_clip.mp4'" >> concat.txt
# ...

# Concatenate all
ffmpeg -f concat -safe 0 -i concat.txt -c copy video_only.mp4

# Add audio
ffmpeg -i video_only.mp4 -i voiceover.mp3 \
  -c:v copy -c:a aac -shortest final_video.mp4
```

### With Crossfade Transitions
```bash
ffmpeg -i clip1.mp4 -i clip2.mp4 -i clip3.mp4 \
  -filter_complex "
    [0][1]xfade=transition=fade:duration=0.5:offset=4.5[v01];
    [v01][2]xfade=transition=fade:duration=0.5:offset=9[vout]
  " \
  -map "[vout]" output.mp4
```

## File Structure

```
test_output/
├── scene_plan.json
├── assets/
│   ├── broll/
│   │   ├── scene_001.jpg
│   │   └── ...
│   ├── generated/
│   │   ├── scene_008.png
│   │   └── ...
│   ├── infographics/
│   │   ├── scene_006.svg
│   │   └── ...
│   ├── clips/                 # ← NEW: Pre-rendered clips
│   │   ├── scene_006.mp4
│   │   ├── scene_010.mp4
│   │   └── ...
│   └── voiceover/
│       ├── voiceover.mp3
│       └── voiceover.srt
├── word_timestamps.json
├── unmatched_align_scenes.json
└── final_video.mp4            # ← Final output
```

## Implementation Order

1. Add `rendered_clip` field to Scene dataclass
2. Implement `nolan render-clips`:
   - Identify scenes needing pre-render
   - Call render-service for each
   - Update scene_plan.json
3. Implement `nolan assemble`:
   - Asset resolution logic
   - FFmpeg filter graph generation
   - Audio mixing
4. Test with Venezuela project
