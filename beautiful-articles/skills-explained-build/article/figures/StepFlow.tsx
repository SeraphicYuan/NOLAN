// figures/StepFlow.tsx — sequential process diagram (steps → arrows → optional result).
//
// Theme-portable: composes only from primitives, styled via --ra-* tokens.
// SSR-safe: presentational, no state/effects. Responsive: flex + rem, wraps on mobile.
import type { CSSProperties, ReactNode } from "react";
import { Card, FRow, FStack, NumberBadge, Chip, Arrow, Highlight, figureTokens as T, figureText as tx } from "./primitives";

export type FlowStep = { badge?: ReactNode; title: ReactNode; body?: ReactNode; tag?: ReactNode };

const titleStyle: CSSProperties = { fontFamily: T.heads, fontWeight: 700, color: T.heading, fontSize: tx("md") };
const bodyStyle: CSSProperties = { color: T.muted, fontSize: tx("sm") };

/** Single step rendered as a card: header (badge + highlighted title + tag), then muted body. */
function StepCard({
  step,
  variant = "surface",
  cardStyle,
}: {
  step: FlowStep;
  variant?: "surface" | "accent";
  cardStyle?: CSSProperties;
}): JSX.Element {
  return (
    <Card variant={variant} style={cardStyle}>
      <FStack gap={2}>
        <FRow gap={2} wrap align="center">
          {step.badge !== undefined && <NumberBadge>{step.badge}</NumberBadge>}
          <Highlight style={titleStyle}>{step.title}</Highlight>
          {step.tag !== undefined && (
            <Chip tone="soft" mono style={{ marginLeft: "auto" }}>
              {step.tag}
            </Chip>
          )}
        </FRow>
        {step.body !== undefined && <div style={bodyStyle}>{step.body}</div>}
      </FStack>
    </Card>
  );
}

export function StepFlow(props: {
  steps: FlowStep[];
  direction?: "horizontal" | "vertical";
  terminal?: { title: ReactNode; body?: ReactNode };
}): JSX.Element {
  const { steps, direction = "horizontal", terminal } = props;
  const horizontal = direction === "horizontal";
  // Horizontal cards flex-grow & wrap; vertical cards fill width without stretching height.
  const cardStyle: CSSProperties = horizontal ? { flex: "1 1 14rem" } : { flex: "0 0 auto", width: "100%" };

  const terminalCard = terminal && (
    <Card variant="accent" style={cardStyle}>
      <FStack gap={2}>
        <FRow gap={2} wrap align="center">
          <NumberBadge>✓</NumberBadge>
          <Highlight style={titleStyle}>{terminal.title}</Highlight>
        </FRow>
        {terminal.body !== undefined && <div style={bodyStyle}>{terminal.body}</div>}
      </FStack>
    </Card>
  );

  if (horizontal) {
    const nodes: ReactNode[] = [];
    steps.forEach((step, i) => {
      nodes.push(<StepCard key={`step-${i}`} step={step} cardStyle={cardStyle} />);
      if (i < steps.length - 1) nodes.push(<Arrow key={`arrow-${i}`} dir="right" />);
    });
    if (terminalCard) {
      nodes.push(<Arrow key="arrow-terminal" dir="right" />);
      nodes.push(<span key="terminal" style={{ display: "contents" }}>{terminalCard}</span>);
    }
    return (
      <FRow gap={3} wrap align="stretch">
        {nodes}
      </FRow>
    );
  }

  // Vertical: full-width cards with a centered down-arrow between each.
  const nodes: ReactNode[] = [];
  steps.forEach((step, i) => {
    nodes.push(<StepCard key={`step-${i}`} step={step} cardStyle={cardStyle} />);
    if (i < steps.length - 1) {
      nodes.push(
        <FRow key={`arrow-${i}`} gap={0} justify="center">
          <Arrow dir="down" />
        </FRow>,
      );
    }
  });
  if (terminalCard) {
    nodes.push(
      <FRow key="arrow-terminal" gap={0} justify="center">
        <Arrow dir="down" />
      </FRow>,
    );
    nodes.push(<div key="terminal">{terminalCard}</div>);
  }
  return (
    <FStack gap={3} style={{ alignItems: "stretch" }}>
      {nodes}
    </FStack>
  );
}
