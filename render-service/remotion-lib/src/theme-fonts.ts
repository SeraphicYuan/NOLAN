// Theme-driven font loading (the font-drift fix).
//
// Themes declare typography as CSS token stacks, but a browser can only use
// fonts the bundle actually LOADS — index.tsx's static list covered seven
// families, so any theme wanting others (creative-voltage → Syne, Space
// Mono, Noto Sans SC) silently fell back to Inter-or-system and the video's
// type drifted from the theme's design. stage.mjs now writes the active
// theme's first-choice families into _active-theme.json; this module loads
// each dynamically from @remotion/google-fonts (delayRender-managed, so
// frames wait). A family Google Fonts doesn't carry is WARNED, never
// silently skipped — drop a self-hosted @font-face in base.css for those.
import {getAvailableFonts} from '@remotion/google-fonts';
import active from './styles/_active-theme.json';

const wanted: string[] = ((active as Record<string, unknown>).fonts as string[]) || [];
const catalog = getAvailableFonts();

for (const family of wanted) {
  const entry = catalog.find((f) => f.fontFamily === family);
  if (!entry) {
    // eslint-disable-next-line no-console
    console.warn(`[theme-fonts] "${family}" is not on Google Fonts — text in `
      + `this family will fall back (self-host it in base.css if it matters)`);
    continue;
  }
  entry
    .load()
    .then((mod) => mod.loadFont())
    // eslint-disable-next-line no-console
    .catch((e) => console.warn(`[theme-fonts] failed to load "${family}":`, e));
}
