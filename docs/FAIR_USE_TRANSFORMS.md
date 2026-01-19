# Fair Use Transformation Strategies

This document outlines techniques for transforming third-party clips and images to reduce copyright detection risks while operating under Fair Use principles.

> **Disclaimer:** These are technical strategies, not legal advice. Always consult with a legal professional for specific copyright concerns.

---

## Visual Modifications

### Framing Changes

| Technique | Description | Effectiveness |
|-----------|-------------|---------------|
| **Crop/Zoom** | Show only 70-80% of the original frame | High |
| **Picture-in-Picture** | Display clip in a smaller window over your own content | High |
| **Borders/Frames** | Add visual framing that distinguishes from original | Medium |
| **Mirror/Flip** | Horizontal flip of the image | Medium |
| **Aspect Ratio** | Change from original (e.g., 16:9 → 4:3 with letterbox) | Medium |

### Processing Effects

| Technique | Description | Effectiveness |
|-----------|-------------|---------------|
| **Color Grading** | Apply custom color treatment or LUT | High |
| **Speed Adjustment** | Slight speed change (1.05x-1.1x or 0.9x-0.95x) | High |
| **Resolution Change** | Downscale from original resolution | Low-Medium |
| **Filters** | Blur, vignette, grain, or stylization | Medium |
| **Frame Rate** | Convert frame rate (e.g., 30fps → 24fps) | Low |

### Overlays

| Technique | Description | Effectiveness |
|-----------|-------------|---------------|
| **On-screen Text** | Commentary, labels, analysis annotations | High |
| **Branding/Watermark** | Your logo or channel identifier | Medium |
| **Split-screen** | Show alongside other content for comparison | High |
| **Motion Graphics** | Animated elements layered on top | High |
| **Progress Bar/Timestamp** | Visual indicator of clip timeline | Low-Medium |

---

## Audio Modifications

| Technique | Description | Effectiveness |
|-----------|-------------|---------------|
| **Replace Audio** | Remove original, use your narration/music | Very High |
| **Mix Under Commentary** | Lower original audio, overlay your voice | High |
| **Pitch Shift** | Slight pitch adjustment (±5-10%) | Medium |
| **Audio Ducking** | Dynamically lower clip audio when speaking | High |

---

## Usage Patterns

### Timing

- **Keep clips brief** - 5-15 seconds per clip is ideal
- **Intercut frequently** - Mix third-party clips with your own footage/graphics
- **Avoid full sequences** - Don't show complete scenes or segments

### Context

- **Transformative purpose** - Add commentary, criticism, or analysis
- **Educational framing** - Explain or teach using the clip as reference
- **News/reporting** - Discuss events depicted in the footage
- **Parody/satire** - Creative reinterpretation (strongest protection)

---

## Recommended Combinations

### Minimal Transform (Low Risk Content)
- Crop to 85%
- Add corner watermark
- Replace or lower audio

### Standard Transform (Medium Risk Content)
- Crop to 75%
- Apply color grade
- Speed adjust ±5%
- Add text overlay/commentary
- Replace audio with narration

### Maximum Transform (High Risk Content)
- Crop to 70%
- Mirror/flip
- Heavy color grade or filter
- Speed adjust ±10%
- Picture-in-picture or split-screen
- Full audio replacement
- Motion graphics overlay

---

## Implementation Notes

These transforms can be applied in the Nolan render pipeline:

1. **Scene Plan Level** - Specify transforms per clip in `scene_plan.json`
2. **Post-Processing** - Apply batch transforms after initial render
3. **Preset System** - Use named presets like `fair_use_standard`

### Potential FFmpeg Commands

```bash
# Crop to 75% center
ffmpeg -i input.mp4 -vf "crop=iw*0.75:ih*0.75" output.mp4

# Horizontal flip
ffmpeg -i input.mp4 -vf "hflip" output.mp4

# Speed up 5%
ffmpeg -i input.mp4 -vf "setpts=0.95*PTS" -af "atempo=1.05" output.mp4

# Color grade (example: increase contrast, desaturate slightly)
ffmpeg -i input.mp4 -vf "eq=contrast=1.2:saturation=0.8" output.mp4

# Combine multiple transforms
ffmpeg -i input.mp4 -vf "crop=iw*0.75:ih*0.75,hflip,setpts=0.95*PTS,eq=contrast=1.1" output.mp4
```

---

