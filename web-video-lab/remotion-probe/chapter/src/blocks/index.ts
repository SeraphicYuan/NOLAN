import { ListReveal } from "./ListReveal";
import { HeroStatement } from "./HeroStatement";
import { WebVsBoxes } from "./WebVsBoxes";
import { ArchetypeCards } from "./ArchetypeCards";
import { Timeline } from "./Timeline";

// The chapter block library — name → component. A chapter step picks a block by
// name; the driver passes its props + revealFrames + durationInFrames.
export const BLOCKS = { ListReveal, HeroStatement, WebVsBoxes, ArchetypeCards, Timeline };
