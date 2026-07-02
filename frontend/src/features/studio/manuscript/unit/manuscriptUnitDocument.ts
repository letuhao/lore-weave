// #12 cycle-1 · the `loreweave.manuscript-unit.v1` document provider — the FIRST consumer of the
// JSON Document Standard, and the generalized 04b raw editor. The document is the 04 envelope:
// `{ type, chapter_id, body (Tiptap JSON), scenes[] (outline metadata — D17) }`.
//
// R2 (LOCKED): the provider serves the ACTIVE Tier-4 unit only — open(chapterId) focuses that
// chapter into the hoist first (single-unit studio semantics, D13). The handle is a THIN VIEW
// over the hoist for the body (SHARED buffer with the rich editor — one document, many views)
// plus a scenes working-copy of its own (metadata edits, saved via composition patchNode OCC).
import type { ManuscriptUnitApi } from './ManuscriptUnitProvider';
import type { OutlineNode } from '@/features/composition/types';
import { compositionApi } from '@/features/composition/api';
import { extractText } from '@/lib/tiptap-utils';
import type { JSONContent } from '@tiptap/react';
import { registerJsonDocumentProvider } from '../../documents/registry';
import type { DocumentHandle, DocumentSnapshot, DocumentStatus } from '../../documents/types';

export const MANUSCRIPT_UNIT_DOC_TYPE = 'loreweave.manuscript-unit.v1';

/** The scene fields the JSON surface may edit (metadata only — D17; ids/order stay read-only). */
const EDITABLE_SCENE_FIELDS = ['title', 'synopsis', 'status'] as const;
type EditableSceneField = (typeof EDITABLE_SCENE_FIELDS)[number];

interface UnitBinding {
  api: ManuscriptUnitApi;
  token: string | null;
  projectId: string | null;
}

let binding: UnitBinding | null = null;
const listeners = new Set<() => void>();

/** Wired by ManuscriptUnitProvider on every state change (mount → live, unmount → null). */
export function _setManuscriptUnitBinding(b: UnitBinding | null): void {
  binding = b;
}

export function emitManuscriptUnitChange(): void {
  listeners.forEach((l) => l());
}

interface SceneDoc {
  node_id: string;
  title: string;
  synopsis: string;
  status: OutlineNode['status'];
  beat_role: string | null;
  story_order: number | null;
  version: number;
}

const sceneToDoc = (n: OutlineNode): SceneDoc => ({
  node_id: n.id, title: n.title, synopsis: n.synopsis, status: n.status,
  beat_role: n.beat_role, story_order: n.story_order, version: n.version,
});

/** JSON Schema (S5) — envelope + scenes strict; the Tiptap body stays an opaque object. */
export const MANUSCRIPT_UNIT_SCHEMA = {
  type: 'object',
  required: ['type', 'chapter_id', 'body', 'scenes'],
  additionalProperties: false,
  properties: {
    type: { const: MANUSCRIPT_UNIT_DOC_TYPE },
    chapter_id: { type: 'string' },
    body: { type: 'object', description: 'Tiptap document JSON (prose — scene prose lives HERE, D17)' },
    scenes: {
      type: 'array',
      items: {
        type: 'object',
        required: ['node_id', 'title', 'synopsis', 'status'],
        additionalProperties: false,
        properties: {
          node_id: { type: 'string', description: 'read-only' },
          title: { type: 'string' },
          synopsis: { type: 'string' },
          status: { enum: ['empty', 'outline', 'drafting', 'done'] },
          beat_role: { type: ['string', 'null'], description: 'read-only' },
          story_order: { type: ['number', 'null'], description: 'read-only' },
          version: { type: 'number', description: 'read-only OCC token' },
        },
      },
    },
  },
} as const;

