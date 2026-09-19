// The one place that builds a link into the Writing Studio.
//
// The legacy chapter editor (`/books/:bookId/chapters/:chapterId/edit`) is RETIRED: the Writing
// Studio is the only writing surface. Its route now only redirects here, so a bookmark or an old
// link still lands somewhere useful, and every in-app "open this chapter" goes straight to the
// Studio. `?chapter=` is the Studio's own deep link (WritingStudioPage reads it).
export function studioChapterPath(bookId: string, chapterId?: string | null): string {
  const base = `/books/${encodeURIComponent(bookId)}/studio`;
  return chapterId ? `${base}?chapter=${encodeURIComponent(chapterId)}` : base;
}
