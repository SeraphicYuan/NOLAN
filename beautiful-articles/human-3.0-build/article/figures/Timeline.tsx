// figures/Timeline.tsx — vertical timeline composed from shared primitives.
import type { CSSProperties, ReactNode } from "react";
import { FStack, FRow, NumberBadge, FLabel, figureTokens as T, figureSpace as sp, figureText as tx } from "./primitives";

export type TimelineEvent = { date?: ReactNode; title: ReactNode; body?: ReactNode; badge?: ReactNode };

/** Vertical timeline: a bordered left rail with a dot/badge per event, content to the right. */
export function Timeline(props: { events: TimelineEvent[] }): JSX.Element {
  const { events } = props;
  return (
    <FStack gap={0}>
      {events.map((event, i) => {
        const isLast = i === events.length - 1;
        const dot: ReactNode = event.badge != null ? (
          <NumberBadge size={1.6}>{event.badge}</NumberBadge>
        ) : (
          <span
            aria-hidden="true"
            style={{
              width: "0.7rem",
              height: "0.7rem",
              borderRadius: "999px",
              background: T.accent,
            }}
          />
        );
        // Rail column: holds the dot, plus a connector line filling the rest down to the next event.
        const railStyle: CSSProperties = {
          flex: "0 0 auto",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          alignSelf: "stretch",
          width: "1.8rem",
        };
        const lineStyle: CSSProperties = {
          flex: "1 1 auto",
          width: "1px",
          minHeight: sp(4),
          background: isLast ? "transparent" : T.border,
        };
        const contentStyle: CSSProperties = {
          flex: "1 1 0%",
          minWidth: 0,
          paddingBottom: isLast ? 0 : sp(5),
        };
        return (
          <FRow key={i} gap={3} wrap={false} align="stretch">
            <div style={railStyle}>
              <div style={{ paddingTop: "0.15rem", flex: "0 0 auto" }}>{dot}</div>
              <div style={lineStyle} />
            </div>
            <div style={contentStyle}>
              <FStack gap={1}>
                {event.date != null ? <FLabel>{event.date}</FLabel> : null}
                <span style={{ fontFamily: T.heads, fontWeight: 700, color: T.heading, fontSize: tx("lg") }}>
                  {event.title}
                </span>
                {event.body != null ? (
                  <span style={{ color: T.text, fontSize: tx("sm") }}>{event.body}</span>
                ) : null}
              </FStack>
            </div>
          </FRow>
        );
      })}
    </FStack>
  );
}
