/**
 * Global background v2 — never a dead frame: near-black base, slow gradient
 * drift, a parallax dot grid, two orbiting accent blobs, film grain, vignette.
 * Everything moves slowly; nothing competes with the foreground.
 */

import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from './tokens';

/** Cheap deterministic grain: SVG turbulence data URI, animated by frame offset. */
const grainUri = (() => {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>
    <filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/>
    <feColorMatrix type='saturate' values='0'/></filter>
    <rect width='240' height='240' filter='url(#n)'/></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
})();

const dotGridUri = (() => {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='72' height='72'>
    <circle cx='4' cy='4' r='1.6' fill='white'/></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
})();

export const Background: React.FC<{tokens: Tokens}> = ({tokens}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  const t = durationInFrames > 1 ? frame / durationInFrames : 0;
  const sec = frame / fps;
  const cx = 30 + 40 * Math.sin(t * Math.PI * 2);
  const cy = 20 + 25 * Math.cos(t * Math.PI * 1.5);

  // two accent blobs on slow independent orbits — depth without noise
  const blobA = {
    x: 50 + 34 * Math.sin(sec * 0.11),
    y: 26 + 16 * Math.cos(sec * 0.07),
  };
  const blobB = {
    x: 50 + 38 * Math.cos(sec * 0.05 + 2),
    y: 74 + 14 * Math.sin(sec * 0.09 + 1),
  };

  const jitter = useMemo(() => {
    const step = Math.floor(frame / 2);
    return {x: ((step * 97) % 120) - 60, y: ((step * 131) % 120) - 60};
  }, [frame]);

  return (
    <AbsoluteFill style={{backgroundColor: tokens.color.bg}}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(120% 90% at ${cx}% ${cy}%, ${tokens.color.bgGradientA} 0%, ${tokens.color.bgGradientB} 62%)`,
        }}
      />
      {/* accent blobs — 5% opacity, huge blur, slow orbit */}
      {[{p: blobA, s: 900}, {p: blobB, s: 760}].map(({p, s}, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: s,
            height: s,
            transform: 'translate(-50%, -50%)',
            background: `radial-gradient(circle, ${tokens.color.accent} 0%, transparent 62%)`,
            opacity: 0.05,
          }}
        />
      ))}
      {/* parallax dot grid — slow diagonal drift */}
      <AbsoluteFill
        style={{
          backgroundImage: `url("${dotGridUri}")`,
          backgroundRepeat: 'repeat',
          backgroundPosition: `${(sec * 4) % 72}px ${(sec * 2.5) % 72}px`,
          opacity: 0.05,
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
      <AbsoluteFill
        style={{
          background: 'radial-gradient(90% 70% at 50% 52%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.42) 100%)',
        }}
      />
    </AbsoluteFill>
  );
};
