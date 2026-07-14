/**
 * chart_pop — synthetic animated chart for trend/cost/scale claims.
 * No data needed: the Director gives a direction + label
 * (payload.chart {kind: bar_up|bar_down|line_up|line_down, label}).
 * Bars grow in staggered springs; lines draw left→right with a glow head.
 * Crisp, native, deterministic — the "charts" Samy asked for.
 */

import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from '../tokens';
import type {Beat} from '../types';
import type {AssetMap} from './common';
import {Glow, seeded, useIdle} from './common';

const W = 720;
const H = 460;

const heights = (up: boolean, seedBase: number, n = 5): number[] => {
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const base = up ? 0.22 + (i / (n - 1)) * 0.72 : 0.94 - (i / (n - 1)) * 0.72;
    out.push(Math.min(Math.max(base + (seedBase - 0.5) * 0.08 * ((i % 3) - 1), 0.1), 1));
  }
  return out;
};

export const ChartPop: React.FC<{beat: Beat; assets: AssetMap; tokens: Tokens}> = ({
  beat, tokens,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const idle = useIdle(20, seeded(beat.id, 3), 6, 3.6);
  const chart = beat.payload?.chart;
  if (!chart) return null;

  const up = chart.kind.endsWith('_up');
  const isLine = chart.kind.startsWith('line');
  const enter = spring({frame, fps, config: tokens.spring.pop, durationInFrames: 16});
  const hs = heights(up, seeded(beat.id, 7));
  const good = up; // rising = accent; falling = red-ish danger

  const barColor = good ? tokens.color.accent : tokens.color.danger;
  const drawT = interpolate(frame, [6, 34], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  // line path through the bar tops
  const pts = hs.map((h, i) => ({
    x: 40 + (i * (W - 80)) / (hs.length - 1),
    y: H - 60 - h * (H - 120),
  }));
  const pathLen = pts.slice(1).reduce((acc, p, i) => acc + Math.hypot(p.x - pts[i].x, p.y - pts[i].y), 0);
  const path = `M ${pts.map((p) => `${p.x} ${p.y}`).join(' L ')}`;
  const headIdx = Math.min(Math.floor(drawT * (pts.length - 1) + 0.999), pts.length - 1);
  const head = pts[headIdx];

  return (
    <AbsoluteFill>
      <Glow cx="50%" cy="32%" color={barColor} opacity={0.12 * enter} scale={1.2} />
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: '31%',
          transform: `translate(-50%, -50%) translateY(${(1 - enter) * 70 + idle.y}px) `
            + `rotate(${idle.rot * 0.4}deg) scale(${0.9 + enter * 0.1})`,
          opacity: Math.min(enter * 1.3, 1),
          width: W,
        }}
      >
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
          {/* faint grid */}
          {[0.25, 0.5, 0.75].map((g) => (
            <line key={g} x1={30} x2={W - 30} y1={H - 60 - g * (H - 120)} y2={H - 60 - g * (H - 120)}
                  stroke="rgba(255,255,255,0.09)" strokeWidth={2} strokeDasharray="4 10" />
          ))}
          <line x1={30} x2={W - 30} y1={H - 58} y2={H - 58} stroke="rgba(255,255,255,0.25)" strokeWidth={3} />
          {isLine ? (
            <>
              <path d={path} fill="none" stroke={barColor} strokeWidth={12} strokeLinecap="round"
                    strokeLinejoin="round" strokeDasharray={pathLen} strokeDashoffset={pathLen * (1 - drawT)} />
              {drawT > 0.02 ? (
                <circle cx={head.x} cy={head.y} r={16} fill={barColor}
                        style={{filter: `drop-shadow(0 0 18px ${barColor})`}} />
              ) : null}
            </>
          ) : (
            hs.map((h, i) => {
              const bs = spring({frame: Math.max(frame - 4 - i * 3, 0), fps,
                                 config: tokens.spring.slam, durationInFrames: 14});
              const bw = (W - 100) / hs.length - 18;
              const bh = h * (H - 120) * bs;
              const x = 50 + i * ((W - 100) / hs.length);
              return (
                <g key={i}>
                  <rect x={x} y={H - 60 - bh} width={bw} height={bh} rx={10}
                        fill={i === hs.length - 1 ? barColor : 'rgba(255,255,255,0.82)'} />
                  {i === hs.length - 1 && bs > 0.9 ? (
                    <text x={x + bw / 2} y={H - 72 - bh} textAnchor="middle"
                          fontFamily={tokens.font.family} fontWeight={900} fontSize={40} fill={barColor}>
                      {up ? '▲' : '▼'}
                    </text>
                  ) : null}
                </g>
              );
            })
          )}
        </svg>
        <div
          style={{
            marginTop: 6,
            textAlign: 'center',
            fontFamily: tokens.font.family,
            fontWeight: tokens.font.weightBlack,
            fontSize: 58,
            letterSpacing: '0.01em',
            color: tokens.color.text,
            textShadow: tokens.caption.textShadow,
            textTransform: 'uppercase',
          }}
        >
          {chart.label} <span style={{color: barColor}}>{up ? '▲' : '▼'}</span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
