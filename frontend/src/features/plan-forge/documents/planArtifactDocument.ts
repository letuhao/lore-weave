// PlanForge S3 (PS-9) — the read-only `plan-artifact` JSON-document provider. Lets the planner's
// artifact rows + the Pass Rail open a compiled artifact (novel_system_spec / cast_plan / package /
// …) in the json-editor as a VIEWER (FE-1's readOnly), fed by BE-3's content route.
//
// F-P11: DocContext carries {token, bookId} but NO runId, and a plan artifact is scoped to its run
// — so the resourceId is COMPOSITE, `{runId}:{artifactId}`. save/update/revert are no-ops: the only
// sanctioned artifact mutation is POST /checkpoint's deep-merge (PF-3), never this viewer.
import type { DocContext, DocumentHandle, DocumentSnapshot } from '@/features/studio/documents/types';
import { registerJsonDocumentProvider } from '@/features/studio/documents/registry';
import { planForgeApi } from '../api';

export const PLAN_ARTIFACT_DOC_TYPE = 'loreweave.plan-artifact.v1';

/** `{runId}:{artifactId}` → the two ids, or null if malformed. */
export function parsePlanArtifactResourceId(resourceId: string): { runId: string; artifactId: string } | null {
  const i = resourceId.indexOf(':');
  if (i <= 0 || i === resourceId.length - 1) return null;
  return { runId: resourceId.slice(0, i), artifactId: resourceId.slice(i + 1) };
}

function readOnlyHandle(resourceId: string, doc: unknown, reloadFn: () => Promise<unknown>): DocumentHandle {
  let snapshot: DocumentSnapshot = { doc, etag: null, dirty: false, status: 'idle', detail: null };
  const listeners = new Set<() => void>();
  const emit = () => listeners.forEach((l) => l());
  return {
    type: PLAN_ARTIFACT_DOC_TYPE,
    resourceId,
    getSnapshot: () => snapshot,
    subscribe: (l) => { listeners.add(l); return () => listeners.delete(l); },
    update: () => { /* read-only: the viewer never mutates the artifact (PF-3) */ },
    save: async () => { /* read-only: nothing to persist */ },
    revert: () => { /* read-only: no local edits to drop */ },
    reload: async () => {
      const next = await reloadFn();
      snapshot = { ...snapshot, doc: next };
      emit();
    },
    release: () => { listeners.clear(); },
  };
}

let registered = false;

/** Idempotent — registered when a plan-forge panel mounts (mirrors the other feature providers). */
export function registerPlanArtifactDocumentProvider(): void {
  if (registered) return;
  registered = true;
  registerJsonDocumentProvider({
    type: PLAN_ARTIFACT_DOC_TYPE,
    titleKey: 'panels.plan-artifact.title',
    readOnly: true,
    open: async (ctx: DocContext, resourceId: string) => {
      const parsed = parsePlanArtifactResourceId(resourceId);
      if (!parsed) throw new Error('malformed plan-artifact id (expected {runId}:{artifactId})');
      const fetchContent = async () => {
        const art = await planForgeApi.getArtifact(ctx.bookId, parsed.runId, parsed.artifactId, ctx.token);
        return art.content;
      };
      return readOnlyHandle(resourceId, await fetchContent(), fetchContent);
    },
  });
}

/** Test-only: reset the registration guard. */
export function _resetPlanArtifactDocumentProvider(): void {
  registered = false;
}
