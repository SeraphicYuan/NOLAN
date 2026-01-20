import React, { useEffect, useRef } from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, continueRender, delayRender, staticFile } from 'remotion';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';
import type { DotLottie } from '@lottiefiles/dotlottie-react';

/**
 * Test component to verify dotLottie works with Remotion's frame-by-frame rendering.
 *
 * Key test points:
 * 1. Can we use setFrame() to seek to specific frames?
 * 2. Does it render deterministically (no flickering)?
 * 3. Do expressions work (if present in the Lottie file)?
 */
export const LottieTest: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const dotLottieRef = useRef<DotLottie | null>(null);
  const [handle] = React.useState(() => delayRender('Loading Lottie'));
  const [isLoaded, setIsLoaded] = React.useState(false);
  const [totalFrames, setTotalFrames] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);

  // Use local Lottie file via staticFile
  // Cyberpunk v2 with proper color transformation
  const lottieUrl = staticFile('sample_cyberpunk2.json');

  // Handle dotLottie instance
  const dotLottieRefCallback = (dotLottie: DotLottie | null) => {
    dotLottieRef.current = dotLottie;

    if (dotLottie) {
      // Listen for load event
      dotLottie.addEventListener('load', () => {
        const frames = dotLottie.totalFrames;
        console.log(`[dotLottie] Loaded - Total frames: ${frames}`);
        setTotalFrames(frames);
        setIsLoaded(true);

        // Stop autoplay - we control frames manually
        dotLottie.pause();

        continueRender(handle);
      });

      dotLottie.addEventListener('loadError', (err) => {
        console.error('[dotLottie] Load error:', err);
        setError(`Failed to load: ${err}`);
        continueRender(handle);
      });
    }
  };

  // Sync dotLottie frame with Remotion's current frame
  useEffect(() => {
    if (!dotLottieRef.current || !isLoaded || totalFrames === 0) {
      return;
    }

    // Map Remotion frame to Lottie frame
    // If Lottie has different duration, we need to map proportionally
    const progress = frame / durationInFrames;
    const lottieFrame = Math.floor(progress * totalFrames);

    // Use setFrame to seek to specific frame
    dotLottieRef.current.setFrame(lottieFrame);

    // Debug log every 30 frames
    if (frame % 30 === 0) {
      console.log(`[dotLottie] Remotion frame ${frame} -> Lottie frame ${lottieFrame}`);
    }
  }, [frame, isLoaded, totalFrames, durationInFrames]);

  return (
    <AbsoluteFill style={{
      backgroundColor: '#0f0a1a',
      background: 'linear-gradient(135deg, #0f0a1a 0%, #1a0a2e 50%, #0a1a2e 100%)'
    }}>
      {/* Lottie animation container */}
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ width: 600, height: 600 }}>
          <DotLottieReact
            src={lottieUrl}
            dotLottieRefCallback={dotLottieRefCallback}
            autoplay={false}
            loop={false}
            useFrameInterpolation={false}
            style={{ width: '100%', height: '100%' }}
          />
        </div>
      </AbsoluteFill>

      {/* Debug overlay */}
      <AbsoluteFill style={{ padding: 40 }}>
        <div style={{
          background: 'rgba(0,0,0,0.7)',
          padding: '16px 24px',
          borderRadius: 8,
          color: '#ffffff',
          fontFamily: 'monospace',
          fontSize: 18,
        }}>
          <div>Remotion Frame: {frame} / {durationInFrames}</div>
          <div>Lottie Frames: {totalFrames}</div>
          <div>FPS: {fps}</div>
          <div>Status: {error ? `Error: ${error}` : isLoaded ? 'Loaded' : 'Loading...'}</div>
        </div>
      </AbsoluteFill>

      {/* Title */}
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'flex-end', paddingBottom: 60 }}>
        <div style={{
          fontSize: 36,
          fontWeight: 700,
          color: '#00e5ff',
          fontFamily: 'Inter, sans-serif',
          textShadow: '0 0 20px #00e5ff, 0 0 40px #9333ea',
          letterSpacing: '0.1em',
        }}>
          LOTTIE CUSTOMIZATION DEMO
        </div>
        <div style={{
          fontSize: 18,
          color: '#ec4899',
          fontFamily: 'monospace',
          marginTop: 8,
        }}>
          Text + Colors + Timing + Dimensions = All Modified
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
