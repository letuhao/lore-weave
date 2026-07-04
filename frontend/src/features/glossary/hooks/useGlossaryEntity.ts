import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '../api';
import type { AttributeValue, GlossaryEntity, Translation } from '../types';

/**
 * The Tier-4 domain hoist for a single entity's edit-in-flight state (docs/standards/
 * dockable-gui.md DOCK-10). Extracted from EntityEditorModal so the modal AND the
 * `loreweave.glossary-entity.v1` JSON document provider (13_glossary_panels.md A2) share
 * ONE owner instead of the JSON view re-fetching/re-deriving a second copy.
 *
 * Write-path errors (save/setStatus) are NOT caught here — they propagate to the caller,
 * which decides how to surface them (a toast for the modal, an inline error for the JSON
 * editor). `reload()` keeps its own toast — it's called from effects/fire-and-forget
 * refresh paths (mount, post-restore) with no natural call-site to catch it.
 */
export function useGlossaryEntity(bookId: string, entityId: string) {
  const { accessToken } = useAuth();
  const [entity, setEntity] = useState<GlossaryEntity | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pendingChanges, setPendingChanges] = useState<Map<string, string>>(new Map());

  const reload = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const e = await glossaryApi.getEntity(bookId, entityId, accessToken);
      setEntity(e);
      setPendingChanges(new Map());
    } catch (e) {
      toast.error((e as Error).message);
    }
    setLoading(false);
  }, [accessToken, bookId, entityId]);

  useEffect(() => { void reload(); }, [reload]);

  const setValue = (attrValueId: string, value: string) => {
    setPendingChanges((prev) => new Map(prev).set(attrValueId, value));
  };

  const getValue = (attr: AttributeValue): string =>
    pendingChanges.get(attr.attr_value_id) ?? attr.original_value ?? '';

  const isDirty = pendingChanges.size > 0;

  const discard = () => setPendingChanges(new Map());

  // Per-attribute PATCH loop — byte-preserving extraction of the modal's original save
  // path (no OCC today; `applyEntityEdit`/base_version is a separate, more atomic write
  // path the JSON provider uses — see 13_glossary_panels.md A2 — kept out of this hook's
  // save() to avoid silently changing the modal's existing concurrent-edit semantics).
  const save = async () => {
    if (!accessToken || !entity || !isDirty) return;
    setSaving(true);
    try {
      for (const [attrValueId, value] of pendingChanges) {
        await glossaryApi.patchAttributeValue(bookId, entityId, attrValueId, { original_value: value }, accessToken);
      }
      setPendingChanges(new Map());
      await reload();
    } finally {
      setSaving(false);
    }
  };

  const setStatus = async (status: string) => {
    if (!accessToken || !entity) return;
    await glossaryApi.patchEntity(bookId, entityId, { status }, accessToken);
    await reload();
  };

  // Pure local merge — the actual translation write already happened inside
  // AttrTranslationRow; this just folds the result into the shared entity snapshot.
  const applyTranslationChange = useCallback(
    (attrValueId: string, updated: Translation | null, oldTranslationId?: string) => {
      setEntity((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          translation_count: prev.translation_count + (updated && !oldTranslationId ? 1 : !updated && oldTranslationId ? -1 : 0),
          attribute_values: prev.attribute_values.map((av) => {
            if (av.attr_value_id !== attrValueId) return av;
            let translations: Translation[];
            if (updated) {
              const idx = av.translations.findIndex((tr) => tr.translation_id === updated.translation_id);
              if (idx >= 0) {
                translations = [...av.translations];
                translations[idx] = updated;
              } else {
                translations = [...av.translations, updated];
              }
            } else {
              translations = av.translations.filter((tr) => tr.translation_id !== oldTranslationId);
            }
            return { ...av, translations };
          }),
        };
      });
    },
    [],
  );

  // Pure local bump — EvidenceTab already persisted the evidence row itself.
  const bumpEvidenceCount = (delta: number) => {
    setEntity((prev) => (prev ? { ...prev, evidence_count: prev.evidence_count + delta } : prev));
  };

  return {
    entity,
    loading,
    saving,
    isDirty,
    pendingChanges,
    getValue,
    setValue,
    discard,
    save,
    setStatus,
    reload,
    applyTranslationChange,
    bumpEvidenceCount,
  };
}

export type UseGlossaryEntityResult = ReturnType<typeof useGlossaryEntity>;
