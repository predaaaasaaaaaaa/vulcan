/**
 * kinetic_type v2 — true kinetic typography. The beat's POWER WORDS build a
 * big animated stack in the upper zone, each line slamming in AT THE MOMENT
 * its word is spoken (word timestamps drive everything). Lines float gently
 * after landing. The lower karaoke captions keep running — the stack is
 * amplification, not duplication (only 2–4 key words, not the sentence).
 *
 * v1 rendered a single faint ghost word: 19/29 beats read as "black void"
 * (Samy, 2026-07-14). The stack IS the motion graphic now.
 */

import React, {useMemo} from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from '../tokens';
import type {Beat, Word} from '../types';
import {msToFrame} from '../types';
import type {AssetMap} from './common';
import {seeded} from './common';

const norm = (w: string) => w.toLowerCase().replace(/[^\p{L}\p{N}-]/gu, '');
const display = (w: string) => w.replace(/[.,!?;:"“”]+$/g, '').toUpperCase();

type StackLine = {word: Word; isEmph: boolean};

/** Deterministic power-word pick: emphasis words first, then longest words,
 * capped at 4, ordered by spoken time. */
const pickStack = (beat: Beat): StackLine[] => {
  const emph = new Set((beat.text_overlay.emphasis_words ?? []).map(norm));
  const scored = beat.words
    .map((w) => ({w, n: norm(w.w)}))
    .filter(({n}) => n.length >= 3);
  const chosen: {word: Word; isEmph: boolean}[] = [];
  for (const {w, n} of scored) {
    if (emph.has(n) && !chosen.some((c) => norm(c.word.w) === n)) {
      chosen.push({word: w, isEmph: true});
    }
  }
  const rest = scored
    .filter(({n}) => !emph.has(n) && n.length >= 5 && !chosen.some((c) => norm(c.word.w) === n))
    .sort((a, b) => b.n.length - a.n.length);
  for (const {w} of rest) {
    if (chosen.length >= 4) break;
    if (!chosen.some((c) => c.word.s === w.s)) chosen.push({word: w, isEmph: false});
  }
  return chosen.sort((a, b) => a.word.s - b.word.s).slice(0, 4);
};

export const KineticType: React.FC<{beat: Beat; assets: AssetMap; tokens: Tokens}> = ({
  beat, tokens,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const stack = useMemo(() => pickStack(beat), [beat]);
  if (stack.length === 0) return null;

  const beatLen = beat.end_ms - beat.start_ms;
  const rows = stack.length;
  // vertical layout inside the upper zone (8%–56%), centered as a group
  const zoneTop = 10, zoneBottom = 54;
  const rowH = (zoneBottom - zoneTop) / Math.max(rows, 2);

  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      {stack.map((line, i) => {
        // anticipate late words the same way heroes do (≤55% of the beat)
        const relMs = Math.min(line.word.s - beat.start_ms, beatLen * 0.55);
        const enterF = msToFrame(Math.max(relMs, 0), fps);
        if (frame < enterF) return null;
        const s = spring({
          frame: frame - enterF, fps,
          config: tokens.spring.slam, durationInFrames: 16,
        });
        const seedA = seeded(beat.id, i * 17);
        const rot = (seedA - 0.5) * 7 + (i % 2 === 0 ? -1.6 : 1.6);
        const xOff = (seeded(beat.id, i * 29 + 5) - 0.5) * 90;
        // gentle idle float after landing — nothing on screen sits still
        const bob = Math.sin((frame - enterF) / fps / 2.6 * Math.PI * 2 + i * 1.7) * 6;
        const big = line.isEmph || i === 0;
        const active = frame - enterF < 14;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: '50%',
              top: `${zoneTop + rowH * (i + 0.5)}%`,
              transform: `translate(-50%, -50%) translate(${xOff}px, ${(1 - s) * 90 + bob}px) `
                + `rotate(${rot * (0.4 + s * 0.6)}deg) scale(${0.7 + s * 0.3})`,
              opacity: Math.min(s * 1.4, 1) * (active ? 1 : 0.92),
              fontFamily: tokens.font.family,
              fontWeight: tokens.font.weightBlack,
              fontSize: big ? 132 : 92,
              letterSpacing: '-0.02em',
              whiteSpace: 'nowrap',
              color: line.isEmph ? tokens.color.accent : tokens.color.text,
              textShadow: line.isEmph
                ? `0 10px 50px rgba(0,0,0,0.55), 0 0 90px ${tokens.color.accent}33`
                : '0 10px 50px rgba(0,0,0,0.55)',
            }}
          >
            {display(line.word.w)}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
