/** URL parsing helpers for capturing IDs from app navigation. */

export function extractBookIdFromUrl(url: string): string {
  const match = url.match(/\/books\/([^/?#]+)/);
  if (!match) {
    throw new Error(`no bookId found in URL: ${url}`);
  }
  return match[1];
}

export function extractChapterIdFromEditorUrl(url: string): string {
  const match = url.match(/\/chapters\/([^/?#]+)\/edit/);
  if (!match) {
    throw new Error(`no chapterId found in editor URL: ${url}`);
  }
  return match[1];
}
