import { registerRoot } from "remotion";
import { loadFont as fArchivo } from "@remotion/google-fonts/ArchivoBlack";
import { loadFont as fGrotesk } from "@remotion/google-fonts/SpaceGrotesk";
import { loadFont as fMono } from "@remotion/google-fonts/JetBrainsMono";
import { loadFont as fInstrument } from "@remotion/google-fonts/InstrumentSerif";
import { loadFont as fManrope } from "@remotion/google-fonts/Manrope";
import { loadFont as fPlexMono } from "@remotion/google-fonts/IBMPlexMono";
import { loadFont as fPlexSans } from "@remotion/google-fonts/IBMPlexSans";
import "./styles/base.css";
import "./styles/_active-theme.css"; // staged per-job from skill/themes/<id>/tokens.css (Chapter only)
import { Root } from "./Root";

const o = { subsets: ["latin"], ignoreTooManyRequestsWarning: true } as const;
fArchivo("normal", { ...o, weights: ["400"] });
fGrotesk("normal", { ...o, weights: ["400", "700"] });
fMono("normal", { ...o, weights: ["400", "500"] });
fInstrument("normal", { ...o, weights: ["400"] });
fManrope("normal", { ...o, weights: ["400", "700", "800"] });
fPlexMono("normal", { ...o, weights: ["400", "500", "600"] });
fPlexSans("normal", { ...o, weights: ["400", "500", "600", "700"] });

registerRoot(Root);
