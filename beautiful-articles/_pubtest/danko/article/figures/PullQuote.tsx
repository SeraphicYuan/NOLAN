// figures/PullQuote.tsx — large decorative typographic pull-quote (not an attributed Quote).
import type { CSSProperties, ReactNode } from "react";
import { FStack, FLabel, figureTokens as T, figureSpace as sp, figureText as tx } from "./primitives";

/** Oversized heading-font pull-quote with an accent bar + big quote mark; optional cite. */
export function PullQuote(props: { children: ReactNode; cite?: ReactNode }): JSX.Element {
  const { children, cite } = props;
  const wrapStyle: CSSProperties = {
    borderLeft: `0.35rem solid ${T.accent}`,
    paddingLeft: sp(5),
    position: "relative",
  };
  const markStyle: CSSProperties = {
    fontFamily: T.heads,
    fontSize: "3.5rem",
    lineHeight: 0.8,
    color: T.accentSoft,
    display: "block",
    marginBottom: `-1rem`,
    userSelect: "none",
  };
  const quoteStyle: CSSProperties = {
    fontFamily: T.heads,
    fontWeight: 700,
    color: T.heading,
    fontSize: tx("3xl"),
    lineHeight: 1.15,
  };
  return (
    <div style={wrapStyle}>
      <FStack gap={3}>
        <div>
          <span aria-hidden="true" style={markStyle}>
            &ldquo;
          </span>
          <span style={quoteStyle}>{children}</span>
        </div>
        {cite != null ? <FLabel>— {cite}</FLabel> : null}
      </FStack>
    </div>
  );
}
