# TTS Integration for Voiceover Generation

This document outlines text-to-speech options for generating voiceovers from scene narrations.

---

## Recommended TTS Engines

### MiniMax (Cloud API) - Primary

High-quality cloud TTS with excellent voice cloning and emotion control.

| Feature | Details |
|---------|---------|
| **Quality** | Studio-grade, human-like |
| **Languages** | 40+ including strong CJK support |
| **Voices** | 300+ built-in voices |
| **Voice Cloning** | 99% similarity from 10s sample |
| **Emotions** | 7 presets: neutral, happy, sad, angry, fearful, surprised, disgusted |
| **Speed Control** | 0.5x - 2.0x |
| **Long Text** | Up to 200,000 chars per request |
| **Latency** | Fast (cloud) |

#### Setup

```bash
# Set API key in .env
MINIMAX_API_KEY=your_api_key
MINIMAX_GROUP_ID=your_group_id
```

#### Python Usage

```python
import requests

url = "https://api.minimax.chat/v1/t2a_v2"

payload = {
    "model": "speech-02-turbo",
    "text": "Your narration text here.",
    "voice_setting": {
        "voice_id": "female-tianmei",  # or custom cloned voice
        "speed": 1.0,
        "emotion": "neutral"
    }
}

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

response = requests.post(url, json=payload, headers=headers)
audio_data = response.content
```

#### Available Models

| Model | Best For |
|-------|----------|
| `speech-02-turbo` | Fast generation, real-time apps |
| `speech-02-hd` | Highest quality, final renders |
| `speech-02` | Balanced quality/speed |

---

### Chatterbox (Local) - Fallback

Open-source TTS from Resemble AI with zero-shot voice cloning.

| Feature | Details |
|---------|---------|
| **License** | MIT (fully open source) |
| **Quality** | High quality |
| **Languages** | 23+ (Multilingual model) |
| **Voice Cloning** | Zero-shot from reference audio |
| **Special Tags** | `[laugh]`, `[cough]`, `[chuckle]`, `[sigh]` |
| **Watermarking** | Built-in neural watermarks |
| **VRAM** | ~8GB (Turbo), ~12GB (Full) |

#### Models

| Model | Parameters | Best For |
|-------|-----------|----------|
| **Turbo** | 350M | Fast batch processing, low latency |
| **Multilingual** | 500M | Non-English content, localization |
| **Original** | 500M | Creative control with CFG tuning |

#### Installation

```bash
pip install chatterbox-tts

# Or from source (Python 3.11+)
git clone https://github.com/resemble-ai/chatterbox
cd chatterbox
pip install -e .
```

#### Python Usage

```python
from chatterbox.tts_turbo import ChatterboxTurboTTS
import torchaudio

# Load model
model = ChatterboxTurboTTS.from_pretrained(device="cuda")

# Generate with voice cloning
wav = model.generate(
    text="Your narration text here.",
    audio_prompt_path="voice_sample.wav"  # 5-10s reference
)

# Save output
torchaudio.save("output.wav", wav, model.sr)
```

#### Paralinguistic Tags

Chatterbox supports natural speech expressions:

```python
text = "I can't believe it [laugh] this is amazing [sigh]"
wav = model.generate(text, audio_prompt_path="voice.wav")
```

Supported tags: `[laugh]`, `[chuckle]`, `[cough]`, `[sigh]`, `[gasp]`, `[groan]`

---

## Other TTS Options

| Engine | Type | Notes |
|--------|------|-------|
| **ElevenLabs** | Cloud API | High quality, expensive |
| **Coqui XTTS-v2** | Local | Good quality, ~6GB VRAM |
| **Fish Speech** | Local | Fast, multilingual |
| **OpenAI TTS** | Cloud API | Simple, good quality |
| **Azure TTS** | Cloud API | Enterprise, many voices |
| **Bark** | Local | Expressive but slow |

---

## Proposed Nolan Integration

