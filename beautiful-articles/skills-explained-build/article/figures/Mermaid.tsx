// figures/Mermaid.tsx — Tier-1: render Mermaid text to a themed SVG.
//
// Covers the long tail our house figures don't (flowchart / sequence / state / ER /
// gantt / timeline / mindmap / sankey / quadrant / class / kanban / xychart…).
// The agent supplies Mermaid source; this themes it from the active theme's --ra-*
// tokens and renders to inline SVG (offline — mermaid is bundled, no network).
//
// IMPORTANT: import this DIRECTLY (`import { Mermaid } from "../figures/Mermaid"`),
// NOT from the figures barrel — that keeps the heavy mermaid dep out of every other
// article's bundle (only articles that use a Mermaid diagram pay for it).
import { useEffect, useId, useRef, useState } from "react";
import { readPalette } from "./_theme";
import { figureText as tx, figureTokens as T } from "./primitives";

export function Mermaid({ code, caption }: { code: string; caption?: string }) {
  const host = useRef<HTMLDivElement>(null);
  const rawId = useId();
  const [svg, setSvg] = useState<string>("");
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    let alive = true;
    const el = host.current;
    if (!el) return;
    (async () => {
      const p = readPalette(el);
      const mermaid = (await import("mermaid")).default;
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: "base",
        fontFamily: p.fontBody,
        themeVariables: {
          background: p.bg,
          primaryColor: p.surface,
          primaryBorderColor: p.borderStrong,
          primaryTextColor: p.heading,
          secondaryColor: p.surface2,
          secondaryBorderColor: p.border,
          secondaryTextColor: p.heading,
          tertiaryColor: p.accentSoft,
          tertiaryBorderColor: p.borderStrong,
          tertiaryTextColor: p.heading,
          lineColor: p.faint,
          textColor: p.text,
          mainBkg: p.surface,
          nodeBorder: p.borderStrong,
          clusterBkg: p.bg,
          clusterBorder: p.border,
          noteBkgColor: p.accentSoft,
          noteTextColor: p.heading,
          noteBorderColor: p.borderStrong,
          actorBkg: p.surface,
          actorBorder: p.borderStrong,
          actorTextColor: p.heading,
          edgeLabelBackground: p.bg,
        },
      });
      try {
        const id = "ra-mmd-" + rawId.replace(/[^a-zA-Z0-9]/g, "");
        const { svg: out } = await mermaid.render(id, code.trim());
        if (alive) setSvg(out);
      } catch (e) {
        if (alive) setErr(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      alive = false;
    };
  }, [code, rawId]);

  return (
    <figure style={{ margin: 0 }}>
      <div
        ref={host}
        className="ra-mermaid"
        style={{ width: "100%", overflowX: "auto", lineHeight: 0 }}
        // svg is produced by mermaid from the trusted, author-supplied diagram source
        {...(svg ? { dangerouslySetInnerHTML: { __html: svg } } : {})}
      >
        {svg ? undefined : (
          <span style={{ fontSize: tx("sm"), color: err ? T.muted : T.faint, lineHeight: 1.4 }}>
            {err ? `diagram error: ${err}` : "rendering diagram…"}
          </span>
        )}
      </div>
      {caption && (
        <figcaption
          style={{ marginTop: "var(--ra-space-2, .5rem)", fontSize: tx("xs"), color: T.faint, fontFamily: T.label }}
        >
          {caption}
        </figcaption>
      )}
    </figure>
  );
}
