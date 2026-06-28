// figures/CompareCards.tsx — replaces a wide comparison TABLE that would clip at
// narrow reading width. One card per row so every field stays visible; theme-portable
// (only --ra-* tokens via primitives) and SSR-safe (presentational only).
import type { ReactNode } from "react";
import { Card, Chip, FStack, FRow, FLabel, Highlight, figureTokens as T, figureSpace as sp, figureText as tx } from "./primitives";

export type CompareField = { label: ReactNode; value: ReactNode };
export type CompareItem = { name: ReactNode; tag?: ReactNode; fields: CompareField[] };

export function CompareCards(props: { items: CompareItem[] }): JSX.Element {
  return (
    <FStack gap={3}>
      {props.items.map((item, i) => (
        <Card key={i}>
          <FRow gap={3} align="baseline">
            <span style={{ fontFamily: T.heads, fontSize: tx("lg"), fontWeight: 700, color: T.heading }}>
              <Highlight>{item.name}</Highlight>
            </span>
            {item.tag != null && (
              <Chip tone="default" mono style={{ marginLeft: "auto" }}>
                {item.tag}
              </Chip>
            )}
          </FRow>
          <FRow
            gap={4}
            style={{ borderTop: `1px solid ${T.border}`, paddingTop: sp(3), marginTop: sp(3) }}
          >
            {item.fields.map((field, j) => (
              <div key={j} style={{ flex: "1 1 12rem", display: "flex", flexDirection: "column", gap: sp(1) }}>
                <FLabel>{field.label}</FLabel>
                <span style={{ color: T.text, fontSize: tx("sm"), lineHeight: 1.45 }}>{field.value}</span>
              </div>
            ))}
          </FRow>
        </Card>
      ))}
    </FStack>
  );
}
