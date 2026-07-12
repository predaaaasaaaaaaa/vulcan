/**
 * logo_versus — two assets slam in from opposite sides, VS badge punches
 * center, 3-frame shake on impact.
 */

import React from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from '../tokens';
import type {Beat} from '../types';
import {msToFrame} from '../types';
import type {AssetMap} from './common';
import {Glow, src} from './common';
import {Img} from 'remotion';

export const LogoVersus: React.FC<{beat: Beat; assets: AssetMap; tokens: Tokens}> = ({
  beat, assets, tokens,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const left = beat.assets.find((a) => a.role === 'left');
  const right = beat.assets.find((a) => a.role === 'right');
  if (!left || !right) return null;

  const leftF = msToFrame(left.enter_ms, fps);
  const rightF = msToFrame(right.enter_ms, fps);
  const impactF = Math.max(leftF, rightF) + 6;

  const sL = spring({frame: Math.max(frame - leftF, 0), fps, config: tokens.spring.slam, durationInFrames: 14});
  const sR = spring({frame: Math.max(frame - rightF, 0), fps, config: tokens.spring.slam, durationInFrames: 14});
  const sVS = spring({frame: Math.max(frame - impactF, 0), fps, config: tokens.spring.slam, durationInFrames: 12});

  // impact shake: 3 frames of decaying jitter after VS lands
  const sinceImpact = frame - impactF;
  const shake = sinceImpact >= 0 && sinceImpact < 4
    ? Math.sin(sinceImpact * 9.4) * (4 - sinceImpact) * 3.2
    : 0;

  const y = 36; // % vertical center of the duel row

  const logoStyle = (s: number, fromLeft: boolean): React.CSSProperties => ({
    position: 'absolute',
    top: `${y}%`,
    left: fromLeft ? '24%' : '76%',
    transform: `translate(-50%, -50%) translateX(${(1 - s) * (fromLeft ? -600 : 600)}px) rotate(${fromLeft ? -4 : 4}deg)`,
    opacity: Math.min(s * 1.5, 1),
    width: 300,
    height: 300,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  });

  return (
    <AbsoluteFill style={{transform: `translate(${shake}px, ${-shake / 2}px)`}}>
      <Glow cx="50%" cy={`${y}%`} color={tokens.color.accent} opacity={0.12 * sVS} scale={1.4} />
      <div style={logoStyle(sL, true)}>
        {assets[left.asset_id] ? (
          <Img src={src(assets[left.asset_id])} style={{maxWidth: '100%', maxHeight: '100%', objectFit: 'contain'}} />
        ) : null}
      </div>
      <div style={logoStyle(sR, false)}>
        {assets[right.asset_id] ? (
          <Img src={src(assets[right.asset_id])} style={{maxWidth: '100%', maxHeight: '100%', objectFit: 'contain'}} />
        ) : null}
      </div>
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: `${y}%`,
          transform: `translate(-50%, -50%) scale(${sVS}) rotate(${(1 - sVS) * 20 - 6}deg)`,
          fontFamily: tokens.font.family,
          fontWeight: tokens.font.weightBlack,
          fontSize: 130,
          color: '#0A0A0C',
          background: tokens.color.accent,
          padding: '6px 34px',
          borderRadius: 22,
          boxShadow: '0 18px 60px rgba(0,0,0,0.55)',
        }}
      >
        VS
      </div>
    </AbsoluteFill>
  );
};
