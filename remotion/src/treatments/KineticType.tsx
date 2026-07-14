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

  // never render a bare beat: no emphasis word → ghost the longest word
  // (a 92s video of caption-only beats reads as "black screen", post-mortem 2)
  const fallback = [...beat.words]
    .map((w) => w.w.replace(/[^\p{L}\p{N}'-]/gu, ''))
    .filter((w) => w.length >= 4)
    .sort((a, b) => b.length - a.length)[0];
  const ghost = (beat.text_overlay.emphasis_words ?? [])[0] ?? fallback;
  if (!ghost) return null;

  // ghost anticipates its word: enters at the word start OR 40% through the
  // beat, whichever comes first — beat-final emphasis words otherwise leave
  // the frame empty (Phase 4 eye check).
  const word = beat.words.find(
    (w) => w.w.toLowerCase().replace(/[^\p{L}\p{N}'-]/gu, '') === ghost.toLowerCase().replace(/[^\p{L}\p{N}'-]/gu, ''),
  );
  const beatLen = beat.end_ms - beat.start_ms;
  const enterMs = Math.min(word ? word.s - beat.start_ms : 0, beatLen * 0.4);
  const enterF = msToFrame(enterMs, fps);
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
