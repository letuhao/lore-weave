// A3 decompose planner (cycle 13) — controller hook (CLAUDE.md MVC: logic here,
// PlannerView renders). Owns the config inputs, the preview→editable-draft
// conversion, per-scene/chapter edits, and the commit + 409→replace flow.
import { useCallback, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { compositionApi, type DecomposeBody } from '../api';
import type { DecomposePreview, PlannerChapterDraft, PlannerSceneDraft } from '../types';

export function useStructureTemplates(token: string | null) {
  return useQuery({
    queryKey: ['composition', 'templates'],
    queryFn: () => compositionApi.listTemplates(token!),
    enabled: !!token,
  });
}

// A stable idempotency key per preview→commit attempt (regenerated on a fresh
// preview), so a double-submit/retry replays the original commit (BE exactly-once).
function newKey(): string {
  return `plan-${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}

function toDraft(preview: DecomposePreview): PlannerChapterDraft[] {
  return preview.chapters.map((c) => ({
    chapter_id: c.chapter.chapter_id,
    title: c.chapter.title,
    intent: c.chapter.intent,
    beat_role: c.chapter.beat_role,
    scenes: c.scenes.map((s) => ({
      title: s.title,
      synopsis: s.synopsis,
      tension: s.tension,
      present_entity_ids: [...s.present_entity_ids],
    })),
  }));
}

export type PlannerError = { status?: number; code?: string; chapterIds?: string[]; message: string };

function asPlannerError(e: unknown): PlannerError {
  const err = e as { status?: number; body?: { detail?: { code?: string; chapter_ids?: string[] } }; message?: string };
  return {
    status: err.status,
    code: err.body?.detail?.code,
    chapterIds: err.body?.detail?.chapter_ids,
    message: err.message || 'request failed',
  };
}

export function usePlanner(projectId: string, token: string | null) {
  const qc = useQueryClient();
  const templates = useStructureTemplates(token);

  const [templateId, setTemplateId] = useState('');
  const [premise, setPremise] = useState('');
  const [arcTitle, setArcTitle] = useState('Arc');
  const [draft, setDraft] = useState<PlannerChapterDraft[] | null>(null);
  const [preview, setPreview] = useState<DecomposePreview | null>(null); // raw, for read-only hints
  const [idemKey, setIdemKey] = useState('');
  const [error, setError] = useState<PlannerError | null>(null);
  const [needsReplace, setNeedsReplace] = useState<string[] | null>(null); // chapter_ids on 409

  const previewMut = useMutation({
    mutationFn: (body: DecomposeBody) => compositionApi.decomposePreview(projectId, body, token!),
  });
  const commitMut = useMutation({
    mutationFn: (replace: boolean) =>
      compositionApi.commitDecompose(
        projectId,
        { arc_title: arcTitle, chapters: draft ?? [], replace, idempotency_key: idemKey },
        token!,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['composition', 'outline', projectId] }),
  });

  const runPreview = useCallback(
    (model: { modelRef: string; modelSource?: 'user_model' | 'platform_model' }) => {
      if (!templateId || !premise.trim() || !model.modelRef) return;
      setError(null);
      setNeedsReplace(null);
      previewMut.mutate(
        { structure_template_id: templateId, premise: premise.trim(), model_source: model.modelSource ?? 'user_model', model_ref: model.modelRef },
        {
          onSuccess: (p) => {
            setArcTitle(p.arc_title || 'Arc');
            setPreview(p);
            setDraft(toDraft(p));
            setIdemKey(newKey());
          },
          onError: (e) => setError(asPlannerError(e)),
        },
      );
    },
    [templateId, premise, previewMut],
  );

  const editScene = useCallback((ci: number, si: number, patch: Partial<PlannerSceneDraft>) => {
    setDraft((d) => d && d.map((c, i) => (i !== ci ? c : { ...c, scenes: c.scenes.map((s, j) => (j !== si ? s : { ...s, ...patch })) })));
  }, []);
  const editChapter = useCallback((ci: number, patch: Partial<Pick<PlannerChapterDraft, 'intent' | 'beat_role' | 'title'>>) => {
    setDraft((d) => d && d.map((c, i) => (i !== ci ? c : { ...c, ...patch })));
  }, []);
  const addScene = useCallback((ci: number) => {
    setDraft((d) => d && d.map((c, i) => (i !== ci ? c : { ...c, scenes: [...c.scenes, { title: '', synopsis: '', tension: 50, present_entity_ids: [] }] })));
  }, []);
  const removeScene = useCallback((ci: number, si: number) => {
    setDraft((d) => d && d.map((c, i) => (i !== ci ? c : { ...c, scenes: c.scenes.filter((_, j) => j !== si) })));
  }, []);

  const doCommit = useCallback(
    (replace: boolean) => {
      if (!draft) return;
      setError(null);
      commitMut.mutate(replace, {
        onSuccess: () => { setNeedsReplace(null); setDraft(null); setPreview(null); },
        onError: (e) => {
          const pe = asPlannerError(e);
          if (pe.status === 409 && pe.code === 'CHAPTER_ALREADY_PLANNED') setNeedsReplace(pe.chapterIds ?? []);
          else setError(pe);
        },
      });
    },
    [draft, commitMut],
  );

  const totalScenes = useMemo(() => (draft ?? []).reduce((n, c) => n + c.scenes.length, 0), [draft]);

  return {
    templates,
    templateId, setTemplateId,
    premise, setPremise,
    arcTitle,
    draft, preview, totalScenes,
    previewing: previewMut.isPending,
    committing: commitMut.isPending,
    error,
    needsReplace,
    cancelReplace: () => setNeedsReplace(null),
    runPreview,
    editScene, editChapter, addScene, removeScene,
    commit: () => doCommit(false),
    confirmReplace: () => doCommit(true),
  };
}
