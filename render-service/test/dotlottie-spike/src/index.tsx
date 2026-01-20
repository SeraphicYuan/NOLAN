import { registerRoot } from 'remotion';
import { LottieTest } from './LottieTest';
import { Composition } from 'remotion';

const Root: React.FC = () => {
  return (
    <Composition
      id="LottieTest"
      component={LottieTest}
      durationInFrames={152}   // 76 Lottie frames * 2 for full loop
      fps={60}                 // Match Lottie's 60fps
      width={1920}
      height={1080}
    />
  );
};

registerRoot(Root);
