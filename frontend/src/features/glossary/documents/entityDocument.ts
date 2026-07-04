// 13_glossary_panels.md A2 · the `loreweave.glossary-entity.v1` document provider — Glossary's
// first JSON Document Standard (spec 12) consumer. Mirrors manuscriptUnitDocument.ts's
// module-level binding-bridge pattern: `useGlossaryEntity` is a React hook and can't be called
// from the plain (non-React) `open()`/handle functions, so EntityEditorModal publishes its live
// hook instance here on mount/update and clears it on unmount.
//
// Unlike manuscript-unit there is no persistent Tier-4 provider above dockview — the entity
// editor stays a MODAL (13_glossary_panels.md G1) — so the handle is only servable while SOME
// EntityEditorModal instance for that exact entityId is mounted (mirrors R2's "active unit only"
// restriction, just modal-scoped instead of dock-scoped).
import type { UseGlossaryEntityResult } from '../hooks/useGlossaryEntity';
import { registerJsonDocumentProvider } from '@/features/studio/documents/registry';
import type { DocumentHandle, DocumentSnapshot, DocumentStatus } from '@/features/studio/documents/types';

export const GLOSSARY_ENTITY_DOC_TYPE = 'loreweave.glossary-entity.v1';

interface EntityBinding {
  api: UseGlossaryEntityResult;
  entityId: string;
}

let binding: EntityBinding | null = null;
const listeners = new Set<() => void>();

/** Wired by EntityEditorModal on every render (mount → live, unmount → null). */
export function _setGlossaryEntityBinding(b: EntityBinding | null): void {
  binding = b;
  listeners.forEach((l) => l());
}

/** 13_glossary_panels.md A5 (Lane B) — reload the entity editor's hoist if (and only if) its
 * modal is open for EXACTLY this entityId. A no-op otherwise (no modal open / a different
 * entity) or when the user has an unsaved edit in flight (G7 — useGlossaryEntity.reload()
 * unconditionally clears pendingChanges, so the guard belongs HERE, at the call site, same
 * shape as entityDocument's own DocumentHandle.reload()). Plain module read, no reconciler
 * wiring needed — unlike manuscript-unit's persistent hoist, the binding is a bare singleton. */
export function reloadBoundGlossaryEntity(entityId: string): void {
  if (binding && binding.entityId === entityId && !binding.api.isDirty) {
    void binding.api.reload();
  }
}

interface AttrDoc {
  attr_value_id: string; // read-only
  code: string;          // read-only
  name: string;          // read-only
  value: string;
}

/** JSON Schema (S5). Evidence/translations/history stay out of this envelope — a separate
 * concern from the attribute+status power-edit surface (mirrors D17: scene prose stays in
 * chapter.body, not the raw scenes[] metadata). */
export const GLOSSARY_ENTITY_SCHEMA = {
  type: 'object',
  required: ['type', 'entity_id', 'status', 'attributes'],
  additionalProperties: false,
  properties: {
    type: { const: GLOSSARY_ENTITY_DOC_TYPE },
    entity_id: { type: 'string', description: 'read-only' },
    status: { enum: ['draft', 'active', 'inactive'] },
    tags: { type: 'array', items: { type: 'string' }, description: 'read-only (no tag-edit path yet)' },
    attributes: {
      type: 'array',
      items: {
        type: 'object',
        required: ['attr_value_id', 'code', 'name', 'value'],
        additionalProperties: false,
        properties: {
          attr_value_id: { type: 'string', description: 'read-only' },
          code: { type: 'string', description: 'read-only' },
          name: { type: 'string', description: 'read-only' },
          value: { type: 'string' },
        },
      },
    },
  },
} as const;

