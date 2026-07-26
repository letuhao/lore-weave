// #12 JSON Document Standard — the studio's 4th registry (S1) + the model–view split (S2).
// A PROVIDER claims a versioned document type (`loreweave.<resource>.v1`) and can open a
// resource into a DocumentHandle. Views (json-editor panel, GUI panels, future diff views)
// share ONE handle per (type, resourceId) — save/revert/dirty live on the HANDLE, never on a
// panel (VS Code supportsMultipleEditorsPerDocument lesson).
//
// S3: save() always wraps the owning DOMAIN API (OCC via etag) — never a generic write. The
// agent's write path stays MCP; this surface is for users + rendering agent-proposed diffs.

export interface DocContext {
  token: string;
  bookId: string;
}

/** Which part of a composite document hit an OCC conflict ('body' | 'scenes' | … — R5). */
export type DocumentStatus = 'idle' | 'loading' | 'saving' | 'error' | 'conflict';

export interface DocumentSnapshot {
  doc: unknown;                 // canonical JSON document (envelope per the provider's type)
  etag: string | number | null; // OCC token (draft_version, updated_at, …)
  dirty: boolean;
  status: DocumentStatus;
  /** conflict part (R5) or error message; null when status is idle/loading/saving. */
  detail: string | null;
}

export interface DocumentHandle {
  readonly type: string;
  readonly resourceId: string;
  getSnapshot(): DocumentSnapshot;
  /** All views re-render from here (external-store contract, like the host stores). */
  subscribe(listener: () => void): () => void;
  /** View → handle. Marks dirty; does NOT persist. */
  update(doc: unknown): void;
  /** Persist through the domain API (S3). Conflict/error land in the snapshot, never throw. */
  save(): Promise<void>;
  /** Drop local edits back to the last loaded/saved doc. */
  revert(): void;
  /** Re-fetch from the domain (Lane-B refresh path). MUST respect dirty buffers (G7/R6). */
  reload(): Promise<void>;
  /** Refcount down — the registry disposes the handle at zero. */
  release(): void;
}

export interface JsonDocumentProvider {
  /** Versioned envelope id, e.g. 'loreweave.manuscript-unit.v1'. */
  type: string;
  /** JSON Schema for CM6 validation + autocomplete (S5). Optional — opaque docs skip it. */
  schema?: object;
  /** Human-readable dock-tab label key (studio i18n ns), e.g. 'documents.manuscriptUnit'. */
  titleKey?: string;
  /** The doc type is immutable output (e.g. a plan-pass artifact). The json-editor renders it as
   *  a VIEWER: no Save, no Revert, no ⌘S. Default false = today's editable behaviour. A property
   *  of the TYPE, not a resource instance — every artifact of this type is read-only. */
  readOnly?: boolean;
  /** Open (or join) the shared handle for one resource. The registry refcounts. */
  open(ctx: DocContext, resourceId: string): Promise<DocumentHandle> | DocumentHandle;
}
