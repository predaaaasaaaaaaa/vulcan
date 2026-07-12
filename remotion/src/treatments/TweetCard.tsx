/**
 * tweet_card — SYNTHETIC tweet rendered natively (never scraped, always crisp).
 * Springs in with a slight rotate; avatar = initials disc in accent.
 */

import React from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from '../tokens';
import type {Beat} from '../types';

const initials = (name: string): string =>
  name.split(/\s+/).map((p) => p[0] ?? '').join('').slice(0, 2).toUpperCase();

export const TweetCard: React.FC<{beat: Beat; assets: unknown; tokens: Tokens}> = ({beat, tokens}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const tweet = beat.payload?.tweet;
  if (!tweet) return null;

  const enter = spring({frame, fps, config: tokens.spring.pop, durationInFrames: 18});

  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: `${tokens.card.yCenter * 100}%`,
          width: tokens.card.width,
          transform: `translate(-50%, -50%) rotate(${(1 - enter) * -4 - 1.2}deg) scale(${0.9 + enter * 0.1})`,
          opacity: enter,
          background: tokens.color.cardBg,
          border: `1.5px solid ${tokens.color.cardBorder}`,
          borderRadius: tokens.card.radius,
          padding: tokens.card.padding,
          boxShadow: '0 30px 80px rgba(0,0,0,0.55)',
          fontFamily: tokens.font.family,
        }}
      >
        <div style={{display: 'flex', alignItems: 'center', gap: 24}}>
          <div
            style={{
              width: 88, height: 88, borderRadius: '50%',
              background: tokens.color.accent, color: '#0A0A0C',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: tokens.font.weightBlack, fontSize: 34,
            }}
          >
            {initials(tweet.author)}
          </div>
          <div style={{display: 'flex', flexDirection: 'column', gap: 2}}>
            <div style={{display: 'flex', alignItems: 'center', gap: 12}}>
              <span style={{color: tokens.color.text, fontWeight: tokens.font.weightHeavy, fontSize: 38}}>
                {tweet.author}
              </span>
              {/* verified badge */}
              <svg width="34" height="34" viewBox="0 0 24 24" fill="#1D9BF0">
                <path d="M22.25 12c0-1.43-.88-2.67-2.19-3.34.46-1.39.2-2.9-.81-3.91s-2.52-1.27-3.91-.81c-.66-1.31-1.91-2.19-3.34-2.19s-2.67.88-3.33 2.19c-1.4-.46-2.91-.2-3.92.81s-1.26 2.52-.8 3.91c-1.31.67-2.2 1.91-2.2 3.34s.89 2.67 2.2 3.34c-.46 1.39-.21 2.9.8 3.91s2.52 1.26 3.91.81c.67 1.31 1.91 2.19 3.34 2.19s2.68-.88 3.34-2.19c1.39.45 2.9.2 3.91-.81s1.27-2.52.81-3.91c1.31-.67 2.19-1.91 2.19-3.34zm-11.71 4.2L6.8 12.46l1.41-1.42 2.26 2.26 4.8-5.23 1.47 1.36-6.2 6.77z" />
              </svg>
            </div>
            <span style={{color: tokens.color.dim, fontWeight: 600, fontSize: 30}}>{tweet.handle}</span>
          </div>
        </div>
        <div
          style={{
            marginTop: 30,
            color: tokens.color.text,
            fontSize: tokens.card.tweetFont,
            lineHeight: 1.3,
            fontWeight: 600,
          }}
        >
          {tweet.text}
        </div>
        <div style={{marginTop: 28, color: tokens.color.dim, fontSize: 26, fontWeight: 500}}>
          {`9:41 AM · Today`}
        </div>
      </div>
    </AbsoluteFill>
  );
};