function createGlossaryEntityHandle(entityId: string): DocumentHandle {
  let pendingStatus: string | null = null;
  let status: DocumentStatus | null = null; // local save-cycle status; null = derive from the hoist
  let detail: string | null = null;
  let snapshot: DocumentSnapshot | null = null;
  const handleListeners = new Set<() => void>();

  const emit = () => { snapshot = null; handleListeners.forEach((l) => l()); };
  const globalListener = () => emit();
  listeners.add(globalListener);

  const build = (): DocumentSnapshot => {
    const b = binding;
    if (!b || b.entityId !== entityId) {
      return { doc: null, etag: null, dirty: false, status: 'error', detail: 'entity editor not open for this entity (modal-scoped, mirrors R2)' };
    }
    const { entity, isDirty, getValue } = b.api;
    if (!entity) return { doc: null, etag: null, dirty: false, status: 'loading', detail: null };
    return {
      doc: {
        type: GLOSSARY_ENTITY_DOC_TYPE,
        entity_id: entityId,
        status: pendingStatus ?? entity.status,
        tags: entity.tags,
        attributes: entity.attribute_values.map((av): AttrDoc => ({
          attr_value_id: av.attr_value_id,
          code: av.attribute_def.code,
          name: av.attribute_def.name,
          value: getValue(av),
        })),
      },
      etag: entity.updated_at,
      dirty: isDirty || pendingStatus !== null,
      status: status ?? (b.api.saving ? 'saving' : 'idle'),
      detail,
    };
  };

  return {
    type: GLOSSARY_ENTITY_DOC_TYPE,
    resourceId: entityId,
    getSnapshot: () => (snapshot ??= build()),
    subscribe: (l) => {
      handleListeners.add(l);
      return () => handleListeners.delete(l);
    },
    update: (doc) => {
      const b = binding;
      if (!b || b.entityId !== entityId || !b.api.entity) return;
      const d = doc as { status?: unknown; attributes?: unknown };
      // Always RECOMPUTE against the original (never a conditional set-only) — a user who edits
      // the status then reverts it back to the original value via the same JSON buffer must
      // clear pendingStatus, not leave it holding the stale intermediate value (a `save()` would
      // otherwise persist a status the user's own visible JSON no longer shows — /review-impl).
      if (typeof d.status === 'string') {
        pendingStatus = d.status !== b.api.entity.status ? d.status : null;
      }
      if (Array.isArray(d.attributes)) {
        const byId = new Map(b.api.entity.attribute_values.map((av) => [av.attr_value_id, av]));
        for (const raw of d.attributes as Array<Record<string, unknown>>) {
          const id = typeof raw?.attr_value_id === 'string' ? raw.attr_value_id : null;
          const av = id ? byId.get(id) : undefined;
          if (!id || !av || typeof raw.value !== 'string') continue;
          if (raw.value !== b.api.getValue(av)) b.api.setValue(id, raw.value);
        }
      }
      status = null; detail = null;
      emit();
    },
    save: async () => {
      const b = binding;
      if (!b || b.entityId !== entityId) return;
      status = 'saving'; detail = null; emit();
      // Phase 1 — attribute values via the hoist's own per-attribute PATCH loop.
      if (b.api.isDirty) {
        try {
          await b.api.save();
        } catch (e) {
          status = 'error'; detail = `attributes: ${(e as Error).message}`; emit();
          return;
        }
      }
      // Phase 2 — status, a separate write (patchEntity), same conflict-surfacing shape as
      // manuscript-unit's two-phase save (R5: no fake atomicity across independent OCC paths).
      if (pendingStatus !== null) {
        try {
          await b.api.setStatus(pendingStatus);
          pendingStatus = null;
        } catch (e) {
          status = 'error'; detail = `status: ${(e as Error).message}`; emit();
          return;
        }
      }
      status = null; detail = null;
      emit();
    },
    revert: () => {
      const b = binding;
      pendingStatus = null;
      status = null; detail = null;
      if (b && b.entityId === entityId && b.api.isDirty) b.api.discard();
      emit();
    },
    reload: async () => {
      const b = binding;
      if (!b || b.entityId !== entityId) return;
      // G7 — never clobber an in-flight edit; the hook's reload() unconditionally clears
      // pendingChanges, so only call it when there is nothing local to lose.
      if (!b.api.isDirty && pendingStatus === null) await b.api.reload();
      emit();
    },
    release: () => {
      listeners.delete(globalListener);
      handleListeners.clear();
    },
  };
}

let registered = false;

/** Idempotent — called by EntityEditorModal on mount. */
export function registerGlossaryEntityDocumentProvider(): void {
  if (registered) return;
  registered = true;
  registerJsonDocumentProvider({
    type: GLOSSARY_ENTITY_DOC_TYPE,
    schema: GLOSSARY_ENTITY_SCHEMA,
    titleKey: 'panels.jsonEditor.title',
    open: async (_ctx, entityId) => {
      const b = binding;
      if (!b || b.entityId !== entityId) {
        throw new Error('glossary entity unavailable — open the entity editor for it first (modal-scoped, mirrors R2)');
      }
      return createGlossaryEntityHandle(entityId);
    },
  });
}

/** Test-only: reset the module registration guard + binding. */
export function _resetGlossaryEntityDocumentProvider(): void {
  registered = false;
  binding = null;
  listeners.clear();
}
