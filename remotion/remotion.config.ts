import {Config} from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
// Concurrency is passed per-render from render.py (RAM-bound, see BUILDLOG Phase 4).
