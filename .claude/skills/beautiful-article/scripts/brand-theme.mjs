// brand-theme.mjs — recolor a reacticle theme's PALETTE from one brand seed color,
// while keeping the theme's typography + decoration (the "shell"). Uses oklch to
// derive a perceptually-even ramp. Emits article/brand.css scoped to [data-theme=<id>].
//
//   node <skill>/scripts/brand-theme.mjs --theme press --color "#3257d6" [--mode light|dark] [--out article/brand.css]
//   then add  import "./brand.css";  to article/main.tsx AFTER  import "reacticle/styles.css";
//
// Best on the typographic themes (press / tufte / bodoni / vignelli / knuth) whose look
// rides the generic --ra-color-* tokens. The signature-color themes (freddie's yellow,
// sottsass/bayer/fuller's named palettes) keep their identity colors by design — that's a
// feature, not a bug: you don't rebrand Memphis. Output is plain hex (works in any browser).
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

// ---- oklch <-> sRGB (Björn Ottosson's oklab) ----
function hexToOklch(hex) {
  const n = hex.replace("#", "");
  const c = [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16) / 255);
  const lin = (x) => (x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4));
  const [R, G, B] = c.map(lin);
  const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B);
  const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B);
  const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const b = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  let H = (Math.atan2(b, a) * 180) / Math.PI;
  if (H < 0) H += 360;
  return { L, C: Math.hypot(a, b), H };
}
function oklchToHex(L, C, H) {
  const hr = (H * Math.PI) / 180;
  const a = C * Math.cos(hr), b = C * Math.sin(hr);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  let r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  let g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  let bl = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;
  const gamma = (x) => (x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(Math.max(0, x), 1 / 2.4) - 0.055);
  const h2 = (x) => Math.round(Math.max(0, Math.min(1, gamma(x))) * 255).toString(16).padStart(2, "0");
  return "#" + h2(r) + h2(g) + h2(bl);
}
const ok = (L, C, H) => oklchToHex(L, C, H);

// ---- args ----
const args = Object.fromEntries(
  process.argv.slice(2).join(" ").split("--").filter(Boolean).map((s) => {
    const [k, ...v] = s.trim().split(/\s+/);
    return [k, v.join(" ") || true];
  })
);
const theme = args.theme;
const seed = (args.color || "").trim();
const mode = args.mode === "dark" ? "dark" : "light";
const out = args.out || "article/brand.css";
if (!theme || !/^#?[0-9a-fA-F]{6}$/.test(seed.replace("#", ""))) {
  console.error('usage: node brand-theme.mjs --theme <id> --color "#rrggbb" [--mode light|dark]');
  process.exit(1);
}
const { C, H } = hexToOklch(seed.startsWith("#") ? seed : "#" + seed);
const accentC = Math.min(C, 0.16); // tame neon
const softC = Math.min(C, 0.06);
const neutralC = Math.min(C, 0.02); // hue-tinted neutrals

// role -> oklch L (chroma), per mode. Hue H is shared (brand).
const L = mode === "dark"
  ? { bg: 0.20, bgTint: 0.22, surface: 0.25, surface2: 0.30, border: 0.34, borderStrong: 0.42, heading: 0.96, text: 0.90, muted: 0.70, faint: 0.55, accentL: 0.72, accentSoftL: 0.32 }
  : { bg: 0.992, bgTint: 0.985, surface: 0.965, surface2: 0.935, border: 0.905, borderStrong: 0.83, heading: 0.23, text: 0.31, muted: 0.52, faint: 0.66, accentL: 0.52, accentSoftL: 0.93 };

const accentL = Math.max(0.36, Math.min(L.accentL, 0.66));
const accent = ok(accentL, accentC, H);
const accentContrast = accentL < 0.6 ? ok(0.99, 0.01, H) : ok(0.20, neutralC, H);

const tokens = {
  "--ra-color-bg": ok(L.bg, mode === "dark" ? neutralC : 0.004, H),
  "--ra-color-bg-tint": ok(L.bgTint, 0.006, H),
  "--ra-color-surface": ok(L.surface, 0.006, H),
  "--ra-color-surface-2": ok(L.surface2, 0.008, H),
  "--ra-color-border": ok(L.border, 0.008, H),
  "--ra-color-border-strong": ok(L.borderStrong, 0.01, H),
  "--ra-color-heading": ok(L.heading, neutralC, H),
  "--ra-color-text": ok(L.text, neutralC, H),
  "--ra-color-muted": ok(L.muted, neutralC, H),
  "--ra-color-faint": ok(L.faint, Math.min(neutralC, 0.015), H),
  "--ra-color-accent": accent,
  "--ra-color-accent-strong": ok(Math.max(0.28, accentL - 0.1), accentC, H),
  "--ra-color-accent-soft": ok(L.accentSoftL, softC, H),
  "--ra-color-accent-contrast": accentContrast,
  // info maps to brand so Asides etc. pick up the brand; risk/warn/success left to the theme.
  "--ra-color-info": accent,
  "--ra-color-info-soft": ok(L.accentSoftL, softC, H),
};

const css =
  `/* Brand recolor for [data-theme="${theme}"] · seed ${seed} · ${mode} mode (oklch-derived).\n` +
  `   Keeps the theme's typography + decoration; overrides only the --ra-color-* palette.\n` +
  `   Import AFTER reacticle/styles.css in main.tsx. */\n` +
  `[data-theme="${theme}"] {\n` +
  Object.entries(tokens).map(([k, v]) => `  ${k}: ${v};`).join("\n") +
  `\n}\n`;

mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, css);
console.log(`▸ wrote ${out} (theme ${theme}, seed ${seed}, ${mode})`);
console.log(`  accent ${accent} · bg ${tokens["--ra-color-bg"]} · text ${tokens["--ra-color-text"]} · on-accent ${accentContrast}`);
console.log(`  next: add  import "./brand.css";  to article/main.tsx AFTER reacticle/styles.css`);
