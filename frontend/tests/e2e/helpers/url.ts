/** URL parsing helpers for capturing IDs from app navigation. */

export function extractBookIdFromUrl(url: string): string {
  const match = url.match(/\/books\/([^/?#]+)/);
  if (!match) {
    throw new Error(`no bookId found in URL: ${url}`);
  }
  return match[1];
}

export function extractChapterIdFromEditorUrl(url: string): string {
  // There are TWO editor routes. #18 made chapter creation land in the Studio
  // (/books/:id/studio?chapter=:chapterId); the classic /chapters/:id/edit route still
  // exists and other flows still reach it. Both are "the editor", so both are read here —
  // and an URL carrying NEITHER still throws, so this cannot quietly return a wrong id.
  const match =
    url.match(/[?&]chapter=([^&#]+)/) ?? url.match(/\/chapters\/([^/?#]+)\/edit/);
  if (!match) {
    throw new Error(`no chapterId found in editor URL: ${url}`);
  }
  return match[1];
}
