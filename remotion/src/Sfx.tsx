/**
 * SFX layer — one <Audio> per manifest cue, placed at beat.start+at_ms.
 * Files are pre-normalized to the SFX bus level (config audio.sfx_lufs), so
 * volume stays 1 here; the mix is decided offline, deterministically.
 */

import React from 'react';
import {Audio, Sequence, staticFile, useVideoConfig} from 'remotion';
import type {Beat} from './types';
import {msToFrame} from './types';

export type SfxIndex = Record<string, {file: string}>;

export const SfxLayer: React.FC<{beats: Beat[]; sfxIndex: SfxIndex}> = ({beats, sfxIndex}) => {
  const {fps} = useVideoConfig();
  return (
    <>
      {beats.flatMap((beat) =>
        beat.sfx.map((s, i) => {
          const meta = sfxIndex[s.cue];
          if (!meta) return null; // validator guarantees this never happens
          const from = msToFrame(beat.start_ms + s.at_ms, fps);
          return (
            <Sequence key={`${beat.id}-sfx-${i}`} from={from} durationInFrames={Math.round(fps * 2.5)}>
              <Audio src={staticFile(`sfx/${meta.file}`)} volume={1} />
            </Sequence>
          );
        }),
      )}
    </>
  );
};
