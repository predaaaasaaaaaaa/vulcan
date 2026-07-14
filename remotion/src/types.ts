/** Manifest types — mirrors schemas/manifest.schema.json exactly. */

export type Word = {w: string; s: number; e: number; p?: number};

export type Treatment =
  | 'kinetic_type' | 'cutout_pop' | 'stat_slam' | 'list_stack' | 'tweet_card'
  | 'screenshot_zoom' | 'logo_versus' | 'emoji_burst' | 'quote_card' | 'chart_pop' | 'network_grow';

export type AssetRole = 'hero' | 'secondary' | 'background' | 'left' | 'right';
export type CameraMove = 'static' | 'punch_in' | 'drift';
export type TransitionOut = 'hard_cut' | 'whip' | 'flash';

export type BeatAssetRef = {
  asset_id: string;
  role: AssetRole;
  enter_ms: number; // relative to beat start
  exit_ms: number;
};

export type SfxRef = {cue: string; at_ms: number};

export type TextOverlay = {
  mode: 'karaoke' | 'headline';
  emphasis_words?: string[];
  headline_text?: string;
};

export type Payload = {
  stat_text?: string;
  chart?: {kind: 'bar_up' | 'bar_down' | 'line_up' | 'line_down'; label: string};
  network?: {label: string};
  items?: {text: string; at_ms: number}[];
  tweet?: {author: string; handle: string; text: string};
  quote?: {text: string; attribution: string};
};

export type Beat = {
  id: string;
  start_ms: number;
  end_ms: number;
  words: Word[];
  treatment: Treatment;
  text_overlay: TextOverlay;
  assets: BeatAssetRef[];
  sfx: SfxRef[];
  camera: CameraMove;
  transition_out: TransitionOut;
  payload?: Payload;
};

export type ManifestAsset = {
  asset_id: string;
  type: 'photo_cutout' | '3d_icon' | 'flat_icon' | 'logo' | 'lottie' | 'emoji' | 'screenshot';
  queries: string[];
  path: string | null;   // rewritten by render.py to a staticFile()-relative key
  status: string;
  score: number | null;
};

export type Manifest = {
  video_id: string;
  fps: 30;
  aspect: '9:16';
  audio: {path: string; duration_ms: number};
  beats: Beat[];
  assets: ManifestAsset[];
  music?: {mood: 'energetic' | 'chill' | 'dramatic' | 'uplifting' | 'tech' | 'none'; file: string | null};
  post_kit?: {hook: string; caption: string; hashtags: string[]};
};

export type MasterProps = {
  manifest: Manifest;
  style?: {accent?: string};
};

export const msToFrame = (ms: number, fps = 30): number => Math.round((ms * fps) / 1000);
