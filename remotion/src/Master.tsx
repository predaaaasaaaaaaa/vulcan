/**
 * <Master> — the one composition. Pure function of (manifest, assets on disk).
 * Background persists; each beat is an independent Sequence stacking
 * Camera(Treatment) + Captions inside its TransitionWrap; voice + SFX on top.
 */

import React, {useMemo} from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile} from 'remotion';
import {Background} from './Background';
import {Captions} from './Captions';
import {Camera} from './Camera';
import {ensureFont} from './fonts';
import {SfxLayer, SfxIndex} from './Sfx';
import {withAccent} from './tokens';
import {TransitionWrap} from './Transitions';
import {TREATMENTS} from './treatments';
import type {AssetMap} from './treatments/common';
import type {MasterProps} from './types';
import {msToFrame} from './types';

export const Master: React.FC<MasterProps & {sfxIndex?: SfxIndex}> = ({manifest, style, sfxIndex = {}}) => {
  ensureFont();
  const tokens = withAccent(style?.accent);

  const assetMap: AssetMap = useMemo(
    () => Object.fromEntries(manifest.assets.map((a) => [a.asset_id, a])),
    [manifest.assets],
  );

  return (
    <AbsoluteFill style={{backgroundColor: tokens.color.bg}}>
      <Background tokens={tokens} />
      {manifest.beats.map((beat, i) => {
        const from = msToFrame(beat.start_ms);
        const durationInFrames = Math.max(msToFrame(beat.end_ms) - from, 1);
        const TreatmentComp = TREATMENTS[beat.treatment];
        const isLast = i === manifest.beats.length - 1;
        return (
          <Sequence key={beat.id} from={from} durationInFrames={durationInFrames} name={`${beat.id} ${beat.treatment}`}>
            <TransitionWrap
              kind={beat.transition_out}
              durationInFrames={durationInFrames}
              tokens={tokens}
              isLastBeat={isLast}
            >
              <Camera move={beat.camera} durationInFrames={durationInFrames} tokens={tokens}>
                <TreatmentComp beat={beat} assets={assetMap} tokens={tokens} />
                <Captions beat={beat} tokens={tokens} />
              </Camera>
            </TransitionWrap>
          </Sequence>
        );
      })}
      <Audio src={staticFile(manifest.audio.path)} volume={1} />
      <SfxLayer beats={manifest.beats} sfxIndex={sfxIndex} />
    </AbsoluteFill>
  );
};
