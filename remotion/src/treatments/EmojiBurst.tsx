/**
 * emoji_burst — oversized 3D emoji spring-slams in with rotation overshoot;
 * a ring of accent sparks bursts outward on impact. Pure joy, 1.5 seconds.
 */

import React from 'react';
import {AbsoluteFill, Img, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from '../tokens';
import type {Beat} from '../types';
import type {AssetMap} from './common';
import {Glow, seeded, src, useAssetWindow} from './common';

export const EmojiBurst: React.FC<{beat: Beat; assets: AssetMap; tokens: Tokens}> = ({
  beat, assets, tokens,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const heroRef = beat.assets.find((a) => a.role === 'hero') ?? beat.assets[0];
  if (!heroRef) return null;
  const {visible, enter, exit, enterF} = useAssetWindow(heroRef, tokens, 'slam');
  const asset = assets[heroRef.asset_id];
  if (!asset || !visible) return null;

  const y = tokens.emojiBurst.yCenter * 100;
  const rot = (1 - enter) * -24 + seeded(beat.id, 3) * 8 - 4;

  // burst particles fly out over 14 frames after entrance
  const burstT = interpolate(frame - enterF, [3, 17], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill>
      <Glow cx="50%" cy={`${y}%`} color={tokens.color.accent} opacity={0.16 * enter * exit} scale={1.2} />
      {Array.from({length: tokens.emojiBurst.burstCount}).map((_, i) => {
        const angle = (i / tokens.emojiBurst.burstCount) * Math.PI * 2 + seeded(beat.id, i) * 0.5;
        const dist = burstT * (240 + seeded(beat.id, i + 20) * 120);
        const size = 16 + seeded(beat.id, i + 40) * 18;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: `calc(50% + ${Math.cos(angle) * dist}px)`,
              top: `calc(${y}% + ${Math.sin(angle) * dist * 0.85}px)`,
              width: size,
              height: size,
              borderRadius: '50%',
              background: i % 3 === 0 ? tokens.color.text : tokens.color.accent,
              opacity: (1 - burstT) * 0.9 * exit,
              transform: `translate(-50%, -50%) scale(${1 - burstT * 0.5})`,
            }}
          />
        );
      })}
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: `${y}%`,
          transform: `translate(-50%, -50%) scale(${enter}) rotate(${rot}deg)`,
          opacity: exit,
          width: tokens.emojiBurst.heroSizePx,
          height: tokens.emojiBurst.heroSizePx,
          filter: 'drop-shadow(0 24px 48px rgba(0,0,0,0.5))',
        }}
      >
        <Img src={src(asset)} style={{width: '100%', height: '100%', objectFit: 'contain'}} />
      </div>
    </AbsoluteFill>
  );
};
