// Raw search — Phase 1 (lexical leg). Mirrors book-service
// services/book-service/internal/api/search.go response shape.

export interface RawSearchLocation {
  blockIndex: number;
  headingContext: string | null;
  /** Unicode CODE-POINT offsets of the match within the block (jump-to-source). */
  charStart: number;
  charEnd: number;
}

export interface RawSearchHit {
  chapterId: string;
  chapterTitle: string | null;
  sortOrder: number;
  /** v1 lexical leg only emits "draft" (canon = Phase 2). */
  surface: 'draft' | 'canon';
  matchType: 'lexical' | 'semantic' | 'both';
  score: number;
  /** Verbatim windowed excerpt of the matched block. */
  snippet: string;
  /** [start, end] CODE-POINT offset pairs into `snippet` (book-service emits
   *  rune offsets — render with Array.from, NOT String.slice; see renderHighlight). */
  highlights: number[][];
  location: RawSearchLocation;
}

export interface RawSearchResponse {
  query: string;
  mode: string;
  results: RawSearchHit[];
}

export interface RawSearchParams {
  q: string;
  surface?: 'draft' | 'canon' | 'all';
  limit?: number;
}
