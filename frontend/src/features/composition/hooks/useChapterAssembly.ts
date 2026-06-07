// LOOM chapter-assembly-modes (FE) — controller for the "Assemble" tab.
//
// Hooks own all logic (CLAUDE.md MVC). Chapter (B2) + stitch (B3) are non-stream
// POSTs; setAssemblyMode persists the work's default mode. Correction capture
// reuses useCorrection (useAutoGenerate) so chapter/stitch human signals flow to
// learning-service via the same composition.generation_corrected pipeline.
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { compositionApi, type ChapterAssembleParams } from '../api';
import type { AssemblyMode } from '../types';

export function useGenerateChapter(token: string | null) {
  return useMutation({
    mutationFn: (v: { projectId: string; chapterId: string } & ChapterAssembleParams) =>
      compositionApi.generateChapter(v.projectId, v.chapterId, v, token!),
  });
}

export function useStitchChapter(token: string | null) {
  return useMutation({
    mutationFn: (v: { projectId: string; chapterId: string } & ChapterAssembleParams) =>
      compositionApi.stitchChapter(v.projectId, v.chapterId, v, token!),
  });
}

// Set work.settings.assembly_mode. The server REPLACES the whole settings blob,
// so we MERGE over the current settings — otherwise critic_model_*/reasoning_engine
// /capture_correction_prose would be silently dropped. Invalidates the work query
// (keyed by bookId) so the toggle reflects the persisted value.
export function useSetAssemblyMode(bookId: string | undefined, token: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { projectId: string; currentSettings: Record<string, unknown>; mode: AssemblyMode }) =>
      compositionApi.patchWork(v.projectId, { settings: { ...v.currentSettings, assembly_mode: v.mode } }, token!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['composition', 'work', bookId] }),
  });
}
