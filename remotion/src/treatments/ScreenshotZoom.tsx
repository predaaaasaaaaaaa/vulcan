/**
 * screenshot_zoom — framed screenshot with slow Ken Burns push.
 * Frame = rounded corners + hairline border + deep shadow; reads like a
 * floating browser window over the void.
 */

import React from 'react';
import {AbsoluteFill, Img, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Tokens} from '../tokens';
import type {Beat} from '../types';
import type {AssetMap} from './common';
import {src, useAssetWindow} from './common';

export const ScreenshotZoom: React.FC<{beat: Beat; assets: AssetMap; tokens: Tokens}> = ({
  beat, assets, tokens,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const heroRef = beat.assets.find((a) => a.role === 'hero') ?? beat.assets[0];
  if (!heroRef) return null;
  const {visible, enter, exit, enterF, exitF} = useAssetWindow(heroRef, tokens, 'gentle');
  const asset = assets[heroRef.asset_id];
  if (!asset || !visible) return null;

  const kb = interpolate(frame, [enterF, exitF], [1, tokens.screenshot.kenBurnsScale], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: `${tokens.screenshot.yCenter * 100}%`,
          transform: `translate(-50%, -50%) translateY(${(1 - enter) * 60}px)`,
          opacity: Math.min(enter * 1.3, 1) * exit,
          width: tokens.canvas.width * tokens.screenshot.maxWidthFrac,
          borderRadius: tokens.screenshot.frameRadius,
          overflow: 'hidden',
          border: `1.5px solid ${tokens.color.cardBorder}`,
          boxShadow: '0 40px 100px rgba(0,0,0,0.6)',
          background: tokens.color.cardBg,
        }}
      >
        {/* faux browser chrome */}
        <div style={{display: 'flex', gap: 10, padding: '18px 22px', background: '#1B1B22'}}>
          {['#FF5F57', '#FEBC2E', '#28C840'].map((c) => (
            <div key={c} style={{width: 18, height: 18, borderRadius: '50%', background: c}} />
          ))}
        </div>
        <div style={{overflow: 'hidden'}}>
          <Img
            src={src(asset)}
            style={{
              width: '100%',
              display: 'block',
              transform: `scale(${kb})`,
              transformOrigin: '50% 30%',
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};
