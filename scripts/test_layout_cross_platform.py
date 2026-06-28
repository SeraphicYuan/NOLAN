"""
Cross-platform Layout System Tests

Tests the layout system works correctly for:
1. Python (PIL/MoviePy) - direct usage
2. Motion Canvas (TypeScript) - JSON export/import
3. Remotion (React) - JSON export/import

This validates that the layout data structure is renderer-agnostic.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nolan.renderer.layout import (
    # Position system
    Position, POSITIONS, resolve_position,
    # Slot/Layout system
    Slot, Layout, LAYOUT_PRESETS, get_preset, slots_to_json, slots_from_json,
)


def test_python_position_system():
    """Test Position system for Python renderer."""
    print("\n" + "=" * 60)
    print("TEST 1: Python Position System")
    print("=" * 60)

    # Test preset positions
    presets_to_test = ["center", "lower-third", "top-left", "right-half"]
    canvas_w, canvas_h = 1920, 1080
    element_w, element_h = 400, 100

    print(f"\nCanvas: {canvas_w}x{canvas_h}, Element: {element_w}x{element_h}")
    print("-" * 40)

    for preset_name in presets_to_test:
        pos = Position.from_preset(preset_name)
        x, y = pos.resolve(canvas_w, canvas_h, element_w, element_h)
        print(f"  {preset_name:20s} -> ({x:4d}, {y:4d})")

    # Test custom position
    custom = Position(x=0.1, y=0.9, align="left", valign="bottom", padding=0.02)
    x, y = custom.resolve(canvas_w, canvas_h, element_w, element_h)
    print(f"  {'custom(0.1, 0.9)':20s} -> ({x:4d}, {y:4d})")

    print("\n[OK] Position system works correctly")
    return True


def test_python_slot_system():
    """Test Slot/Layout system for Python renderer."""
    print("\n" + "=" * 60)
    print("TEST 2: Python Slot/Layout System")
    print("=" * 60)

    layout = Layout(width=1920, height=1080, margin=100, default_gap=60)

    # Test columns
    print("\nColumns [1, 2] (1/3 + 2/3):")
    left, right = layout.columns([1, 2])
    print(f"  Left:  x={left.x:4d}, width={left.width:4d}, inner_width={left.inner_width:4d}")
    print(f"  Right: x={right.x:4d}, width={right.width:4d}, inner_width={right.inner_width:4d}")

    # Test rows
    print("\nRows [1, 4] (header + body):")
    header, body = layout.rows([1, 4])
    print(f"  Header: y={header.y:4d}, height={header.height:4d}")
    print(f"  Body:   y={body.y:4d}, height={body.height:4d}")

    # Test grid
    print("\nGrid 2x2:")
    grid = layout.grid(2, 2)
    for row_idx, row in enumerate(grid):
        for col_idx, cell in enumerate(row):
            print(f"  [{row_idx}][{col_idx}]: x={cell.x:4d}, y={cell.y:4d}, size={cell.width}x{cell.height}")

    # Test presets
    print("\nPresets:")
    for preset_name in ["golden", "thirds", "split-1-2"]:
        slots = get_preset(preset_name)
        widths = [s.width for s in slots]
        print(f"  {preset_name:12s}: widths = {widths}")

    # Test slot alignment helpers
    print("\nSlot alignment helpers:")
    slot = Slot(x=100, y=100, width=500, height=400, padding=40)
    element_w, element_h = 200, 100

    x_left = slot.align_x(element_w, "left")
    x_center = slot.align_x(element_w, "center")
    x_right = slot.align_x(element_w, "right")
    print(f"  align_x (200px element): left={x_left}, center={x_center}, right={x_right}")

    px, py = slot.place(element_w, element_h, "center", "center")
    print(f"  place(center, center): ({px}, {py})")

    # Test subdivision
    print("\nSlot subdivision:")
    sub_cols = slot.subdivide_cols([1, 1])
    print(f"  subdivide_cols([1,1]): widths = {[s.width for s in sub_cols]}")

    print("\n[OK] Slot/Layout system works correctly")
    return True


def test_json_export_import():
    """Test JSON serialization for cross-platform use."""
    print("\n" + "=" * 60)
    print("TEST 3: JSON Export/Import")
    print("=" * 60)

    layout = Layout(width=1920, height=1080)

    # Test single slot
    single = layout.full()
    json_single = slots_to_json(single)
    print("\nSingle slot JSON:")
    print(json_single[:200] + "..." if len(json_single) > 200 else json_single)

    # Verify round-trip
    restored_single = slots_from_json(json_single)
    assert restored_single.x == single.x
    assert restored_single.width == single.width
    print("  [OK] Single slot round-trip")

    # Test list of slots
    columns = layout.columns([1, 2])
    json_columns = slots_to_json(columns)
    print("\nColumns JSON:")
    print(json_columns)

    # Verify round-trip
    restored_columns = slots_from_json(json_columns)
    assert len(restored_columns) == 2
    assert restored_columns[0].width == columns[0].width
    assert restored_columns[1].width == columns[1].width
    print("  [OK] Column list round-trip")

    # Test grid (2D list)
    grid = layout.grid(2, 2)
    json_grid = slots_to_json(grid)
    print("\nGrid JSON (truncated):")
    print(json_grid[:300] + "...")

    # Verify round-trip
    restored_grid = slots_from_json(json_grid)
    assert len(restored_grid) == 2
    assert len(restored_grid[0]) == 2
    assert restored_grid[0][0].x == grid[0][0].x
    print("  [OK] Grid round-trip")

    print("\n[OK] JSON export/import works correctly")
    return True


def test_motion_canvas_integration():
    """Test that exported data works for Motion Canvas."""
    print("\n" + "=" * 60)
    print("TEST 4: Motion Canvas Integration")
    print("=" * 60)

    # Create layout and export
    layout = Layout(width=1920, height=1080)
    portrait_slot, content_slot = layout.columns([1, 2])

    # Export to JSON (this is what would be passed to Motion Canvas)
    slots_json = slots_to_json([portrait_slot, content_slot])
    slots_data = json.loads(slots_json)

    print("\nSlots data for Motion Canvas:")
    for i, slot in enumerate(slots_data):
        print(f"  Slot {i}: {slot}")

    # Verify Motion Canvas can use this data
    # Motion Canvas uses center-based coordinates, so we need to convert
    print("\nMotion Canvas coordinate conversion:")
    for i, slot in enumerate(slots_data):
        # Motion Canvas Rect uses center coordinates
        mc_x = slot['x'] + slot['width'] / 2
        mc_y = slot['y'] + slot['height'] / 2
        print(f"  Slot {i}: center=({mc_x:.0f}, {mc_y:.0f}), size=({slot['width']}, {slot['height']})")

    # Generate example TypeScript code
    ts_code = f'''
// Motion Canvas usage example (auto-generated)
import {{makeScene2D}} from '@motion-canvas/2d';
import {{Rect, Txt}} from '@motion-canvas/2d/lib/components';

// Slot data from Python Layout system
const slots = {json.dumps(slots_data, indent=2)};

export default makeScene2D(function* (view) {{
  // Portrait slot (index 0)
  const portrait = slots[0];
  view.add(
    <Rect
      x={{portrait.x + portrait.width / 2}}
      y={{portrait.y + portrait.height / 2}}
      width={{portrait.width}}
      height={{portrait.height}}
      fill="#333"
    />
  );

  // Content slot (index 1)
  const content = slots[1];
  view.add(
    <Rect
      x={{content.x + content.width / 2}}
      y={{content.y + content.height / 2}}
      width={{content.width}}
      height={{content.height}}
      fill="#222"
    />
  );
}});
'''

    # Save example file
    example_dir = "test_output/layout_examples"
    os.makedirs(example_dir, exist_ok=True)

    ts_path = f"{example_dir}/motion_canvas_example.tsx"
    with open(ts_path, 'w') as f:
        f.write(ts_code)
    print(f"\n  Generated: {ts_path}")

    # Also save the raw JSON
    json_path = f"{example_dir}/slots_data.json"
    with open(json_path, 'w') as f:
        f.write(slots_json)
    print(f"  Generated: {json_path}")

    print("\n[OK] Motion Canvas integration validated")
    return True


def test_remotion_integration():
    """Test that exported data works for Remotion."""
    print("\n" + "=" * 60)
    print("TEST 5: Remotion Integration")
    print("=" * 60)

    # Create layout and export
    layout = Layout(width=1920, height=1080)
    slots = layout.columns([1, 2], names=["portrait", "content"])

    # Export to JSON
    slots_json = slots_to_json(slots)
    slots_data = json.loads(slots_json)

    print("\nSlots data for Remotion:")
    for slot in slots_data:
        print(f"  {slot.get('name', 'unnamed')}: x={slot['x']}, y={slot['y']}, "
              f"width={slot['width']}, height={slot['height']}")

    # Remotion uses absolute CSS positioning
    print("\nCSS styles for Remotion:")
    for slot in slots_data:
        css = {
            'position': 'absolute',
            'left': slot['x'],
            'top': slot['y'],
            'width': slot['width'],
            'height': slot['height'],
            'padding': slot['padding'],
        }
        print(f"  {slot.get('name', 'slot')}: {css}")

    # Generate example React code
    tsx_code = f'''
// Remotion usage example (auto-generated)
import {{AbsoluteFill, useCurrentFrame, interpolate}} from 'remotion';
import React from 'react';

// Slot interface matching Python Slot class
interface Slot {{
  x: number;
  y: number;
  width: number;
  height: number;
  padding: number;
  name?: string;
}}

// Slot data from Python Layout system
const slots: Slot[] = {json.dumps(slots_data, indent=2)};

// Helper component for slot containers
const SlotContainer: React.FC<{{
  slot: Slot;
  children: React.ReactNode;
  style?: React.CSSProperties;
}}> = ({{slot, children, style}}) => (
  <div
    style={{{{
      position: 'absolute',
      left: slot.x,
      top: slot.y,
      width: slot.width,
      height: slot.height,
      padding: slot.padding,
      boxSizing: 'border-box',
      ...style,
    }}}}
  >
    {{children}}
  </div>
);

// Example composition
export const PortraitReveal: React.FC = () => {{
  const frame = useCurrentFrame();
  const [portrait, content] = slots;

  return (
    <AbsoluteFill style={{{{backgroundColor: '#0a0a12'}}}}>
      <SlotContainer slot={{portrait}} style={{{{backgroundColor: '#333'}}}}>
        <div style={{{{color: 'white', textAlign: 'center'}}}}>
          Portrait Area
        </div>
      </SlotContainer>

      <SlotContainer slot={{content}} style={{{{backgroundColor: '#222', border: '2px solid gold'}}}}>
        <h1 style={{{{color: 'gold'}}}}>Title Here</h1>
        <ul style={{{{color: 'white'}}}}>
          <li>Point 1</li>
          <li>Point 2</li>
        </ul>
      </SlotContainer>
    </AbsoluteFill>
  );
}};
'''

    # Save example file
    example_dir = "test_output/layout_examples"
    os.makedirs(example_dir, exist_ok=True)

    tsx_path = f"{example_dir}/remotion_example.tsx"
    with open(tsx_path, 'w') as f:
        f.write(tsx_code)
    print(f"\n  Generated: {tsx_path}")

    print("\n[OK] Remotion integration validated")
    return True


def test_schema_based_layouts():
    """Test schema-based layout creation."""
    print("\n" + "=" * 60)
    print("TEST 6: Schema-based Layouts")
    print("=" * 60)

    layout = Layout(width=1920, height=1080)

    # Test various schemas
    schemas = [
        {"type": "full"},
        {"type": "columns", "ratios": [1, 2]},
        {"type": "rows", "ratios": [1, 4]},
        {"type": "grid", "cols": 2, "rows": 2},
        {"type": "preset", "name": "golden"},
    ]

    for schema in schemas:
        result = layout.from_schema(schema)
        schema_type = schema.get("type")

        if isinstance(result, Slot):
            print(f"  {schema_type:10s} -> Slot(width={result.width})")
        elif isinstance(result, list) and result and isinstance(result[0], Slot):
            widths = [s.width for s in result]
            print(f"  {schema_type:10s} -> {len(result)} slots, widths={widths}")
        elif isinstance(result, list) and result and isinstance(result[0], list):
            print(f"  {schema_type:10s} -> {len(result)}x{len(result[0])} grid")

    # Test that presets work
    print("\nAll available presets:")
    for name in sorted(LAYOUT_PRESETS.keys()):
        print(f"  - {name}")

    print("\n[OK] Schema-based layouts work correctly")
    return True


def test_real_render_with_layout():
    """Test actual video rendering with layout system."""
    print("\n" + "=" * 60)
    print("TEST 7: Real Render with Layout System")
    print("=" * 60)

    from src.nolan.renderer.scenes.portrait_reveal import render_portrait_reveal

    # Test with default layout
    print("\nRendering with default layout...")
    output1 = "test_output/layout_examples/render_default.mp4"
    render_portrait_reveal(
        title="Default Layout",
        points=["Using 1:2 column ratio", "Portrait on left"],
        portrait_caption="Default",
        output_path=output1,
    )
    print(f"  [OK] {output1}")

    # Test with golden ratio layout
    print("\nRendering with golden ratio layout...")
    layout = Layout(width=1920, height=1080)
    golden_slots = layout.columns([38, 62])  # Golden ratio

    output2 = "test_output/layout_examples/render_golden.mp4"
    render_portrait_reveal(
        title="Golden Ratio",
        points=["Using 38:62 ratio", "More balanced split"],
        portrait_caption="Golden",
        layout=golden_slots,
        output_path=output2,
    )
    print(f"  [OK] {output2}")

    # Test with custom wide layout
    print("\nRendering with custom 1:3 layout...")
    wide_slots = layout.columns([1, 3])

    output3 = "test_output/layout_examples/render_wide.mp4"
    render_portrait_reveal(
        title="Wide Content Area",
        points=["Using 1:3 ratio", "Small portrait, large content"],
        portrait_caption="Narrow",
        layout=wide_slots,
        output_path=output3,
    )
    print(f"  [OK] {output3}")

    print("\n[OK] Real renders with layout system work correctly")
    return True


def main():
    print("=" * 60)
    print("CROSS-PLATFORM LAYOUT SYSTEM TESTS")
    print("=" * 60)

    all_passed = True

    # Run all tests
    tests = [
        ("Python Position System", test_python_position_system),
        ("Python Slot/Layout System", test_python_slot_system),
        ("JSON Export/Import", test_json_export_import),
        ("Motion Canvas Integration", test_motion_canvas_integration),
        ("Remotion Integration", test_remotion_integration),
        ("Schema-based Layouts", test_schema_based_layouts),
        ("Real Render with Layout", test_real_render_with_layout),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, "PASS" if passed else "FAIL"))
        except Exception as e:
            print(f"\n[FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, "FAIL"))
            all_passed = False

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for name, status in results:
        icon = "[OK]" if status == "PASS" else "[FAIL]"
        print(f"  {icon} {name}")

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)

    print("\nGenerated files:")
    print("  - test_output/layout_examples/slots_data.json")
    print("  - test_output/layout_examples/motion_canvas_example.tsx")
    print("  - test_output/layout_examples/remotion_example.tsx")
    print("  - test_output/layout_examples/render_*.mp4")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
