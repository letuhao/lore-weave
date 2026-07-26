// 13_glossary_panels.md A2 — the glossary-entity document provider: modal-scoped binding
// (no persistent Tier-4 provider exists for entities, unlike manuscript-unit), the two-phase
// save (attributes via the per-attribute loop, status via a separate patchEntity call), and
// the G7 dirty-guard on reload. Mirrors manuscriptUnitDocument.test.ts's structure/coverage.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { GlossaryEntity } from '../../types';
import type { UseGlossaryEntityResult } from '../../hooks/useGlossaryEntity';

import { _clearJsonDocuments, openJsonDocument } from '@/features/studio/documents/registry';
import {
  GLOSSARY_ENTITY_DOC_TYPE, _resetGlossaryEntityDocumentProvider, _setGlossaryEntityBinding,
  registerGlossaryEntityDocumentProvider, reloadBoundGlossaryEntity,
} from '../entityDocument';

function baseEntity(over: Partial<GlossaryEntity> = {}): GlossaryEntity {
  return {
    entity_id: 'e1', book_id: 'b1', kind_id: 'k1',
    kind: { kind_id: 'k1', code: 'character', name: 'Character', icon: '🧑', color: '#fff' },
    display_name: 'Jiang Ziya', display_name_translation: null,
    status: 'draft', tags: ['deity'],
    chapter_link_count: 0, translation_count: 0, evidence_count: 0,
    created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-04T00:00:00Z',
    chapter_links: [],
    attribute_values: [
      {
        attr_value_id: 'av1', entity_id: 'e1', attr_def_id: 'd1',
        attribute_def: { attr_def_id: 'd1', code: 'title', name: 'Title', field_type: 'text', is_required: false, is_system: false, is_active: true, sort_order: 0, genre_tags: [] },
        original_language: 'en', original_value: 'Immortal', translations: [], evidences: [],
      },
      {
        attr_value_id: 'av2', entity_id: 'e1', attr_def_id: 'd2',
        attribute_def: { attr_def_id: 'd2', code: 'domain', name: 'Domain', field_type: 'text', is_required: false, is_system: false, is_active: true, sort_order: 1, genre_tags: [] },
        original_language: 'en', original_value: 'War', translations: [], evidences: [],
      },
    ],
    ...over,
  };
}

function fakeApi(entity: GlossaryEntity | null = baseEntity()) {
  const pendingChanges = new Map<string, string>();
  const api = {
    entity,
    loading: false,
    saving: false,
    get isDirty() { return pendingChanges.size > 0; },
    pendingChanges,
    getValue: vi.fn((attr: { attr_value_id: string; original_value: string }) => pendingChanges.get(attr.attr_value_id) ?? attr.original_value),
    setValue: vi.fn((id: string, v: string) => pendingChanges.set(id, v)),
    discard: vi.fn(() => pendingChanges.clear()),
    save: vi.fn(async () => { pendingChanges.clear(); }),
    setStatus: vi.fn(async (s: string) => { if (api.entity) api.entity = { ...api.entity, status: s as GlossaryEntity['status'] }; }),
    reload: vi.fn(async () => { pendingChanges.clear(); }),
    applyTranslationChange: vi.fn(),
    bumpEvidenceCount: vi.fn(),
  };
  return api as unknown as UseGlossaryEntityResult & { entity: GlossaryEntity | null };
}

const ctx = { token: 'tok', bookId: 'b1' };

async function openDoc(api: UseGlossaryEntityResult) {
  _setGlossaryEntityBinding({ api, entityId: 'e1' });
  registerGlossaryEntityDocumentProvider();
  return openJsonDocument(GLOSSARY_ENTITY_DOC_TYPE, 'e1', ctx);
}

beforeEach(() => {
  _clearJsonDocuments();
  _resetGlossaryEntityDocumentProvider();
});

