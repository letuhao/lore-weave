// F15 — web fonts are an enhancement; they must never gate the app.
//
// `index.html` used to load Google Fonts as an ordinary <link rel="stylesheet">. A stylesheet
// blocks the document's `load` event, so when fonts.googleapis.com did not answer — a filtered or
// air-gapped network, or just a stalled request — the page never finished loading. Measured: the
// one request that never completed in a hung load was this stylesheet (status -1), with every
// same-origin resource done in under 200ms and the host idle.
//
// Inserted after `load`, the stylesheet can no longer hold it. The CSS carries `display=swap`, and
// every family already has a fallback stack (tailwind.config.cjs), so text renders at once in the
// fallback and swaps when — if — the web font arrives.
export const WEB_FONTS_HREF =
  'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700' +
  '&family=Lora:ital,wght@0,400;0,500;0,600;1,400&family=JetBrains+Mono:wght@400;500&display=swap';

export function loadWebFonts(doc: Document = document, win: Window = window): void {
  const insert = () => {
    if (doc.querySelector(`link[data-web-fonts]`)) return;
    const link = doc.createElement('link');
    link.rel = 'stylesheet';
    link.href = WEB_FONTS_HREF;
    link.setAttribute('data-web-fonts', '');
    doc.head.appendChild(link);
  };
  if (doc.readyState === 'complete') insert();
  else win.addEventListener('load', insert, { once: true });
}
