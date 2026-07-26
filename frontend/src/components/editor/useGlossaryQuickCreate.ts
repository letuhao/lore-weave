import { useCallback } from 'react';
import { knowledgeApi } from '@/features/knowledge/api';
import type { AuthorableKind } from './GlossaryAutocomplete';

// S-10 O7 (PO D-d) — the `[[`-create action, shared by EditorPanel + ChapterEditorPage so the
// create-then-insert behaviour is ONE implementation with ONE test (the two consumers only differ in
// how they insert text into their editor). Given the trigger name + the chosen (closed-set) kind, it
// creates the KG entity via knowledgeApi.createEntity (BE complete) and, on success, inserts the
// created entity's canonical name back into the prose via the consumer's `insert`.
//
// Returns undefined (an inert handler) when the project/token isn't resolved yet — the caller passes
// `undefined` to GlossaryAutocomplete in that case, so the "＋ Create" affordance stays hidden rather
// than offering a create that would fail (no dead affordance — the same discipline the 2026-07-17
// audit applied when it hid the old no-op link).
export function useGlossaryQuickCreate(
  projectId: string | null | undefined,
  token: string | null | undefined,
  insert: (name: string) => void,
): ((name: string, kind: AuthorableKind) => Promise<void>) | undefined {
  const handler = useCallback(
    async (name: string, kind: AuthorableKind) => {
      const clean = name.trim();
      if (!projectId || !token || !clean) return;
      const entity = await knowledgeApi.createEntity(
        { project_id: projectId, name: clean, kind },
        token,
      );
      insert(entity.name);
    },
    [projectId, token, insert],
  );
  return projectId && token ? handler : undefined;
}
