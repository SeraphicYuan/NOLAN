// figures/CardGrid.tsx — replaces "grid of annotated cards" visuals (subagent
// delegation cards with tool-permission chips, getting-started track cards with
// checklists). Theme-portable (only --ra-* tokens via primitives), SSR-safe, and
// responsive (FGrid collapses to one column on mobile).
import type { ReactNode } from "react";
import { Card, Chip, Sticker, NumberBadge, FStack, FRow, FGrid, FLabel, figureTokens as T, figureSpace as sp, figureText as tx } from "./primitives";

export type GridChip = { label: ReactNode; on?: boolean };
export type GridCard = {
  sticker?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  items?: ReactNode[];
  chips?: GridChip[];
  footnote?: ReactNode;
};

export function CardGrid(props: { cards: GridCard[]; min?: string; lead?: ReactNode }): JSX.Element {
  return (
    <FStack gap={4}>
      {props.lead != null && <div style={{ textAlign: "center", color: T.muted, fontSize: tx("sm") }}>{props.lead}</div>}
      <FGrid min={props.min ?? "15rem"} gap={3}>
        {props.cards.map((card, i) => (
          <Card key={i}>
            <FStack gap={3}>
              {card.sticker != null && <Sticker>{card.sticker}</Sticker>}
              <div style={{ display: "flex", flexDirection: "column", gap: sp(1) }}>
                <span style={{ fontFamily: T.heads, fontSize: tx("lg"), fontWeight: 700, color: T.heading }}>{card.title}</span>
                {card.subtitle != null && <span style={{ color: T.muted, fontSize: tx("sm") }}>{card.subtitle}</span>}
              </div>

              {card.items != null && card.items.length > 0 && (
                <FStack gap={2}>
                  {card.items.map((item, j) => (
                    <FRow key={j} gap={2} wrap={false} align="flex-start">
                      <NumberBadge size={1.2}>✓</NumberBadge>
                      <span style={{ color: T.text, fontSize: tx("sm"), lineHeight: 1.45 }}>{item}</span>
                    </FRow>
                  ))}
                </FStack>
              )}

              {card.chips != null && card.chips.length > 0 && (
                <FRow gap={2} style={{ borderTop: `1px solid ${T.border}`, paddingTop: sp(3) }}>
                  {card.chips.map((chip, j) => (
                    <Chip key={j} tone={chip.on === false ? "struck" : "default"} mono>
                      {chip.label}
                    </Chip>
                  ))}
                </FRow>
              )}

              {card.footnote != null && <FLabel>{card.footnote}</FLabel>}
            </FStack>
          </Card>
        ))}
      </FGrid>
    </FStack>
  );
}
