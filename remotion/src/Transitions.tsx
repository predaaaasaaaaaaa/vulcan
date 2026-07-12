/**
 * Beat exit transitions: hard_cut (nothing) | whip (blur slide-out) | flash.
 * Implemented entirely in the outgoing beat's final frames so every beat
 * remains an independent Sequence.
 */

import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import type {Tokens} from './tokens';
import type {TransitionOut} from './types';

export const TransitionWrap: React.FC<{
  kind: TransitionOut;
  durationInFrames: number;
  tokens: Tokens;
  isLastBeat: boolean;
  children: React.ReactNode;
}> = ({kind, durationInFrames, tokens, isLastBeat, children}) => {
  const frame = useCurrentFrame();

  if (isLastBeat || kind === 'hard_cut') {
    return <AbsoluteFill>{children}</AbsoluteFill>;
  }

  if (kind === 'whip') {
    const n = tokens.transition.whipFrames;
    const start = durationInFrames - n;
    const t = interpolate(frame, [start, durationInFrames - 1], [0, 1], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });
    const eased = t * t; // accelerate out
    return (
      <AbsoluteFill
        style={{
          transform: `translateX(${-eased * 1250}px)`,
          filter: t > 0 ? `blur(${eased * 26}px)` : 'none',
        }}
      >
        {children}
      </AbsoluteFill>
    );
  }

  // flash: white overlay ramps in over the last flashFrames
  const n = tokens.transition.flashFrames;
  const start = durationInFrames - n;
  const t = interpolate(frame, [start, durationInFrames - 1], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill>
      {children}
      {t > 0 ? (
        <AbsoluteFill style={{backgroundColor: '#FFFFFF', opacity: t * 0.9}} />
      ) : null}
    </AbsoluteFill>
  );
};
