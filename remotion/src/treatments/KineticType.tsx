/**
 * kinetic_type — the default. Karaoke captions carry the beat; a giant ghost
 * echo of the first emphasis word fills the canvas behind them so the frame
 * never reads empty.
 */

import React from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from '../tokens';
import type {Beat} from '../types';
import {msToFrame} from '../types';
import type {AssetMap} from './common';
import {seeded} from './common';

export const KineticType: React.FC<{beat: Beat; assets: AssetMap; tokens: Tokens}> = ({
  beat, tokens,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const ghost = (beat.text_overlay.emphasis_words ?? [])[0];
  if (!ghost) return null;

  // ghost appears when its word is spoken
  const word = beat.words.find(
    (w) => w.w.toLowerCase().replace(/[^\p{L}\p{N}'-]/gu, '') === ghost.toLowerCase().replace(/[^\p{L}\p{N}'-]/gu, ''),
  );
  const enterF = word ? msToFrame(word.s - beat.start_ms, fps) : 0;
  const enter = spring({
    frame: Math.max(frame - enterF, 0),
    fps,
    config: tokens.spring.gentle,
    durationInFrames: 24,
  });
  if (frame < enterF) return null;

  const tilt = -8 + seeded(beat.id, 7) * 16;

  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: '34%',
          transform: `translate(-50%, -50%) rotate(${tilt}deg) scale(${0.92 + enter * 0.08})`,
          fontFamily: tokens.font.family,
          fontWeight: tokens.font.weightBlack,
          fontSize: 300,
          letterSpacing: '-0.03em',
          color: tokens.color.accent,
          opacity: enter * 0.07,
          whiteSpace: 'nowrap',
          textTransform: 'uppercase',
        }}
      >
        {ghost}
      </div>
    </AbsoluteFill>
  );
};
