/** URL parsing helpers for capturing IDs from app navigation. */

export function extractBookIdFromUrl(url: string): string {
  const match = url.match(/\/books\/([^/?#]+)/);
  if (!match) {
    throw new Error(`no bookId found in URL: ${url}`);
  }
  return match[1];
}

export function extractChapterIdFromEditorUrl(url: string): string {
  // The Writing Studio is the only chapter editor: /books/:id/studio?chapter=:chapterId.
  // The retired /chapters/:id/edit route is only a redirect to that URL, so by the time a
  // test reads page.url() it is the Studio's. An URL without `chapter=` throws, so this
  // cannot quietly return a wrong id.
  const match = url.match(/[?&]chapter=([^&#]+)/);
  if (!match) {
    throw new Error(`no chapterId found in editor URL: ${url}`);
  }
  return match[1];
}
