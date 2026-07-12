/**
 * Camera enum: static | punch_in | drift — applied to the whole beat content.
 * Slow, subtle, never fights the treatment's own springs.
 */

import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import type {Tokens} from './tokens';
import type {CameraMove} from './types';

export const Camera: React.FC<{
  move: CameraMove;
  durationInFrames: number;
  tokens: Tokens;
  children: React.ReactNode;
}> = ({move, durationInFrames, tokens, children}) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [0, Math.max(durationInFrames - 1, 1)], [0, 1], {
    extrapolateRight: 'clamp',
  });

  let transform = 'none';
  if (move === 'punch_in') {
    // ease-out: fast start, settles — feels like a beat hit
    const eased = 1 - Math.pow(1 - t, 2.2);
    transform = `scale(${1 + eased * (tokens.camera.punchInScale - 1)})`;
  } else if (move === 'drift') {
    const scale = 1.015 + t * (tokens.camera.driftScale - 1.015);
    const pan = (t - 0.5) * 2 * tokens.camera.driftPanPx;
    transform = `scale(${scale}) translateX(${pan}px)`;
  }

  return <AbsoluteFill style={{transform, transformOrigin: '50% 45%'}}>{children}</AbsoluteFill>;
};
