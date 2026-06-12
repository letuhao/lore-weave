// Chapter revision compare (1-vs-1 diff) types — mirror the book-service
// /v1/books/{id}/chapters/{cid}/revisions/compare contract.

export type DiffOp = 'equal' | 'insert' | 'delete';

/** One server-computed line-diff op (left=equal+delete, right=equal+insert). */
export type DiffLine = {
  op: DiffOp;
  text: string;
};

export type RevisionSide = {
  revision_id: string;
  chapter_id: string;
  created_at: string;
  author_user_id: string | null;
  message: string | null;
  body: unknown; // TipTap JSON
  body_format: string;
  text_content: string | null;
};

export type RevisionCompare = {
  left: RevisionSide;
  right: RevisionSide;
  diff: DiffLine[];
  /** true → the diff was degraded to a full replace (server perf guard). */
  truncated: boolean;
};

/** A revision summary from the list endpoint (used by the compare pickers). */
export type RevisionSummary = {
  revision_id: string;
  created_at: string;
  message?: string;
};
