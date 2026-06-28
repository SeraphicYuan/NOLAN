// figures/Stat.tsx — responsive row of big-number stat callouts composed from primitives.
import type { CSSProperties, ReactNode } from "react";
import { FGrid, FStack, Card, Chip, FLabel, figureTokens as T, figureText as tx } from "./primitives";

export type StatItem = {
  value: ReactNode;
  label: ReactNode;
  sub?: ReactNode;
  delta?: { dir: "up" | "down"; text: ReactNode };
};

/** Scannable grid of large-number callouts with optional up/down delta chips. */
export function Stat(props: { items: StatItem[] }): JSX.Element {
  const { items } = props;
  return (
    <FGrid min="10rem" gap={3}>
      {items.map((item, i) => {
        let delta: ReactNode = null;
        if (item.delta) {
          const up = item.delta.dir === "up";
          const color = up ? "var(--ra-color-success, #2f7d4f)" : "var(--ra-color-risk, #c63d1a)";
          const chipStyle: CSSProperties = { color, borderColor: color };
          delta = (
            <Chip tone="default" style={chipStyle}>
              <span aria-hidden="true">{up ? "↑" : "↓"}</span>
              {item.delta.text}
            </Chip>
          );
        }
        return (
          <Card key={i} variant="surface">
            <FStack gap={2}>
              <span
                style={{
                  fontFamily: T.heads,
                  fontWeight: 700,
                  color: T.heading,
                  fontSize: tx("4xl"),
                  lineHeight: 1.05,
                }}
              >
                {item.value}
              </span>
              <FLabel>{item.label}</FLabel>
              {item.sub != null ? (
                <span style={{ color: T.faint, fontSize: tx("xs") }}>{item.sub}</span>
              ) : null}
              {delta}
            </FStack>
          </Card>
        );
      })}
    </FGrid>
  );
}