## AI Video Regeneration

A more robust approach: extract a frame from the source clip, then use an Image-to-Video AI model to regenerate the scene entirely. The output is AI-generated content, not the original footage.

### Why This Works

| Aspect | Original Clip | AI-Regenerated |
|--------|---------------|----------------|
| ContentID match | Yes | No |
| Legal status | Licensed/copyrighted | You own the output |
| Visual similarity | Identical | Similar concept |
| Fingerprint match | Yes | No |

### Workflow

```
Source Clip → Extract Key Frame → Wan 2.1 I2V → New AI Video
```

### Recommended Models

| Model | Type | VRAM | Speed | Quality |
|-------|------|------|-------|---------|
| **LTX-Video 2** | Image-to-Video | ~12GB | Very Fast | Good |
| **Wan 2.1-I2V-14B** | Image-to-Video | ~24GB | Slow | Highest |
| **Wan 2.1-I2V-1.3B** | Image-to-Video | ~8GB | Fast | Good |
| **CogVideoX-I2V** | Image-to-Video | ~16GB | Medium | Good |
| **Stable Video Diffusion** | Image-to-Video | ~12GB | Medium | Medium |

> **LTX-2** from Lightricks is particularly good for batch processing - generates 5s clips in seconds on a 4090.

### Implementation Example

```bash
# 1. Extract key frame from source clip (middle frame)
ffmpeg -i source_clip.mp4 -vf "select=eq(n\,75)" -frames:v 1 keyframe.png

# 2. Run Wan 2.1 I2V (via ComfyUI or direct API)
# The output is a new AI-generated video based on the keyframe

# 3. Use regenerated video in your project
```

### Best Practices

1. **Choose representative frames** - Pick frames that capture the essential visual (not transitions)
2. **Match duration** - Generate videos matching your scene timing needs
3. **Prompt enhancement** - Add text prompts to guide the regeneration style
4. **Batch process** - Queue all clips needing regeneration in one run

### Prompt Tips for I2V

```
# Neutral regeneration (stay close to source)
"cinematic video, smooth motion, high quality"

# Stylized regeneration (add artistic distance)
"documentary footage, film grain, 1970s aesthetic"
"news broadcast style, professional lighting"
```

---

## AI Image Editing (For Stills & Keyframes)

Fast local image editing models can transform source images before use - useful for b-roll stills or as a pre-step before I2V.

### Recommended Image Edit Models

| Model | Type | VRAM | Speed | Best For |
|-------|------|------|-------|----------|
| **Qwen2-VL + Edit** | Instruction-based edit | ~8GB | Fast | Text-guided edits |
| **InstructPix2Pix** | Instruction-based edit | ~8GB | Fast | "Make it look like..." |
| **FLUX.1 img2img** | Style transfer | ~12GB | Medium | High quality restyling |
| **IP-Adapter** | Style/face transfer | ~8GB | Fast | Apply reference style |
| **ControlNet + SD** | Guided generation | ~8GB | Fast | Preserve structure, change style |
| **Stable Diffusion img2img** | Denoising | ~6GB | Fast | Quick style shift |

### Workflow Options

**Option A: Edit Frame → I2V**
```
Source Frame → Image Edit (restyle) → I2V → AI Video
```

**Option B: Direct Image Edit (for stills)**
```
Source Image → Image Edit → Use directly as b-roll
```

### Example Prompts for Image Editing

```
# InstructPix2Pix / Qwen style
"Convert to oil painting style"
"Add film grain and vintage color grading"
"Make it look like a documentary photograph"
"Stylize as graphic novel illustration"

# img2img with low denoising (0.3-0.5)
# Preserves composition, shifts aesthetics
```

### Why This Helps

- Lower compute than full I2V
- Works for single images (b-roll, thumbnails)
- Can be chained: edit image → then I2V for motion
- Many models run fast on consumer GPUs

---

## Future Enhancements

- [ ] Add `--fair-use-transform` flag to render CLI
- [ ] Create preset configurations for transform levels
- [ ] Integrate transforms into scene plan schema
- [ ] Build automated batch processing for clip libraries
- [ ] Add `nolan regenerate-clips` command using LTX-2 / Wan I2V
- [ ] Add `nolan transform-images` command using Qwen/InstructPix2Pix
- [ ] ComfyUI workflows for batch I2V and image editing
- [ ] Chain workflows: source → image edit → I2V → output