function createManuscriptUnitHandle(chapterId: string): DocumentHandle {
  // Scene metadata edits live HERE (the body working-copy lives in the hoist — shared with the
  // rich editor). Keyed by node_id; only fields that actually differ are kept.
  let sceneEdits = new Map<string, Partial<Record<EditableSceneField, unknown>>>();
  let status: DocumentStatus | null = null; // local save-cycle status; null = derive from the hoist
  let detail: string | null = null;
  let snapshot: DocumentSnapshot | null = null;
  const handleListeners = new Set<() => void>();

  const emit = () => { snapshot = null; handleListeners.forEach((l) => l()); };
  const busUnsub: (() => void)[] = [];
  // Follow the hoist: any unit state change invalidates our snapshot too.
  const globalListener = () => emit();
  listeners.add(globalListener);
  busUnsub.push(() => listeners.delete(globalListener));

  const mergedScenes = (unitScenes: OutlineNode[]): SceneDoc[] =>
    unitScenes.map((n) => {
      const edit = sceneEdits.get(n.id);
      const base = sceneToDoc(n);
      return edit ? { ...base, ...edit } as SceneDoc : base;
    });

  const build = (): DocumentSnapshot => {
    const b = binding;
    if (!b) return { doc: null, etag: null, dirty: false, status: 'error', detail: 'manuscript unit unavailable' };
    const s = b.api.state;
    if (s.chapterId !== chapterId) {
      return { doc: null, etag: null, dirty: false, status: 'error', detail: 'not the active chapter (R2)' };
    }
    return {
      doc: {
        type: MANUSCRIPT_UNIT_DOC_TYPE,
        chapter_id: chapterId,
        body: s.workingBody ?? s.savedBody,
        scenes: mergedScenes(s.scenes),
      },
      etag: s.version ?? null,
      dirty: b.api.isDirty || sceneEdits.size > 0,
      status: status ?? (s.saveState === 'loading' ? 'loading' : s.saveState === 'saving' ? 'saving' : s.saveState === 'error' ? 'error' : 'idle'),
      detail: detail ?? s.error,
    };
  };

  return {
    type: MANUSCRIPT_UNIT_DOC_TYPE,
    resourceId: chapterId,
    getSnapshot: () => (snapshot ??= build()),
    subscribe: (l) => {
      handleListeners.add(l);
      return () => handleListeners.delete(l);
    },
    update: (doc) => {
      const b = binding;
      if (!b || b.api.state.chapterId !== chapterId) return;
      const d = doc as { body?: unknown; scenes?: unknown };
      // Body → the SHARED hoist working buffer (the rich editor sees it live).
      if (d.body && typeof d.body === 'object') {
        const cur = b.api.state.workingBody ?? b.api.state.savedBody;
        if (JSON.stringify(d.body) !== JSON.stringify(cur)) {
          const body = d.body as JSONContent;
          b.api.setBody(body, extractText(body));
        }
      }
      // Scenes → the metadata working-copy. Only KNOWN node_ids and editable fields;
      // additions/removals are ignored (creation via the outline tools, not raw JSON).
      if (Array.isArray(d.scenes)) {
        const next = new Map<string, Partial<Record<EditableSceneField, unknown>>>();
        const byId = new Map(b.api.state.scenes.map((n) => [n.id, n]));
        for (const raw of d.scenes as Array<Record<string, unknown>>) {
          const id = typeof raw?.node_id === 'string' ? raw.node_id : null;
          const node = id ? byId.get(id) : undefined;
          if (!node) continue;
          const edit: Partial<Record<EditableSceneField, unknown>> = {};
          for (const f of EDITABLE_SCENE_FIELDS) {
            if (f in raw && raw[f] !== (node as unknown as Record<string, unknown>)[f]) edit[f] = raw[f];
          }
          if (Object.keys(edit).length) next.set(id, edit);
        }
        sceneEdits = next;
      }
      status = null; detail = null;
      emit();
    },
    save: async () => {
      const b = binding;
      if (!b || !b.token || b.api.state.chapterId !== chapterId) return;
      status = 'saving'; detail = null; emit();
      // Phase 1 — body via the hoist's own save (draft PATCH, OCC draft_version). R5: per-part.
      if (b.api.isDirty) {
        await b.api.save();
        if (b.api.state.saveState === 'error') {
          status = 'error'; detail = `body: ${b.api.state.error ?? 'save failed'}`; emit();
          return;
        }
      }
      // Phase 2 — scene metadata via composition patchNode (If-Match version → 412 conflict).
      for (const [nodeId, edit] of sceneEdits) {
        const node = b.api.state.scenes.find((n) => n.id === nodeId);
        if (!node) continue;
        try {
          await compositionApi.patchNode(nodeId, edit as Partial<OutlineNode>, b.token, node.version);
        } catch (e) {
          const err = e as { status?: number };
          status = err.status === 412 ? 'conflict' : 'error';
          detail = `scenes: ${nodeId}${err.status === 412 ? ' (stale version)' : ''}`;
          emit();
          return;
        }
      }
      sceneEdits = new Map();
      await b.api.reloadScenes();
      status = null; detail = null;
      emit();
    },
    revert: () => {
      const b = binding;
      sceneEdits = new Map();
      status = null; detail = null;
      if (b && b.api.state.chapterId === chapterId && b.api.isDirty) b.api.revert();
      emit();
    },
    reload: async () => {
      const b = binding;
      if (!b || b.api.state.chapterId !== chapterId) return;
      // R6/G7 per-buffer: scenes always; body only when it has no local edits.
      await b.api.reloadScenes();
      if (!b.api.isDirty) await b.api.reload();
      emit();
    },
    release: () => {
      busUnsub.forEach((u) => u());
      handleListeners.clear();
    },
  };
}

let registered = false;

/** Idempotent — called by ManuscriptUnitProvider on mount. */
export function registerManuscriptUnitDocumentProvider(): void {
  if (registered) return;
  registered = true;
  registerJsonDocumentProvider({
    type: MANUSCRIPT_UNIT_DOC_TYPE,
    schema: MANUSCRIPT_UNIT_SCHEMA,
    titleKey: 'panels.jsonEditor.title',
    open: async (_ctx, chapterId) => {
      // R2 — single-unit semantics: focus the requested chapter into the hoist first.
      const b = binding;
      if (!b) throw new Error('manuscript unit unavailable (studio not mounted)');
      if (b.api.state.chapterId !== chapterId) await b.api.openUnit(chapterId);
      return createManuscriptUnitHandle(chapterId);
    },
  });
}

/** Test-only: reset the module registration guard + binding. */
export function _resetManuscriptUnitDocumentProvider(): void {
  registered = false;
  binding = null;
  listeners.clear();
}
