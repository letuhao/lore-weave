import { createContext, useContext, type ReactNode } from 'react';

/**
 * wiki-llm M7a — optional context carrying the BOOK the article belongs to, so a
 * `CitationChip` deep inside the shared `InlineRenderer` can build its
 * jump-to-source link (`/books/{bookId}/chapters/{chapterId}/read?block=N`)
 * without prop-drilling through ContentRenderer's many other callers.
 *
 * Optional by design: the wiki reader (authed + public) provides it; every other
 * ContentRenderer consumer (chapter reader, revision history, translation review)
 * does not — there the citation chip degrades to "popover only, no jump link".
 */
interface CitationContextValue {
  bookId?: string;
}

const CitationContext = createContext<CitationContextValue>({});

export function CitationProvider({
  bookId,
  children,
}: {
  bookId?: string;
  children: ReactNode;
}) {
  return (
    <CitationContext.Provider value={{ bookId }}>
      {children}
    </CitationContext.Provider>
  );
}

export function useCitationContext(): CitationContextValue {
  return useContext(CitationContext);
}