describe('glossary-entity document provider (13_glossary_panels.md A2)', () => {
  it('builds the envelope from the bound hook (attributes + status; etag = updated_at)', async () => {
    const h = await openDoc(fakeApi());
    const snap = h.getSnapshot();
    expect(snap.status).toBe('idle');
    expect(snap.etag).toBe('2026-07-04T00:00:00Z');
    expect(snap.doc).toMatchObject({
      type: GLOSSARY_ENTITY_DOC_TYPE,
      entity_id: 'e1',
      status: 'draft',
      tags: ['deity'],
      attributes: [
        { attr_value_id: 'av1', code: 'title', value: 'Immortal' },
        { attr_value_id: 'av2', code: 'domain', value: 'War' },
      ],
    });
  });

  it('open() throws when no modal is bound for this entity (R2-style modal-scoping)', async () => {
    _setGlossaryEntityBinding(null);
    registerGlossaryEntityDocumentProvider();
    await expect(openJsonDocument(GLOSSARY_ENTITY_DOC_TYPE, 'e1', ctx)).rejects.toThrow(/open the entity editor/);
  });

  it('update: an attribute value change flows into the hoist via setValue', async () => {
    const api = fakeApi();
    const h = await openDoc(api);
    h.update({ entity_id: 'e1', status: 'draft', tags: ['deity'], attributes: [{ attr_value_id: 'av1', code: 'title', name: 'Title', value: 'Deity' }] });
    expect(api.setValue).toHaveBeenCalledWith('av1', 'Deity');
    expect(h.getSnapshot().dirty).toBe(true);
  });

  it('update: an unknown attr_value_id is ignored (no crash, no phantom edit)', async () => {
    const api = fakeApi();
    const h = await openDoc(api);
    h.update({ attributes: [{ attr_value_id: 'ghost', value: 'nope' }] });
    expect(api.setValue).not.toHaveBeenCalled();
    expect(h.getSnapshot().dirty).toBe(false);
  });

  it('update: a status change stages as pending (not yet persisted)', async () => {
    const api = fakeApi();
    const h = await openDoc(api);
    h.update({ status: 'active', attributes: [] });
    expect(api.setStatus).not.toHaveBeenCalled();
    const snap = h.getSnapshot();
    expect(snap.dirty).toBe(true);
    expect((snap.doc as { status: string }).status).toBe('active');
  });

  // /review-impl MED: pendingStatus was only ever SET, never cleared, when a later update()
  // brought the JSON status back to the original value — dirty stayed true and a stray save()
  // would have persisted the STALE intermediate status the user's own buffer no longer showed.
  it('update: reverting the status back to the original via the SAME buffer clears pendingStatus (no stale save)', async () => {
    const api = fakeApi(); // entity.status === 'draft'
    const h = await openDoc(api);
    h.update({ status: 'active', attributes: [] }); // stage a change
    h.update({ status: 'draft', attributes: [] }); // revert it back to the original
    const snap = h.getSnapshot();
    expect(snap.dirty).toBe(false);
    expect((snap.doc as { status: string }).status).toBe('draft');
    await h.save();
    expect(api.setStatus).not.toHaveBeenCalled(); // must NOT persist the reverted-away 'active'
  });

  it('save: phase-1 attributes via api.save, phase-2 status via api.setStatus', async () => {
    const api = fakeApi();
    const h = await openDoc(api);
    h.update({ status: 'active', attributes: [{ attr_value_id: 'av1', code: 'title', name: 'Title', value: 'Deity' }] });
    await h.save();
    expect(api.save).toHaveBeenCalledTimes(1);
    expect(api.setStatus).toHaveBeenCalledWith('active');
    expect(h.getSnapshot().dirty).toBe(false);
  });

  it('save conflict on attributes surfaces status=error with the "attributes:" part, edits preserved', async () => {
    const api = fakeApi();
    api.save = vi.fn().mockRejectedValue(new Error('412 stale'));
    const h = await openDoc(api);
    h.update({ attributes: [{ attr_value_id: 'av1', code: 'title', name: 'Title', value: 'Deity' }] });
    await h.save();
    const snap = h.getSnapshot();
    expect(snap.status).toBe('error');
    expect(snap.detail).toContain('attributes:');
    expect(snap.dirty).toBe(true); // edits preserved for the user to reconcile
    expect(api.setStatus).not.toHaveBeenCalled(); // phase 2 never runs after a phase-1 failure
  });

  it('save conflict on status surfaces status=error with the "status:" part', async () => {
    const api = fakeApi();
    api.setStatus = vi.fn().mockRejectedValue(new Error('conflict'));
    const h = await openDoc(api);
    h.update({ status: 'active', attributes: [] });
    await h.save();
    const snap = h.getSnapshot();
    expect(snap.status).toBe('error');
    expect(snap.detail).toContain('status:');
  });

  it('revert clears the pending status and discards dirty attribute edits', async () => {
    const api = fakeApi();
    const h = await openDoc(api);
    h.update({ status: 'active', attributes: [{ attr_value_id: 'av1', code: 'title', name: 'Title', value: 'Deity' }] });
    h.revert();
    expect(api.discard).toHaveBeenCalled();
    const snap = h.getSnapshot();
    expect(snap.dirty).toBe(false);
    expect((snap.doc as { status: string }).status).toBe('draft');
  });

  it('reload (Lane B, G7): calls api.reload only when nothing local would be lost', async () => {
    const api = fakeApi();
    const h = await openDoc(api);
    await h.reload();
    expect(api.reload).toHaveBeenCalledTimes(1);

    h.update({ attributes: [{ attr_value_id: 'av1', code: 'title', name: 'Title', value: 'Deity' }] });
    await h.reload();
    expect(api.reload).toHaveBeenCalledTimes(1); // untouched while dirty

    h.revert();
    await h.reload();
    expect(api.reload).toHaveBeenCalledTimes(2);
  });

  it('the modal closing (binding cleared) surfaces an error snapshot instead of stale data', async () => {
    const api = fakeApi();
    const h = await openDoc(api);
    _setGlossaryEntityBinding(null);
    expect(h.getSnapshot()).toMatchObject({ status: 'error', detail: expect.stringContaining('modal-scoped') });
  });
});

describe('reloadBoundGlossaryEntity (13_glossary_panels.md A5 — Lane B live refresh)', () => {
  it('reloads when the modal is open for exactly this entity and clean', () => {
    const api = fakeApi();
    _setGlossaryEntityBinding({ api, entityId: 'e1' });
    reloadBoundGlossaryEntity('e1');
    expect(api.reload).toHaveBeenCalled();
  });

  it('is a no-op when no modal is open at all', () => {
    _setGlossaryEntityBinding(null);
    expect(() => reloadBoundGlossaryEntity('e1')).not.toThrow();
  });

  it('is a no-op when the open modal is for a DIFFERENT entity (never hijacks the editor)', () => {
    const api = fakeApi();
    _setGlossaryEntityBinding({ api, entityId: 'other-entity' });
    reloadBoundGlossaryEntity('e1');
    expect(api.reload).not.toHaveBeenCalled();
  });

  it('G7: is a no-op when the bound entity has unsaved edits (never clobbers a dirty hoist)', () => {
    const api = fakeApi();
    api.pendingChanges.set('av1', 'user is typing');
    _setGlossaryEntityBinding({ api, entityId: 'e1' });
    reloadBoundGlossaryEntity('e1');
    expect(api.reload).not.toHaveBeenCalled();
  });
});
