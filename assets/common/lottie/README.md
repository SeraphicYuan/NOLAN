# Lottie Animation Library

This directory contains reusable Lottie animation templates for NOLAN video production.

## Directory Structure

```
lottie/
├── lower-thirds/     # Speaker names, titles, labels
├── title-cards/      # Section headers, intro cards
├── transitions/      # Scene transitions, wipes
├── icons/            # Animated icons, indicators
└── data-callouts/    # Stats, numbers, progress bars
```

## Template Guidelines

### Naming Convention
- Use lowercase with hyphens: `modern-lower-third.json`
- Include style variant: `simple-fade.json`, `bold-slide.json`

### Design Requirements
- Resolution: Design at 1920x1080
- Frame rate: 30 or 60 fps preferred
- Keep text as text layers (not outlines) for customization
- Use descriptive layer names for easy identification

### Customizable Properties
Templates should support customization of:
- Text content (layer names: "Title", "Subtitle", "Name", etc.)
- Colors (primary, secondary, accent)
- Duration (can be extended/shortened)

### Slot IDs (Optional)
For advanced theming, add slot IDs (`sid`) to properties:
```json
{
  "ty": "fl",
  "c": {
    "sid": "primary_color",
    "k": [0.012, 0.663, 0.957, 1]
  }
}
```

## Usage in Scene Plans

```json
{
  "visual_type": "lottie",
  "lottie_template": "assets/common/lottie/lower-thirds/modern.json",
  "lottie_config": {
    "text": {
      "Name": "John Smith",
      "Title": "CEO, Acme Corp"
    },
    "colors": {
      "#0077B6": "#FF5500"
    },
    "duration_seconds": 3
  }
}
```

## Python Customization

```python
from nolan.lottie import customize_lottie

customize_lottie(
    'assets/common/lottie/lower-thirds/modern.json',
    'output/scene_01_lower_third.json',
    text_replacements={'Name': 'Jane Doe'},
    color_map={'#0077B6': '#FF5500'},
    duration_seconds=4
)
```

## Resources

- [LottieFiles](https://lottiefiles.com/) - Free animations
- [docs/LOTTIE_INTEGRATION.md](../../../docs/LOTTIE_INTEGRATION.md) - Full integration guide
