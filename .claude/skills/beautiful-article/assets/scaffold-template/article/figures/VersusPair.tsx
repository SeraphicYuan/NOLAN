// figures/VersusPair.tsx — "A vs B" balanced contrast: two equal cards with a
// connector between them (e.g. ephemeral prompt vs persistent Skill).
//
// Theme-portable (only --ra-* tokens via primitives/helpers), SSR-safe (presentational),
// responsive (FRow flex 1 1 16rem → wraps/stacks on mobile).
import type { ReactNode } from "react";
import {
  FRow,
  FStack,
  Card,
  Sticker,
  Arrow,
  figureTokens as T,
  figureSpace as sp,
  figureRadius as rad,
  figureText as tx,
} from "./primitives";

export type VersusSide = { sticker?: ReactNode; title: ReactNode; body?: ReactNode; items?: ReactNode[] };

function Side({ side }: { side: VersusSide }): JSX.Element {
  return (
    <Card variant="surface" style={{ flex: "1 1 16rem", display: "flex", flexDirection: "column", gap: sp(3) }}>
      {side.sticker ? <Sticker>{side.sticker}</Sticker> : null}
      <span style={{ fontFamily: T.heads, fontSize: tx("lg"), fontWeight: 700, lineHeight: 1.2, color: T.heading }}>
        {side.title}
      </span>
      {side.body ? (
        <span style={{ fontSize: tx("sm"), lineHeight: 1.5, color: T.text }}>{side.body}</span>
      ) : null}
      {side.items && side.items.length > 0 ? (
        <FStack gap={2}>
          {side.items.map((item, i) => (
            <span key={i} style={{ display: "flex", alignItems: "baseline", gap: sp(2) }}>
              <span
                aria-hidden="true"
                style={{
                  flex: "0 0 auto",
                  width: "0.45rem",
                  height: "0.45rem",
                  borderRadius: rad("full"),
                  background: T.accent,
                  transform: "translateY(-0.08rem)",
                }}
              />
              <span style={{ fontSize: tx("sm"), lineHeight: 1.45, color: T.text }}>{item}</span>
            </span>
          ))}
        </FStack>
      ) : null}
    </Card>
  );
}

export function VersusPair(props: { left: VersusSide; right: VersusSide; connector?: ReactNode }): JSX.Element {
  const { left, right, connector } = props;
  return (
    <FRow gap={3} wrap align="stretch" justify="center">
      <Side side={left} />
      <div
        style={{
          flex: "0 0 auto",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          alignSelf: "center",
        }}
      >
        {connector ?? (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: sp(2),
              fontFamily: T.label,
              fontSize: tx("xs"),
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: T.faint,
            }}
          >
            vs
            <Arrow dir="right" />
          </span>
        )}
      </div>
      <Side side={right} />
    </FRow>
  );
}
