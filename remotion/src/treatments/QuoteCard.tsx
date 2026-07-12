/**
 * quote_card — serif pull-quote on the house card. Giant accent quotation
 * mark, Georgia italic (system serif, offline), attribution in Outfit.
 */

import React from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from '../tokens';
import type {Beat} from '../types';
import type {AssetMap} from './common';

export const QuoteCard: React.FC<{beat: Beat; assets: AssetMap; tokens: Tokens}> = ({beat, tokens}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const quote = beat.payload?.quote;
  if (!quote) return null;

  const enter = spring({frame, fps, config: tokens.spring.gentle, durationInFrames: 20});
  const markEnter = spring({frame: Math.max(frame - 4, 0), fps, config: tokens.spring.pop, durationInFrames: 14});

  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: `${tokens.card.yCenter * 100}%`,
          width: tokens.card.width,
          transform: `translate(-50%, -50%) translateY(${(1 - enter) * 40}px)`,
          opacity: enter,
          background: tokens.color.cardBg,
          border: `1.5px solid ${tokens.color.cardBorder}`,
          borderRadius: tokens.card.radius,
          padding: tokens.card.padding + 10,
          boxShadow: '0 30px 80px rgba(0,0,0,0.55)',
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: -64,
            left: 44,
            fontFamily: 'Georgia, serif',
            fontSize: 200,
            lineHeight: 1,
            color: tokens.color.accent,
            transform: `scale(${markEnter})`,
            transformOrigin: 'bottom left',
            textShadow: '0 12px 40px rgba(0,0,0,0.4)',
          }}
        >
          “
        </div>
        <div
          style={{
            fontFamily: 'Georgia, serif',
            fontStyle: 'italic',
            fontSize: tokens.card.quoteFont,
            lineHeight: 1.34,
            color: tokens.color.text,
            marginTop: 34,
          }}
        >
          {quote.text}
        </div>
        <div
          style={{
            marginTop: 34,
            fontFamily: tokens.font.family,
            fontWeight: tokens.font.weightHeavy,
            fontSize: 32,
            letterSpacing: '0.06em',
            color: tokens.color.accent,
            textTransform: 'uppercase',
          }}
        >
          — {quote.attribution}
        </div>
      </div>
    </AbsoluteFill>
  );
};
