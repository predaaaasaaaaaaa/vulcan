/** Shared treatment helpers — asset windows, springs, glows. */

import React from 'react';
import {spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from '../tokens';
import type {Beat, BeatAssetRef, ManifestAsset} from '../types';
import {msToFrame} from '../types';

export type AssetMap = Record<string, ManifestAsset>;

export const useLocalFrame = () => useCurrentFrame();

/** Visibility + entrance spring for one asset ref window (beat-relative). */
export const useAssetWindow = (ref: BeatAssetRef, tokens: Tokens, springKind: keyof Tokens['spring'] = 'pop') => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enterF = msToFrame(ref.enter_ms, fps);
  const exitF = msToFrame(ref.exit_ms, fps);
  const visible = frame >= enterF && frame < exitF;
  const enter = spring({
    frame: Math.max(frame - enterF, 0),
    fps,
    config: tokens.spring[springKind],
    durationInFrames: 18,
  });
  // quick 4-frame exit fade so cuts never pop mid-air
  const remaining = exitF - frame;
  const exit = remaining <= 4 ? Math.max(remaining / 4, 0) : 1;
  return {visible, enter, exit, enterF, exitF};
};

export const src = (asset: ManifestAsset): string => staticFile(asset.path ?? '');

/** Soft radial glow that lifts cutouts off the near-black bg. */
export const Glow: React.FC<{cx: string; cy: string; scale?: number; color: string; opacity?: number}> = ({
  cx, cy, scale = 1, color, opacity = 0.16,
}) => (
  <div
    style={{
      position: 'absolute',
      left: cx,
      top: cy,
      width: 900 * scale,
      height: 900 * scale,
      transform: 'translate(-50%, -50%)',
      background: `radial-gradient(circle, ${color} 0%, transparent 62%)`,
      opacity,
      pointerEvents: 'none',
    }}
  />
);

/** Deterministic pseudo-random from beat id — stable across renders. */
export const seeded = (beatId: string, salt: number): number => {
  let h = salt;
  for (let i = 0; i < beatId.length; i++) h = (h * 31 + beatId.charCodeAt(i)) % 997;
  return (h % 200) / 200; // 0..1
};

/** Idle life for landed elements: gentle bob + sway. Nothing sits still —
 * static heroes read as screenshots, not motion graphics. */
export const useIdle = (sinceFrame: number, seed: number, ampPx = 9, periodS = 2.9) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = Math.max(frame - sinceFrame, 0) / fps;
  const phase = seed * Math.PI * 2;
  return {
    y: Math.sin((t / periodS) * Math.PI * 2 + phase) * ampPx,
    rot: Math.sin((t / (periodS * 1.7)) * Math.PI * 2 + phase) * 1.3,
    pulse: 1 + Math.sin((t / (periodS * 1.3)) * Math.PI * 2 + phase) * 0.012,
  };
};
