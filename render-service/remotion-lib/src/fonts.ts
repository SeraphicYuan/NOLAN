// Shared web font for all effects. @remotion/google-fonts handles the
// delayRender/continueRender so frames wait until the font is ready.
import {loadFont} from '@remotion/google-fonts/Inter';

export const {fontFamily: FONT} = loadFont('normal', {
  weights: ['400', '600', '800'],
  subsets: ['latin'],
});
