
// Motion Canvas usage example (auto-generated)
import {makeScene2D} from '@motion-canvas/2d';
import {Rect, Txt} from '@motion-canvas/2d/lib/components';

// Slot data from Python Layout system
const slots = [
  {
    "x": 100,
    "y": 100,
    "width": 553,
    "height": 880,
    "padding": 40,
    "name": "col0"
  },
  {
    "x": 713,
    "y": 100,
    "width": 1106,
    "height": 880,
    "padding": 40,
    "name": "col1"
  }
];

export default makeScene2D(function* (view) {
  // Portrait slot (index 0)
  const portrait = slots[0];
  view.add(
    <Rect
      x={portrait.x + portrait.width / 2}
      y={portrait.y + portrait.height / 2}
      width={portrait.width}
      height={portrait.height}
      fill="#333"
    />
  );

  // Content slot (index 1)
  const content = slots[1];
  view.add(
    <Rect
      x={content.x + content.width / 2}
      y={content.y + content.height / 2}
      width={content.width}
      height={content.height}
      fill="#222"
    />
  );
});