### Command

```bash
# Using MiniMax (cloud)
nolan voiceover scene_plan.json --tts minimax --voice "female-tianmei"
nolan voiceover scene_plan.json --tts minimax --voice-clone my_voice.wav

# Using Chatterbox (local)
nolan voiceover scene_plan.json --tts chatterbox --voice-sample narrator.wav

# Options
--output, -o       Output audio file (default: voiceover.wav)
--speed            Speech speed multiplier (default: 1.0)
--emotion          Emotion preset (minimax only)
--model            TTS model variant
```

### Workflow

```
scene_plan.json → Extract narration_excerpt per scene
                → Concatenate into full script
                → Generate audio via TTS
                → Output: voiceover.wav

voiceover.wav   → nolan align scene_plan.json voiceover.wav
                → Updates scene start_seconds/end_seconds
```

### Scene Plan Integration

The `nolan voiceover` command reads narration from scene_plan.json:

```json
{
  "scenes": [
    {
      "id": "Hook_scene_001",
      "narration_excerpt": "In 1999, Hugo Chavez rose to power...",
      "section": "Hook"
    },
    {
      "id": "Hook_scene_002",
      "narration_excerpt": "But behind the scenes, something darker was happening.",
      "section": "Hook"
    }
  ]
}
```

Output: Single audio file with all narrations concatenated in scene order.

### Configuration

```yaml
# nolan.yaml
tts:
  provider: minimax  # or chatterbox

  minimax:
    api_key: ${MINIMAX_API_KEY}
    group_id: ${MINIMAX_GROUP_ID}
    model: speech-02-turbo
    voice_id: female-tianmei
    speed: 1.0
    emotion: neutral

  chatterbox:
    model: turbo  # turbo, multilingual, or original
    voice_sample: ./assets/narrator_voice.wav
    device: cuda
```

---

## Voice Cloning Best Practices

### Recording a Voice Sample

For best cloning results:

1. **Duration**: 10-30 seconds of clean speech
2. **Quality**: 44.1kHz or higher, minimal background noise
3. **Content**: Natural speaking pace, varied intonation
4. **Format**: WAV or FLAC (uncompressed)

### Sample Script for Recording

```
"Hello, my name is [Name]. I'll be narrating this documentary about
the history of Venezuela. The story begins in 1999, when a former
military officer named Hugo Chavez won the presidential election.
What followed would change the country forever."
```

This covers: declarative sentences, questions, names, numbers, and emotional range.

---

## Full Automation Pipeline

With TTS integration, the complete automated pipeline becomes:

```bash
# 1. Process essay to script and scene plan
nolan process essay.md --project venezuela

# 2. Build video library (one-time)
nolan index ./source-videos --project venezuela
nolan sync-vectors --project venezuela

# 3. Match assets
nolan match-clips projects/venezuela/scene_plan.json --project venezuela
nolan match-broll projects/venezuela/scene_plan.json

# 4. Generate voiceover (NEW)
nolan voiceover projects/venezuela/scene_plan.json --tts minimax

# 5. Align scenes to audio
nolan align projects/venezuela/scene_plan.json projects/venezuela/voiceover.wav

# 6. Render and assemble
nolan render-clips projects/venezuela/scene_plan.json
nolan assemble projects/venezuela/scene_plan.json projects/venezuela/voiceover.wav

# Output: projects/venezuela/final_video.mp4
```

### One-Command Version (Future)

```bash
nolan make-video essay.md --project venezuela --voice narrator.wav
```

---

## Future Enhancements

- [ ] Implement `nolan voiceover` command
- [ ] MiniMax API client with streaming support
- [ ] Chatterbox local inference wrapper
- [ ] Voice sample management (store per-project)
- [ ] SSML support for fine-grained control
- [ ] Per-scene emotion/speed adjustments
- [ ] Automatic pause insertion between scenes
- [ ] Audio normalization and compression
