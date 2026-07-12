/**
 * Caption engine — always on, every beat.
 *
 * Karaoke mode: words grouped 3–4 (break on punctuation / ≥300ms gaps), the
 * group holds until the next group starts; the word being spoken RIGHT NOW
 * pops (scale + accent). Emphasis words are accent-colored permanently.
 * Text comes verbatim from beat.words — this component cannot paraphrase.
 *
 * Headline mode: static ≤6-word line (Director-authored), springs in once.
 */

import React, {useMemo} from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from './tokens';
import type {Beat, Word} from './types';

const PUNCT_BREAK = /[.!?,;:]$/;
const GAP_BREAK_MS = 300;

export type WordGroup = {words: Word[]; startMs: number; endMs: number};

export const groupWords = (words: Word[], maxWords: number): WordGroup[] => {
  const groups: WordGroup[] = [];
  let cur: Word[] = [];
  const flush = () => {
    if (cur.length) {
      groups.push({words: cur, startMs: cur[0].s, endMs: cur[cur.length - 1].e});
      cur = [];
    }
  };
  for (let i = 0; i < words.length; i++) {
    cur.push(words[i]);
    const w = words[i];
    const next = words[i + 1];
    const punct = PUNCT_BREAK.test(w.w);
    const gap = next ? next.s - w.e >= GAP_BREAK_MS : false;
    if (cur.length >= maxWords || punct || gap) flush();
  }
  flush();
  // merge a trailing 1-word orphan into the previous group for rhythm
  if (groups.length >= 2 && groups[groups.length - 1].words.length === 1) {
    const orphan = groups.pop()!;
    const prev = groups[groups.length - 1];
    if (prev.words.length < maxWords + 1) {
      prev.words.push(...orphan.words);
      prev.endMs = orphan.endMs;
    } else {
      groups.push(orphan);
    }
  }
  return groups;
};

const displayWord = (w: string): string =>
  w.replace(/[.,!?;:"“”]+$/g, '').replace(/^["“”]+/g, '').toUpperCase();

const normWord = (w: string): string =>
  w.toLowerCase().replace(/[^\p{L}\p{N}'-]/gu, '');

export const Captions: React.FC<{
  beat: Beat;
  tokens: Tokens;
}> = ({beat, tokens}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const nowMs = beat.start_ms + (frame / fps) * 1000;

  const overlay = beat.text_overlay;
  const emphasis = useMemo(
    () => new Set((overlay.emphasis_words ?? []).map(normWord)),
    [overlay.emphasis_words],
  );

  if (overlay.mode === 'headline') {
    return <Headline beat={beat} tokens={tokens} />;
  }

  const groups = useMemo(
    () => groupWords(beat.words, tokens.caption.maxGroupWords),
    [beat.words, tokens.caption.maxGroupWords],
  );
  if (groups.length === 0) return null;

  // active group: last group whose startMs <= now. Before the first word the
  // FIRST group is already displayed (dim) — captions are always on; a beat
  // that opens with silence must never show an empty frame (QC dead-frame
  // rule found this on the golden run).
  let gi = 0;
  for (let i = 0; i < groups.length; i++) {
    if (nowMs >= groups[i].startMs) gi = i;
  }
  const group = groups[gi];
  const preFirstGroup = nowMs < groups[0].startMs;

  // group entrance spring, restarted per group (beat start for the lead-in)
  const groupStartFrame = preFirstGroup
    ? 0
    : Math.round(((group.startMs - beat.start_ms) / 1000) * fps);
  const enter = spring({
    frame: frame - groupStartFrame,
    fps,
    config: tokens.spring.pop,
    durationInFrames: 14,
  });

  return (
    <div
      style={{
        position: 'absolute',
        left: '50%',
        top: `${tokens.caption.yCenter * 100}%`,
        transform: `translate(-50%, -50%) translateY(${(1 - enter) * 18}px)`,
        opacity: enter,
        width: tokens.caption.maxWidthPx,
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        alignItems: 'baseline',
        columnGap: tokens.caption.wordGap,
        rowGap: 6,
        textAlign: 'center',
      }}
    >
      {group.words.map((w, i) => {
        const active = nowMs >= w.s && nowMs < w.e + 60;
        const spoken = nowMs >= w.s;
        const isEmph = emphasis.has(normWord(w.w));
        const popFrame = frame - Math.round(((w.s - beat.start_ms) / 1000) * fps);
        const pop = active
          ? spring({frame: Math.max(popFrame, 0), fps, config: tokens.spring.pop, durationInFrames: 10})
          : 0;
        // one shared pop scale: long emphasized words at 1.13 overflowed the
        // word gap and visually fused with neighbours (Phase 6 eye check) —
        // emphasis is already carried by color + weight 900
        const scale = 1 + pop * (tokens.caption.emphasisScale - 1);
        return (
          <span
            key={`${gi}-${i}`}
            style={{
              fontFamily: tokens.font.family,
              fontWeight: isEmph ? tokens.font.weightBlack : tokens.font.weightHeavy,
              fontSize: tokens.caption.fontSize,
              lineHeight: tokens.caption.lineHeight,
              letterSpacing: tokens.caption.letterSpacing,
              color: isEmph || active ? tokens.color.accent : tokens.color.text,
              opacity: spoken || active ? 1 : tokens.caption.inactiveOpacity,
              textShadow: tokens.caption.textShadow,
              display: 'inline-block',
              transform: `scale(${scale})`,
              transformOrigin: 'center 70%',
            }}
          >
            {displayWord(w.w)}
          </span>
        );
      })}
    </div>
  );
};

const Headline: React.FC<{beat: Beat; tokens: Tokens}> = ({beat, tokens}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({frame, fps, config: tokens.spring.slam, durationInFrames: 16});
  const bar = spring({frame: Math.max(frame - 5, 0), fps, config: tokens.spring.pop, durationInFrames: 14});
  const text = (beat.text_overlay.headline_text ?? '').toUpperCase();
  return (
    <div
      style={{
        position: 'absolute',
        left: '50%',
        top: `${tokens.caption.yCenter * 100}%`,
        transform: `translate(-50%, -50%) scale(${0.88 + enter * 0.12})`,
        opacity: enter,
        width: tokens.caption.maxWidthPx,
        textAlign: 'center',
        fontFamily: tokens.font.family,
        fontWeight: tokens.font.weightBlack,
        fontSize: tokens.headline.fontSize,
        lineHeight: tokens.headline.lineHeight,
        letterSpacing: '0.01em',
        color: tokens.color.text,
        textShadow: tokens.caption.textShadow,
      }}
    >
      {text}
      <div
        style={{
          margin: '18px auto 0',
          width: tokens.headline.underlineWidth * bar,
          height: tokens.headline.underlineHeight,
          borderRadius: tokens.headline.underlineHeight / 2,
          background: tokens.color.accent,
        }}
      />
    </div>
  );
};
