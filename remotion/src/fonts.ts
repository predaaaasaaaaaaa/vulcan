/** Offline font loading — committed variable TTF, no network ever. */

import {continueRender, delayRender, staticFile} from 'remotion';

let loaded = false;

export const ensureFont = (): void => {
  if (loaded) return;
  loaded = true;
  const handle = delayRender('load Outfit font');
  const font = new FontFace(
    'Outfit',
    `url(${staticFile('fonts/Outfit-Variable.ttf')}) format('truetype-variations')`,
    {weight: '100 900'},
  );
  font
    .load()
    .then(() => {
      document.fonts.add(font);
      continueRender(handle);
    })
    .catch((err) => {
      // Fail the render loudly — a fallback font would silently break the look.
      throw err;
    });
};
