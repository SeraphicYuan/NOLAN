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

// Load ONLY the weights/subsets the themes actually use. An unconstrained
// loadFont() pulls every unicode-range slice — Noto Serif SC alone made 808
// network requests, which stalled headless-browser setup past its 30s
// timeout once Google started throttling (renders died with "Timed out
// setting up the headless browser"). CJK families get their CJK subset;
// everything gets latin.
const CJK = /(SC|TC|JP|KR)$/;

for (const family of wanted) {
  const entry = catalog.find((f) => f.fontFamily === family);
  if (!entry) {
    // eslint-disable-next-line no-console
    console.warn(`[theme-fonts] "${family}" is not on Google Fonts — text in `
      + `this family will fall back (self-host it in base.css if it matters)`);
    continue;
  }
  const subsets = CJK.test(family)
    ? ['latin', 'chinese-simplified']
    : ['latin', 'latin-ext'];
  entry
    .load()
    .then((mod) => {
      type Info = {fonts: Record<string, Record<string, Record<string, unknown>>>};
      const m = mod as {loadFont: (s?: string, o?: object) => unknown;
                        getInfo?: () => Info};
      const info = m.getInfo?.();
      const styles = info?.fonts ? Object.keys(info.fonts) : [];
      const style = styles.includes('normal') ? 'normal' : styles[0];
      if (!info || !style) {
        return m.loadFont();                    // no manifest — old behavior
      }
      const availWeights = Object.keys(info.fonts[style] || {});
      const weights = ['400', '700'].filter((w) => availWeights.includes(w));
      const availSubsets = new Set<string>();
      for (const w of availWeights) {
        for (const s of Object.keys(info.fonts[style][w] || {})) {
          availSubsets.add(s);
        }
      }
      const pick = subsets.filter((s) => availSubsets.has(s));
      return m.loadFont(style, {
        weights: weights.length ? weights : availWeights.slice(0, 2),
        subsets: pick.length ? pick : undefined,
        ignoreTooManyRequestsWarning: true,
      });
    })
    // eslint-disable-next-line no-console
    .catch((e) => console.warn(`[theme-fonts] failed to load "${family}":`, e));
}
