import { registerRoot } from "remotion";
// Load the fonts the demo themes reference, registered under their real family
// names so the theme tokens (--font-display-en etc.) resolve. A full impl would
// load the *active* theme's font list; here we load bold-signal + paper-press.
import { loadFont as fArchivo } from "@remotion/google-fonts/ArchivoBlack";
import { loadFont as fGrotesk } from "@remotion/google-fonts/SpaceGrotesk";
import { loadFont as fMono } from "@remotion/google-fonts/JetBrainsMono";
import { loadFont as fInstrument } from "@remotion/google-fonts/InstrumentSerif";
import { loadFont as fManrope } from "@remotion/google-fonts/Manrope";
import "./styles/base.css";
import "./styles/_active-theme.css"; // staged per-job from skill/themes/<id>/tokens.css
import { Root } from "./Root";

const o = { subsets: ["latin"], ignoreTooManyRequestsWarning: true } as const;
fArchivo("normal", { ...o, weights: ["400"] });
fGrotesk("normal", { ...o, weights: ["400", "700"] });
fMono("normal", { ...o, weights: ["400", "500"] });
fInstrument("normal", { ...o, weights: ["400"] });
fManrope("normal", { ...o, weights: ["400", "700", "800"] });

registerRoot(Root);
