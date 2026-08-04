/**
 * AntV infographic spec -> SVG string. The WHOLE "engine".
 *
 * Replaces the 2026-01 architecture (Express + job queue + polling + puppeteer) with a pure
 * function: @antv/infographic >=0.2.19 ships an `./ssr` export that renders through a linkedom
 * DOM shim, so no browser and no service are involved.
 *
 *   node render_svg.mjs <spec.json> <out.svg>
 *
 * Failures are LOUD: any render error exits non-zero with the message on stderr. There is no
 * partial-SVG-on-failure path — a broken spec must not produce a file that looks like a success.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { renderToString } from '@antv/infographic/ssr';
import { setDefaultFont } from '@antv/infographic';

const [, , specPath, outPath] = process.argv;

if (!specPath || !outPath) {
  console.error('usage: node render_svg.mjs <spec.json> <out.svg>');
  process.exit(2);
}

let spec;
try {
  spec = JSON.parse(readFileSync(specPath, 'utf-8'));
} catch (e) {
  console.error(`spec unreadable (${specPath}): ${e.message}`);
  process.exit(2);
}

// `_nolan` carries out-of-band knobs that are API calls rather than spec fields. The font is the
// load-bearing one: the library defaults to 'Alibaba PuHuiTi' and, because that family IS in its
// font registry, emits a remote `<?xml-stylesheet href="https://assets.antv.antgroup.com/...">`
// into every artifact. Setting an unregistered family (i.e. a NOLAN theme face) both applies our
// type AND leaves the registry empty, so no remote reference is produced at all.
const nolan = spec._nolan || {};
delete spec._nolan;
if (nolan.font) setDefaultFont(nolan.font);

try {
  const svg = await renderToString(spec);
  if (!svg || !svg.includes('<svg')) {
    // renderToString resolving with something that is not an SVG is a silent-failure shape.
    // Refuse it rather than writing a file the caller would trust.
    console.error(`render returned no SVG (got ${String(svg).slice(0, 80)})`);
    process.exit(1);
  }
  // The library prepends `<?xml-stylesheet href="https://assets.antgroup.com/...">` for every font
  // family it used. That is a REMOTE dependency baked into the artifact: the SVG is not
  // self-contained, and anything rendering it reaches out to a CDN. NOLAN supplies its own theme
  // fonts, so report every such reference rather than shipping it silently.
  const remote = Array.from(svg.matchAll(/<\?xml-stylesheet\s+href="([^"]+)"/g), (m) => m[1]);
  for (const url of remote) console.error(`remote-font-ref: ${url}`);
  writeFileSync(outPath, svg, 'utf-8');
  console.error(`ok ${outPath} (${svg.length} bytes, ${remote.length} remote font refs)`);
} catch (e) {
  console.error(`render failed: ${e && e.stack ? e.stack : e}`);
  process.exit(1);
}
