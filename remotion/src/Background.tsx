/**
 * Global background: near-black, slow gradient drift, film grain.
 * Runs under every beat — never competes with foreground content.
 */

import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from './tokens';

const GRAIN_CELL = 3;

/** Cheap deterministic grain: SVG turbulence data URI, animated by frame offset. */
const grainUri = (() => {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>
    <filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/>
    <feColorMatrix type='saturate' values='0'/></filter>
    <rect width='240' height='240' filter='url(#n)'/></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
})();

export const Background: React.FC<{tokens: Tokens}> = ({tokens}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  // One slow full drift over the whole video: gradient hotspot wanders.
  const t = durationInFrames > 1 ? frame / durationInFrames : 0;
  const cx = 30 + 40 * Math.sin(t * Math.PI * 2);
  const cy = 20 + 25 * Math.cos(t * Math.PI * 1.5);

  // Grain jitters every 2 frames — reads as film, not static noise.
  const jitter = useMemo(() => {
    const step = Math.floor(frame / 2);
    return {
      x: ((step * 97) % 120) - 60,
      y: ((step * 131) % 120) - 60,
    };
  }, [frame]);

  return (
    <AbsoluteFill style={{backgroundColor: tokens.color.bg}}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(120% 90% at ${cx}% ${cy}%, ${tokens.color.bgGradientA} 0%, ${tokens.color.bgGradientB} 62%)`,
        }}
      />
      <AbsoluteFill
        style={{
          backgroundImage: `url("${grainUri}")`,
          backgroundRepeat: 'repeat',
          backgroundPosition: `${jitter.x}px ${jitter.y}px`,
          opacity: tokens.grain.opacity,
          mixBlendMode: 'overlay',
        }}
      />
      {/* subtle vignette keeps eyes center */}
      <AbsoluteFill
        style={{
          background: 'radial-gradient(90% 70% at 50% 52%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.42) 100%)',
        }}
      />
    </AbsoluteFill>
  );
};
