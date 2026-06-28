// figures/Inline.tsx — inline article components that live inside running prose <p>.
//
// Rules (theme-portable + offline + SSR-safe):
//   • Style ONLY via --ra-* tokens with fallbacks. NEVER theme-specific tokens.
//   • The hover/focus popover is PURE CSS (:hover / :focus-within) — no useState / effects.
//     useId() gives each instance a unique class so the injected <style> rules never collide.
//   • Trigger is keyboard-focusable (tabIndex 0) so :focus-within reveals the popover too.
import { useId } from "react";
import type { ReactNode } from "react";
import { figureTokens as T, figureRadius as rad, figureText as tx } from "./primitives";

// Shared CSS for the popover behaviour, scoped to a per-instance class.
function popoverCss(cls: string): string {
  return [
    `.${cls}{position:relative}`,
    `.${cls} .ra-pop{`,
    `position:absolute;left:50%;bottom:calc(100% + 0.4rem);transform:translateX(-50%) translateY(0.25rem);`,
    `z-index:50;width:max-content;max-width:16rem;`,
    `padding:0.5rem 0.65rem;`,
    `background:${T.surface};color:${T.text};`,
    `border:1px solid ${T.borderStrong};border-radius:${rad("md")};`,
    `box-shadow:0 6px 20px var(--ra-shadow, rgba(0,0,0,0.18));`,
    `font-size:${tx("sm")};line-height:1.45;font-weight:400;text-align:left;white-space:normal;`,
    `opacity:0;visibility:hidden;pointer-events:none;`,
    `transition:opacity 0.14s ease, transform 0.14s ease, visibility 0.14s;`,
    `}`,
    `.${cls}:hover .ra-pop,.${cls}:focus-within .ra-pop{`,
    `opacity:1;visibility:visible;transform:translateX(-50%) translateY(0);`,
    `}`,
  ].join("");
}

// Inline glossary term: dotted-underlined word; hover/focus reveals its definition.
export function Term(props: { children: ReactNode; def: ReactNode }): JSX.Element {
  const cls = `ra-term-${useId().replace(/[:]/g, "")}`;
  return (
    <span className={cls} style={{ display: "inline" }}>
      <style dangerouslySetInnerHTML={{ __html: popoverCss(cls) }} />
      <span
        tabIndex={0}
        role="term"
        aria-label="Glossary term"
        style={{
          borderBottom: `1px dotted ${T.faint}`,
          cursor: "help",
          outline: "none",
        }}
      >
        {props.children}
      </span>
      <span className="ra-pop" role="tooltip" style={{ color: T.heading }}>
        {props.def}
      </span>
    </span>
  );
}

// Inline footnote/citation: a small superscript marker (number or ●); hover/focus reveals the note.
export function Footnote(props: { children?: ReactNode; marker?: ReactNode }): JSX.Element {
  const cls = `ra-fn-${useId().replace(/[:]/g, "")}`;
  const marker = props.marker ?? "●";
  return (
    <span className={cls} style={{ display: "inline" }}>
      <style dangerouslySetInnerHTML={{ __html: popoverCss(cls) }} />
      <sup
        tabIndex={0}
        role="button"
        aria-label="Footnote"
        style={{
          fontSize: tx("xs"),
          color: T.accent,
          cursor: "help",
          fontWeight: 600,
          padding: "0 0.1em",
          outline: "none",
        }}
      >
        {marker}
      </sup>
      <span className="ra-pop" role="tooltip">
        {props.children}
      </span>
    </span>
  );
}
