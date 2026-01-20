/**
 * dotLottie + Remotion Integration Spike Test
 *
 * This test verifies:
 * 1. dotlottie-react can be bundled with Remotion
 * 2. setFrame() works for frame-accurate video export
 * 3. The animation renders without flickering
 *
 * Run: npx ts-node --esm test/dotlottie-spike/run-test.ts
 */

import * as fs from 'fs';
import * as path from 'path';
import { bundle } from '@remotion/bundler';
import { renderMedia, selectComposition } from '@remotion/renderer';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function runTest() {
  console.log('='.repeat(60));
  console.log('dotLottie + Remotion Integration Spike');
  console.log('='.repeat(60));
  console.log('');

  const entryPoint = path.join(__dirname, 'src', 'index.tsx');
  const outputDir = path.join(__dirname, 'output');
  const outputPath = path.join(outputDir, 'dotlottie-test.mp4');

  // Ensure output directory exists
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  console.log('[1/4] Entry point:', entryPoint);
  console.log('[1/4] Output:', outputPath);
  console.log('');

  try {
    // Step 1: Bundle
    console.log('[2/4] Bundling Remotion project...');
    const bundleStart = Date.now();
    const publicDir = path.join(__dirname, 'public');
    const bundleLocation = await bundle({
      entryPoint,
      publicDir,
      onProgress: (progress) => {
        if (progress === 100) {
          console.log('      Bundle complete!');
        }
      },
    });
    console.log(`      Bundle time: ${((Date.now() - bundleStart) / 1000).toFixed(1)}s`);
    console.log('');

    // Step 2: Select composition
    console.log('[3/4] Selecting composition...');
    const composition = await selectComposition({
      serveUrl: bundleLocation,
      id: 'LottieTest',
    });
    console.log(`      Composition: ${composition.id}`);
    console.log(`      Duration: ${composition.durationInFrames} frames @ ${composition.fps} fps`);
    console.log(`      Size: ${composition.width}x${composition.height}`);
    console.log('');

    // Step 3: Render
    console.log('[4/4] Rendering video...');
    const renderStart = Date.now();
    await renderMedia({
      serveUrl: bundleLocation,
      composition,
      codec: 'h264',
      outputLocation: outputPath,
      onProgress: ({ progress }) => {
        const pct = Math.round(progress * 100);
        process.stdout.write(`\r      Progress: ${pct}%`);
      },
    });
    console.log('');
    console.log(`      Render time: ${((Date.now() - renderStart) / 1000).toFixed(1)}s`);
    console.log('');

    // Step 4: Verify output
    if (fs.existsSync(outputPath)) {
      const stats = fs.statSync(outputPath);
      console.log('='.repeat(60));
      console.log('SUCCESS!');
      console.log('='.repeat(60));
      console.log(`Output: ${outputPath}`);
      console.log(`Size: ${(stats.size / 1024 / 1024).toFixed(2)} MB`);
      console.log('');
      console.log('Next steps:');
      console.log('1. Open the video and verify animation plays smoothly');
      console.log('2. Check for any flickering or frame skips');
      console.log('3. If successful, dotLottie integration is viable!');
    } else {
      console.error('ERROR: Output file not created');
      process.exit(1);
    }
  } catch (error) {
    console.error('');
    console.error('='.repeat(60));
    console.error('FAILED');
    console.error('='.repeat(60));
    console.error(error);
    process.exit(1);
  }
}

runTest();
