// Chapter-hostable motion compositions (render story v2).
//
// These are the motion registry's standalone comps re-exported under their
// registry TARGET ids so the Chapter driver can host them as steps — the
// same components, same props, same theme tokens; only the frame they live
// in changes (a beat-anchored Series step instead of a standalone render).
// They all read duration via useVideoConfig(), which a Series.Sequence
// scopes to the step, so word-anchored timing keeps working.
//
// Deliberately absent: StillMotion (its parallax/rack-focus treatments need
// rembg pre-processing — ArtworkStage covers in-chapter camera moves) and
// ClipMontage (it authors its own internal timeline; a chapter step's
// duration is narration-owned).
import { KineticText } from "./KineticText";
import { BarCompare } from "./BarCompare";
import { KShape } from "./KShape";
import { AnnotateStat } from "./AnnotateStat";
import { AnnotateOverVideo } from "./AnnotateOverVideo";
import { RouteMap } from "./RouteMap";
import { PremiumCard } from "./PremiumCard";
import { SplitScreen } from "./SplitScreen";
import { StatOver } from "./StatOver";
import { PhotoMontage } from "./PhotoMontage";
import { PhotoGrid } from "./PhotoGrid";
import { Timeline } from "./Timeline";
import { ScreenFrame } from "./ScreenFrame";
import { CameraShake } from "./CameraShake";
import { BarRace } from "./BarRace";
import { Typewriter } from "./Typewriter";
import { BeforeAfter } from "./BeforeAfter";
import { WhipTransition } from "./WhipTransition";
import { PictureInPicture } from "./PictureInPicture";
import { CutoutCollage } from "./CutoutCollage";

export const COMPS: Record<string, React.FC<any>> = {
  Kinetic: KineticText,
  BarCompare,
  KShape,
  AnnotateStat,
  AnnotateOverVideo,
  RouteMap,
  PremiumCard,
  SplitScreen,
  StatOver,
  // the blocks library has its OWN PhotoMontage/PhotoGrid rebuilds (different
  // props) — the motion-comp variants get distinct keys so neither shadows
  // the other; nolan.motion.executor maps the registry targets to these.
  PhotoMontagePro: PhotoMontage,
  PhotoGridPro: PhotoGrid,
  // the blocks library also has its own single-purpose Timeline (the
  // "gap is the argument" layout) — same distinct-key rule
  TimelinePro: Timeline,
  // gap effects (2026-07)
  ScreenFrame,
  CameraShake,
  BarRace,
  Typewriter,
  BeforeAfter,
  WhipTransition,
  PictureInPicture,
  CutoutCollage,
};
