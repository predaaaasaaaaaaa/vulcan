/**
 * cutout_pop — stamped PNG cutout springs in above the captions.
 * Hero centered high with accent glow; secondaries tuck beside it smaller.
 */

import React from 'react';
import {AbsoluteFill, Img} from 'remotion';
import type {Tokens} from '../tokens';
import type {Beat} from '../types';
import type {AssetMap} from './common';
import {Glow, seeded, src, useAssetWindow, useIdle} from './common';

const HeroCutout: React.FC<{
  beat: Beat; assets: AssetMap; tokens: Tokens; refIndex: number;
}> = ({beat, assets, tokens, refIndex}) => {
  const ref = beat.assets[refIndex];
  const {visible, enter, exit, enterF} = useAssetWindow(ref, tokens, 'pop');
  const idle = useIdle(enterF + 14, seeded(beat.id, refIndex * 7 + 2));
  const asset = assets[ref.asset_id];
  if (!asset || !visible) return null;

  const isHero = ref.role === 'hero';
  const n = beat.assets.length;
  const tilt = (isHero ? tokens.cutout.rotateDeg : 6) + seeded(beat.id, refIndex * 13) * 4 - 2 + idle.rot;
  // hero center; secondaries offset to the sides
  const xPct = isHero ? 50 : refIndex % 2 === 1 ? 24 : 76;
  const yPct = tokens.cutout.yCenter * 100 + (isHero ? 0 : 7);
  const scale = (isHero ? 1 : 0.55) * (0.62 + enter * 0.38);

  return (
    <>
      {isHero ? (
        <Glow cx={`${xPct}%`} cy={`${yPct}%`} color={tokens.color.accent} opacity={0.13 * enter * exit} />
      ) : null}
      <div
        style={{
          position: 'absolute',
          left: `${xPct}%`,
          top: `${yPct}%`,
          transform: `translate(-50%, -50%) translateY(${idle.y}px) `
            + `rotate(${tilt * (0.5 + enter * 0.5)}deg) scale(${scale * idle.pulse})`,
          opacity: Math.min(enter * 1.4, 1) * exit,
          maxWidth: tokens.canvas.width * tokens.cutout.maxWidthFrac,
          maxHeight: tokens.canvas.height * tokens.cutout.maxHeightFrac,
          display: 'flex',
          justifyContent: 'center',
        }}
      >
        <Img
          src={src(asset)}
          style={{
            maxWidth: '100%',
            maxHeight: tokens.canvas.height * tokens.cutout.maxHeightFrac,
            objectFit: 'contain',
          }}
        />
      </div>
    </>
  );
};

export const CutoutPop: React.FC<{beat: Beat; assets: AssetMap; tokens: Tokens}> = ({
  beat, assets, tokens,
}) => (
  <AbsoluteFill>
    {beat.assets.map((_, i) => (
      <HeroCutout key={i} beat={beat} assets={assets} tokens={tokens} refIndex={i} />
    ))}
  </AbsoluteFill>
);
