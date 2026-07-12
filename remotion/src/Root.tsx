/**
 * Composition registry. Duration/fps/size all derive from the manifest via
 * calculateMetadata — the renderer cannot disagree with the audio timeline.
 */

import React from 'react';
import {Composition} from 'remotion';
import {Master} from './Master';
import {TOKENS} from './tokens';
import type {Manifest, MasterProps} from './types';
import type {SfxIndex} from './Sfx';

/** Tiny built-in demo so `remotion studio` opens without props. */
const demoManifest: Manifest = {
  video_id: 'v_studio_demo',
  fps: 30,
  aspect: '9:16',
  audio: {path: 'runs/golden/audio/mastered.wav', duration_ms: 6000},
  beats: [
    {
      id: 'b01', start_ms: 0, end_ms: 3000,
      words: [
        {w: 'this', s: 200, e: 450}, {w: 'is', s: 450, e: 640},
        {w: 'the', s: 640, e: 800}, {w: 'VULCAN', s: 820, e: 1500},
        {w: 'render', s: 1550, e: 2000}, {w: 'stack', s: 2000, e: 2500},
      ],
      treatment: 'kinetic_type',
      text_overlay: {mode: 'karaoke', emphasis_words: ['VULCAN']},
      assets: [], sfx: [], camera: 'punch_in', transition_out: 'whip',
    },
    {
      id: 'b02', start_ms: 3000, end_ms: 6000,
      words: [
        {w: 'numbers', s: 3200, e: 3700}, {w: 'hit', s: 3750, e: 4000},
        {w: 'different', s: 4050, e: 4600},
      ],
      treatment: 'stat_slam',
      text_overlay: {mode: 'headline', headline_text: 'Numbers hit different'},
      assets: [], sfx: [], camera: 'static', transition_out: 'hard_cut',
      payload: {stat_text: '87%'},
    },
  ],
  assets: [],
};

type Props = MasterProps & {sfxIndex?: SfxIndex};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Master"
      component={Master as React.FC<Props>}
      width={TOKENS.canvas.width}
      height={TOKENS.canvas.height}
      fps={TOKENS.canvas.fps}
      durationInFrames={180}
      defaultProps={{manifest: demoManifest, style: {}, sfxIndex: {}}}
      calculateMetadata={({props}) => {
        const m = (props as Props).manifest;
        return {
          durationInFrames: Math.round((m.audio.duration_ms * TOKENS.canvas.fps) / 1000),
          fps: TOKENS.canvas.fps,
          width: TOKENS.canvas.width,
          height: TOKENS.canvas.height,
        };
      }}
    />
  );
};
