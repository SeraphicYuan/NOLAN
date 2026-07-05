# Music library

Drop license-safe music tracks here (mp3/wav/m4a/ogg/flac) — e.g. downloads
from the YouTube Audio Library (safe for monetized videos).

Optional `music.json` tags tracks for auto-selection by the sound-design
stage (untagged files default to energy 0.5):

```json
[
  {"file": "epic-dawn.mp3",  "energy": 0.75, "mood": "epic",       "tags": ["orchestral", "rising"]},
  {"file": "still-water.mp3","energy": 0.25, "mood": "contemplative", "tags": ["piano", "ambient"]}
]
```

Enable per project in `project.yaml`:

```yaml
music: auto            # or a path, or omit for no music
music_gain_db: -14     # optional
music_mood: epic       # optional manifest filter
sfx: true              # transition whooshes (default on when music enabled)
```
