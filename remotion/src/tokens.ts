/**
 * tokens.ts — THE single style source. Every color, size, spring and timing
 * constant lives here. Components never hardcode style values.
 *
 * The accent color can be overridden per-render from config.yaml via
 * inputProps.style.accent (render.py injects it) — nothing else is overridable.
 */

export const TOKENS = {
  canvas: {width: 1080, height: 1920, fps: 30},

  color: {
    bg: '#0A0A0C',
    bgGradientA: '#101018',
    bgGradientB: '#0A0A0C',
    text: '#FFFFFF',
    accent: '#FFCC00', // default; overridden via inputProps.style.accent
    dim: '#8A8F98',
    shadow: 'rgba(0,0,0,0.55)',
    cardBg: '#16161C',
    cardBorder: 'rgba(255,255,255,0.10)',
    danger: '#FF4D4D',
  },

  font: {
    family: 'Outfit',
    weightHeavy: 800,
    weightBlack: 900,
  },

  caption: {
    fontSize: 76,
    lineHeight: 1.12,
    letterSpacing: '-0.01em',
    /** vertical center of the caption block as fraction of canvas height */
    yCenter: 0.70,
    maxGroupWords: 4,
    minGroupWords: 3,
    emphasisScale: 1.08,
    inactiveOpacity: 0.92,
    strokePx: 0,
    textShadow: '0 4px 24px rgba(0,0,0,0.65), 0 2px 6px rgba(0,0,0,0.5)',
    maxWidthPx: 940,
    wordGap: 30, // scale pops overflow their layout box — gap must absorb it
  },

  headline: {
    fontSize: 96,
    lineHeight: 1.05,
    underlineWidth: 180,
    underlineHeight: 10,
  },

  cutout: {
    strokePx: 12,          // baked by stamp.py; listed for reference
    maxWidthFrac: 0.72,
    maxHeightFrac: 0.42,
    yCenter: 0.38,         // hero art sits above the captions
    rotateDeg: -3,
  },

  stat: {
    fontSize: 240,
    countUpMs: 700,
    yCenter: 0.36,
  },

  list: {
    fontSize: 64,
    rowGap: 36,
    yTop: 0.22,
    maxWidthPx: 880,
  },

  card: {
    // tweet_card + quote_card share the card language
    width: 920,
    radius: 28,
    padding: 48,
    tweetFont: 48,
    quoteFont: 54,
    yCenter: 0.36,
  },

  spring: {
    pop:    {damping: 12, stiffness: 170, mass: 0.8},
    slam:   {damping: 15, stiffness: 320, mass: 0.9},
    gentle: {damping: 18, stiffness: 110, mass: 1.0},
  },

  camera: {
    punchInScale: 1.07,
    driftScale: 1.045,
    driftPanPx: 26,
  },

  transition: {
    whipFrames: 7,
    flashFrames: 4,
  },

  grain: {opacity: 0.055},

  emojiBurst: {
    heroSizePx: 460,
    yCenter: 0.36,
    burstCount: 8,
  },

  screenshot: {
    frameRadius: 24,
    maxWidthFrac: 0.86,
    yCenter: 0.36,
    kenBurnsScale: 1.10,
  },
} as const;

export type Tokens = Omit<typeof TOKENS, 'color'> & {
  color: Omit<(typeof TOKENS)['color'], 'accent'> & {accent: string};
};

/** Accent override plumbing — Master reads inputProps.style?.accent. */
export const withAccent = (accent?: string): Tokens =>
  accent && /^#[0-9A-Fa-f]{6}$/.test(accent)
    ? {...TOKENS, color: {...TOKENS.color, accent}}
    : (TOKENS as Tokens);
