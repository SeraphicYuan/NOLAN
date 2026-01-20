import { registerRoot } from 'remotion';
import { LottieTest } from './LottieTest';
import { Composition } from 'remotion';

const Root: React.FC = () => {
  return (
    <Composition
      id="LottieTest"
      component={LottieTest}
      durationInFrames={90}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};

registerRoot(Root);
