/**
 * list_stack — enumerations. Each item springs in ON ITS WORD TIMESTAMP
 * (payload.items[].at_ms, Director-anchored to the spoken word), stacking down.
 */

import React from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from '../tokens';
import type {Beat} from '../types';
import {msToFrame} from '../types';

export const ListStack: React.FC<{beat: Beat; assets: unknown; tokens: Tokens}> = ({beat, tokens}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const items = beat.payload?.items ?? [];

  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: `${tokens.list.yTop * 100}%`,
          transform: 'translateX(-50%)',
          width: tokens.list.maxWidthPx,
          display: 'flex',
          flexDirection: 'column',
          gap: tokens.list.rowGap,
        }}
      >
        {items.map((item, i) => {
          const startF = msToFrame(item.at_ms, fps);
          if (frame < startF) return null;
          const s = spring({
            frame: frame - startF,
            fps,
            config: tokens.spring.pop,
            durationInFrames: 16,
          });
          return (
            <div
              key={i}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 28,
                transform: `translateY(${(1 - s) * 40}px) scale(${0.94 + s * 0.06})`,
                opacity: s,
              }}
            >
              <div
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: 18,
                  flexShrink: 0,
                  background: tokens.color.accent,
                  color: '#0A0A0C',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontFamily: tokens.font.family,
                  fontWeight: tokens.font.weightBlack,
                  fontSize: 36,
                  boxShadow: '0 8px 30px rgba(0,0,0,0.45)',
                }}
              >
                {i + 1}
              </div>
              <div
                style={{
                  fontFamily: tokens.font.family,
                  fontWeight: tokens.font.weightHeavy,
                  fontSize: tokens.list.fontSize,
                  lineHeight: 1.15,
                  color: tokens.color.text,
                  textShadow: tokens.caption.textShadow,
                }}
              >
                {item.text.toUpperCase()}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
