/**
 * network_grow — animated node network for scale/system/connect/growth beats.
 * Nodes spring in one by one, edges draw between them, the accent pulse
 * travels the graph. Pure SVG, deterministic from the beat id — the
 * Remotion-native "scale" moment Samy called out as the direction.
 */

import React, {useMemo} from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from '../tokens';
import type {Beat} from '../types';
import type {AssetMap} from './common';
import {Glow, seeded, useIdle} from './common';

const W = 860;
const H = 620;
const N = 12;

type Node = {x: number; y: number; r: number; order: number};

const buildGraph = (beatId: string) => {
  // deterministic scatter: golden-angle spiral + jitter → organic but stable
  const nodes: Node[] = [];
  for (let i = 0; i < N; i++) {
    const a = i * 2.39996 + seeded(beatId, i) * 0.6;
    const rad = 60 + (i / N) * 250 + seeded(beatId, i + 40) * 40;
    nodes.push({
      x: W / 2 + Math.cos(a) * rad * 1.15,
      y: H / 2 + Math.sin(a) * rad * 0.72,
      r: i === 0 ? 26 : 12 + seeded(beatId, i + 80) * 10,
      order: i,
    });
  }
  // edges: each node connects to its nearest earlier node (tree → clean look)
  const edges: [number, number][] = [];
  for (let i = 1; i < N; i++) {
    let best = 0, bd = Infinity;
    for (let j = 0; j < i; j++) {
      const d = Math.hypot(nodes[i].x - nodes[j].x, nodes[i].y - nodes[j].y);
      if (d < bd) { bd = d; best = j; }
    }
    edges.push([best, i]);
  }
  // a couple of cross-links for the "network" read
  edges.push([2, Math.min(7, N - 1)], [1, Math.min(9, N - 1)]);
  return {nodes, edges};
};

export const NetworkGrow: React.FC<{beat: Beat; assets: AssetMap; tokens: Tokens}> = ({
  beat, tokens,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const idle = useIdle(24, seeded(beat.id, 9), 7, 3.8);
  const {nodes, edges} = useMemo(() => buildGraph(beat.id), [beat.id]);
  const label = beat.payload?.network?.label ?? '';

  const nodeS = (i: number) =>
    spring({frame: Math.max(frame - 4 - i * 3, 0), fps, config: tokens.spring.pop, durationInFrames: 14});

  // accent pulse travels along the whole graph on a loop
  const pulseT = ((frame / fps) % 2.4) / 2.4;
  const pulseEdge = Math.floor(pulseT * edges.length);

  const enter = spring({frame, fps, config: tokens.spring.gentle, durationInFrames: 18});

  return (
    <AbsoluteFill>
      <Glow cx="50%" cy="30%" color={tokens.color.accent} opacity={0.13 * enter} scale={1.25} />
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: '30%',
          transform: `translate(-50%, -50%) translateY(${idle.y}px) rotate(${idle.rot * 0.35}deg) `
            + `scale(${0.92 + enter * 0.08})`,
          opacity: Math.min(enter * 1.3, 1),
          width: W,
        }}
      >
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
          {edges.map(([a, b], i) => {
            const sA = nodeS(a), sB = nodeS(b);
            const vis = Math.min(sA, sB);
            if (vis < 0.05) return null;
            const draw = interpolate(vis, [0.05, 1], [0, 1]);
            const na = nodes[a], nb = nodes[b];
            const len = Math.hypot(nb.x - na.x, nb.y - na.y);
            const hot = i === pulseEdge && frame > 40;
            return (
              <line
                key={i}
                x1={na.x} y1={na.y}
                x2={na.x + (nb.x - na.x) * draw}
                y2={na.y + (nb.y - na.y) * draw}
                stroke={hot ? tokens.color.accent : 'rgba(255,255,255,0.30)'}
                strokeWidth={hot ? 5 : 3}
                strokeDasharray={hot ? undefined : '1 0'}
                style={hot ? {filter: `drop-shadow(0 0 10px ${tokens.color.accent})`} : undefined}
              />
            );
          })}
          {nodes.map((n, i) => {
            const s = nodeS(i);
            if (s < 0.02) return null;
            const isHub = i === 0;
            const breathe = 1 + Math.sin(frame / fps * Math.PI * 2 / 2.2 + i) * 0.06;
            return (
              <g key={i} transform={`translate(${n.x} ${n.y}) scale(${s * breathe})`}>
                <circle r={n.r + 7} fill="none"
                        stroke={isHub ? tokens.color.accent : 'rgba(255,255,255,0.25)'}
                        strokeWidth={isHub ? 4 : 2} opacity={0.8} />
                <circle r={n.r} fill={isHub ? tokens.color.accent : '#FFFFFF'}
                        opacity={isHub ? 1 : 0.92}
                        style={isHub ? {filter: `drop-shadow(0 0 22px ${tokens.color.accent})`} : undefined} />
              </g>
            );
          })}
        </svg>
        {label ? (
          <div
            style={{
              marginTop: 2,
              textAlign: 'center',
              fontFamily: tokens.font.family,
              fontWeight: tokens.font.weightBlack,
              fontSize: 56,
              letterSpacing: '0.02em',
              textTransform: 'uppercase',
              color: tokens.color.text,
              textShadow: tokens.caption.textShadow,
            }}
          >
            {label}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
