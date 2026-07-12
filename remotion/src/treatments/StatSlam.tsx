/**
 * stat_slam — giant numeral count-up with punch-in settle.
 * Parses payload.stat_text ("87%", "$3M", "12x") → counts the numeric part up
 * over countUpMs, prefix/suffix render static. Accent number, white affixes.
 */

import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from '../tokens';
import type {Beat} from '../types';
import {Glow} from './common';

const parseStat = (text: string): {prefix: string; num: number; decimals: number; suffix: string} | null => {
  const m = text.match(/^([^0-9]*)([0-9]+(?:[.,][0-9]+)?)(.*)$/);
  if (!m) return null;
  const numStr = m[2].replace(',', '.');
  const decimals = numStr.includes('.') ? numStr.split('.')[1].length : 0;
  return {prefix: m[1], num: parseFloat(numStr), decimals, suffix: m[3]};
};

export const StatSlam: React.FC<{beat: Beat; assets: unknown; tokens: Tokens}> = ({beat, tokens}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const statText = beat.payload?.stat_text ?? '';
  const parsed = parseStat(statText);

  const countFrames = Math.round((tokens.stat.countUpMs / 1000) * fps);
  const enter = spring({frame, fps, config: tokens.spring.slam, durationInFrames: 14});
  const settle = spring({
    frame: Math.max(frame - countFrames, 0),
    fps,
    config: tokens.spring.slam,
    durationInFrames: 10,
  });

  const progress = interpolate(frame, [0, countFrames], [0, 1], {
    extrapolateRight: 'clamp',
  });
  // ease-out count: rushes early, lands exact
  const eased = 1 - Math.pow(1 - progress, 3);

  let display = statText;
  if (parsed) {
    const val = parsed.num * eased;
    display = `${parsed.prefix}${val.toFixed(parsed.decimals)}${parsed.suffix}`;
    if (progress >= 1) display = statText; // exact landing, no float dust
  }

  const scale = (0.86 + enter * 0.14) * (1 + settle * 0.06);

  return (
    <AbsoluteFill>
      <Glow cx="50%" cy={`${tokens.stat.yCenter * 100}%`} color={tokens.color.accent} opacity={0.18 * enter} scale={1.3} />
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: `${tokens.stat.yCenter * 100}%`,
          transform: `translate(-50%, -50%) scale(${scale})`,
          opacity: Math.min(enter * 1.5, 1),
          fontFamily: tokens.font.family,
          fontWeight: tokens.font.weightBlack,
          fontSize: tokens.stat.fontSize,
          letterSpacing: '-0.04em',
          color: tokens.color.accent,
          textShadow: '0 10px 60px rgba(0,0,0,0.6)',
          whiteSpace: 'nowrap',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {display}
      </div>
    </AbsoluteFill>
  );
};
