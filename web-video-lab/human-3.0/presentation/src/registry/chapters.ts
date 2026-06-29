import type { ChapterDef } from "./types";
import HookChapter from "../chapters/01-hook/Hook";
import { narrations as hookNarrations } from "../chapters/01-hook/narrations";
import OneMapChapter from "../chapters/02-one-map/OneMap";
import { narrations as oneMapNarrations } from "../chapters/02-one-map/narrations";

/**
 * Order = order of presentation. Each chapter's `narrations.length` is its
 * step count (single source of truth; no separate totalSteps).
 */
export const CHAPTERS: ChapterDef[] = [
  {
    id: "hook",
    title: "Hook — I never wanted to be an NPC",
    narrations: hookNarrations,
    Component: HookChapter,
  },
  {
    id: "one-map",
    title: "One Map — knowledge is a web",
    narrations: oneMapNarrations,
    Component: OneMapChapter,
  },
];
