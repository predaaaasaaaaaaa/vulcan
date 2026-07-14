/** Treatment registry — the enum the Director picks from maps 1:1 here. */

import React from 'react';
import type {Tokens} from '../tokens';
import type {Beat, Treatment} from '../types';
import type {AssetMap} from './common';
import {ChartPop} from './ChartPop';
import {CutoutPop} from './CutoutPop';
import {EmojiBurst} from './EmojiBurst';
import {KineticType} from './KineticType';
import {ListStack} from './ListStack';
import {LogoVersus} from './LogoVersus';
import {NetworkGrow} from './NetworkGrow';
import {QuoteCard} from './QuoteCard';
import {ScreenshotZoom} from './ScreenshotZoom';
import {StatSlam} from './StatSlam';
import {TweetCard} from './TweetCard';

type TreatmentComponent = React.FC<{beat: Beat; assets: AssetMap; tokens: Tokens}>;

export const TREATMENTS: Record<Treatment, TreatmentComponent> = {
  kinetic_type: KineticType,
  cutout_pop: CutoutPop,
  stat_slam: StatSlam,
  list_stack: ListStack,
  tweet_card: TweetCard,
  screenshot_zoom: ScreenshotZoom,
  logo_versus: LogoVersus,
  emoji_burst: EmojiBurst,
  quote_card: QuoteCard,
  chart_pop: ChartPop,
  network_grow: NetworkGrow,
};
