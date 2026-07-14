/**
 * Music bed — looped mood track under the voice, with DETERMINISTIC ducking
 * computed from the word timestamps: while words are being spoken the bed sits
 * at duck level; in real pauses it breathes back up. No live audio analysis —
 * the words ARE the sidechain.
 */

import React, {useMemo} from 'react';
import {Audio, staticFile, useVideoConfig} from 'remotion';
import type {Beat} from './types';

const BASE = 1.0;     // bed files are pre-normalized to sit ≈ −28 dBFS RMS
const DUCK = 0.45;    // while speech is active
const PAD_MS = 160;   // speech window padding
const RAMP_MS = 240;  // duck attack/release

export const MusicBed: React.FC<{
  beats: Beat[];
  file: string;
  durationMs: number;
}> = ({beats, file, durationMs}) => {
  const {fps, durationInFrames} = useVideoConfig();

  // merge padded word intervals into speech spans, once
  const spans = useMemo(() => {
    const words = beats.flatMap((b) => b.words);
    const raw = words
      .map((w) => [Math.max(w.s - PAD_MS, 0), w.e + PAD_MS] as [number, number])
      .sort((a, b) => a[0] - b[0]);
    const merged: [number, number][] = [];
    for (const [s, e] of raw) {
      const last = merged[merged.length - 1];
      if (last && s <= last[1]) last[1] = Math.max(last[1], e);
      else merged.push([s, e]);
    }
    return merged;
  }, [beats]);

  const volumeAt = (frame: number): number => {
    const ms = (frame / fps) * 1000;
    // distance to the nearest speech span (0 when inside one)
    let dist = Infinity;
    for (const [s, e] of spans) {
      if (ms >= s && ms <= e) {
        dist = 0;
        break;
      }
      dist = Math.min(dist, ms < s ? s - ms : ms - e);
    }
    const t = Math.min(dist / RAMP_MS, 1); // 0 = speaking, 1 = free air
    const v = DUCK + (BASE - DUCK) * t;
    // gentle fade in/out at the video edges
    const edgeIn = Math.min(frame / (fps * 0.8), 1);
    const edgeOut = Math.min((durationInFrames - frame) / (fps * 1.2), 1);
    return v * Math.max(Math.min(edgeIn, edgeOut), 0);
  };

  return <Audio loop src={staticFile(file)} volume={volumeAt} />;
};
