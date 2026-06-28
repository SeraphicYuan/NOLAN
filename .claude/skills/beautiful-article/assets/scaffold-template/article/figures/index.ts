// figures/ — reusable, theme-portable article figures (compose from primitives,
// style only via --ra-* tokens, SSR-safe, responsive). Prefer a figure over
// hand-writing Raw; compose primitives for semi-novel visuals; Raw is the last resort.
export * from "./primitives";
export { StepFlow, type FlowStep } from "./StepFlow";
export { HubSpoke, type SpokeNode } from "./HubSpoke";
export { CompareCards, type CompareItem, type CompareField } from "./CompareCards";
export { VersusPair, type VersusSide } from "./VersusPair";
export { CardGrid, type GridCard, type GridChip } from "./CardGrid";
export { ProportionBar, type BarSegment } from "./ProportionBar";
export { Timeline, type TimelineEvent } from "./Timeline";
export { Stat, type StatItem } from "./Stat";
export { PullQuote } from "./PullQuote";
export { Term, Footnote } from "./Inline";
