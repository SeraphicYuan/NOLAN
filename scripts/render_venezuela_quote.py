#!/usr/bin/env python3
"""
Render the Venezuela quote scene using a Lottie template.

This script demonstrates NOLAN's template automation:
1. Load a Lottie template with schema
2. Customize it with scene-specific content
3. Render to video via the render service

Scene: Hook scene_005 from Venezuela project
Quote: "WE ARE TIRED"
Template: Modern Lower Third (lower-thirds/modern.json)
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nolan.lottie import (
    load_lottie,
    load_schema,
    render_template,
    save_lottie,
    replace_text,
    get_lottie_info,
)


def main():
    # Paths
    project_root = Path(__file__).parent.parent
    template_path = project_root / "assets/common/lottie/lower-thirds/modern.json"
    output_dir = project_root / "test_output"
    output_dir.mkdir(exist_ok=True)

    # Scene data from Venezuela project
    scene = {
        "id": "hook_scene_005",
        "narration": "Listen to what Maria Rodriguez, a resident of Caracas, said recently...",
        "quote": "WE ARE TIRED",
        "speaker": "Maria Rodriguez, Caracas Resident",
    }

    print("=" * 60)
    print("NOLAN Template Automation Demo")
    print("=" * 60)
    print(f"\nScene: {scene['id']}")
    print(f"Quote: \"{scene['quote']}\"")
    print(f"Template: {template_path.name}")

    # 1. Load and inspect the template
    print("\n--- Step 1: Load Template ---")
    info = get_lottie_info(template_path)
    print(f"Template: {info['name']}")
    print(f"Size: {info['width']}x{info['height']}")
    print(f"Duration: {info['duration_seconds']}s @ {info['fps']}fps")
    print(f"Text layers: {len(info['text_layers'])}")
    for tl in info['text_layers']:
        print(f"  - {tl['name']}: \"{tl['text']}\"")

    # 2. Load schema
    print("\n--- Step 2: Load Schema ---")
    schema = load_schema(template_path)
    if schema:
        print(f"Schema: {schema['name']}")
        print(f"Fields: {list(schema['fields'].keys())}")
        for name, field in schema['fields'].items():
            print(f"  - {name}: {field['type']} (default: \"{field.get('default', '')}\")")
    else:
        print("No schema found - using direct text replacement")

    # 3. Customize the template
    print("\n--- Step 3: Customize Template ---")
    output_json = output_dir / f"{scene['id']}_lower_third.json"

    if schema:
        # Use schema-based customization
        try:
            rendered = render_template(
                template_path,
                output_path=output_json,
                headline=scene['quote']
            )
            print(f"Rendered with schema: headline=\"{scene['quote']}\"")
        except ValueError as e:
            print(f"Schema error: {e}")
            # Fallback to direct replacement
            data = load_lottie(template_path)
            replace_text(data, "BREAKING NEWS", scene['quote'])
            save_lottie(data, output_json)
            print(f"Used direct text replacement")
    else:
        # Direct text replacement
        data = load_lottie(template_path)
        count = replace_text(data, "BREAKING NEWS", scene['quote'])
        save_lottie(data, output_json)
        print(f"Replaced {count} text occurrences")

    # The template has TWO text layers with same text (for depth effect)
    # The schema only updates layer[0], so we need to update layer[1] too
    data = load_lottie(output_json)
    # Check if layer[1] still has old text
    layers = data.get('layers', [])
    if len(layers) > 1:
        layer1_text = layers[1].get('t', {}).get('d', {}).get('k', [{}])[0].get('s', {}).get('t', '')
        if layer1_text == "BREAKING NEWS":
            # Update layer[1] as well
            replace_text(data, "BREAKING NEWS", scene['quote'])
            save_lottie(data, output_json)
            print("Updated secondary text layer for depth effect")

    print(f"\nCustomized template saved to: {output_json}")

    # 4. Verify the customization
    print("\n--- Step 4: Verify ---")
    final_info = get_lottie_info(output_json)
    print("Text layers after customization:")
    for tl in final_info['text_layers']:
        print(f"  - {tl['name']}: \"{tl['text']}\"")

    # 5. Generate render spec for render-service
    print("\n--- Step 5: Generate Render Spec ---")
    render_spec = {
        "engine": "remotion",
        "width": 1920,
        "height": 1080,
        "duration": 7.0,  # Match template duration
        "data": {
            "lottie_path": str(output_json.absolute()),
            "lottie": {
                "width": 1920,  # Scale up for full HD
                "height": 1080,
                "background": "#1a1a1a",  # Dark background for contrast
            }
        }
    }

    render_spec_path = output_dir / f"{scene['id']}_render_spec.json"
    with open(render_spec_path, 'w') as f:
        json.dump(render_spec, f, indent=2)
    print(f"Render spec saved to: {render_spec_path}")

    print("\n--- Next Steps ---")
    print("To render to video, start the render service and run:")
    print(f'  curl -X POST http://localhost:3000/render -H "Content-Type: application/json" -d @{render_spec_path}')
    print("\nOr use the Python API:")
    print("""
import httpx
with open(render_spec_path) as f:
    spec = json.load(f)
response = httpx.post("http://localhost:3000/render", json=spec)
print(response.json())
""")

    print("\n" + "=" * 60)
    print("Template customization complete!")
    print("=" * 60)

    return output_json, render_spec_path


if __name__ == "__main__":
    main()
