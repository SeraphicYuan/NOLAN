# Assets Directory

Visual assets for NOLAN video essay effects, organized by style.

## Structure

```
assets/
├── styles/                    # Style-specific assets
│   ├── noir-essay/
│   │   ├── icons/            # Style-specific icons
│   │   ├── card-bg.svg       # Styled card background
│   │   └── staircase-arrow.svg
│   ├── cold-data/
│   ├── modern-creator/
│   ├── podcast-visual/
│   └── ...
├── common/                    # Shared assets (fallback for all styles)
│   ├── icons/                # Common icons
│   │   ├── check.svg
│   │   ├── star.svg
│   │   ├── arrow-up.svg
│   │   └── ...
│   └── shapes/               # Common shapes
└── README.md
```

## Usage

```python
from nolan.assets import asset_manager

# Get asset path (falls back to common if style-specific doesn't exist)
path = asset_manager.get_asset("noir-essay", "icons/check.svg")

# Get SVG content directly
svg = asset_manager.get_asset_content("noir-essay", "card-bg.svg")

# Convenience method for icons
icon_path = asset_manager.get_icon("noir-essay", "star")  # .svg auto-added

# List available assets
assets = asset_manager.list_assets("noir-essay")
icons = asset_manager.list_assets("noir-essay", category="icons")
```

## Asset Lookup Order

1. `assets/styles/{style_id}/{asset_name}` - Style-specific version
2. `assets/common/{asset_name}` - Common fallback

## Adding New Assets

### Common Icons
Add to `assets/common/icons/`. Available to all styles.

### Style-Specific Assets
Add to `assets/styles/{style_id}/`. Only used when that style is active.

### Asset Guidelines

- **Icons**: SVG format, 24x24 viewBox, use `currentColor` for stroke/fill
- **Backgrounds**: SVG preferred, can use PNG for complex textures
- **Naming**: lowercase, hyphen-separated (e.g., `arrow-up.svg`, `card-bg.svg`)

## Available Common Icons

| Icon | File | Description |
|------|------|-------------|
| ✓ | `check.svg` | Checkmark |
| ★ | `star.svg` | Star |
| ↑ | `arrow-up.svg` | Up arrow |
| 📈 | `trending-up.svg` | Trending/growth |
| </> | `code.svg` | Code/development |
| 🗄 | `database.svg` | Data/database |
| 👥 | `users.svg` | Users/community |
| ⚡ | `zap.svg` | Lightning/speed |
| 🏆 | `award.svg` | Award/achievement |

## Future: Database-Backed Asset Management

For larger asset libraries with search/tagging needs, a database-backed system is planned. See `docs/plans/2026-01-19-asset-vs-code-graphics.md` for details.
