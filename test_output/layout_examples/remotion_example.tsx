
// Remotion usage example (auto-generated)
import {AbsoluteFill, useCurrentFrame, interpolate} from 'remotion';
import React from 'react';

// Slot interface matching Python Slot class
interface Slot {
  x: number;
  y: number;
  width: number;
  height: number;
  padding: number;
  name?: string;
}

// Slot data from Python Layout system
const slots: Slot[] = [
  {
    "x": 100,
    "y": 100,
    "width": 553,
    "height": 880,
    "padding": 40,
    "name": "portrait"
  },
  {
    "x": 713,
    "y": 100,
    "width": 1106,
    "height": 880,
    "padding": 40,
    "name": "content"
  }
];

// Helper component for slot containers
const SlotContainer: React.FC<{
  slot: Slot;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({slot, children, style}) => (
  <div
    style={{
      position: 'absolute',
      left: slot.x,
      top: slot.y,
      width: slot.width,
      height: slot.height,
      padding: slot.padding,
      boxSizing: 'border-box',
      ...style,
    }}
  >
    {children}
  </div>
);

// Example composition
export const PortraitReveal: React.FC = () => {
  const frame = useCurrentFrame();
  const [portrait, content] = slots;

  return (
    <AbsoluteFill style={{backgroundColor: '#0a0a12'}}>
      <SlotContainer slot={portrait} style={{backgroundColor: '#333'}}>
        <div style={{color: 'white', textAlign: 'center'}}>
          Portrait Area
        </div>
      </SlotContainer>

      <SlotContainer slot={content} style={{backgroundColor: '#222', border: '2px solid gold'}}>
        <h1 style={{color: 'gold'}}>Title Here</h1>
        <ul style={{color: 'white'}}>
          <li>Point 1</li>
          <li>Point 2</li>
        </ul>
      </SlotContainer>
    </AbsoluteFill>
  );
};
