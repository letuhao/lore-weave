// LOOM Composition (M8) — gateway calls. Relative /v1 rides the Vite proxy →
// gateway (dev :3123) / nginx (prod). The generate SSE stream is NOT here — it
// uses a raw fetch+ReadableStream in useCompositionStream (apiJson can't stream).
import { apiBase, apiJson } from '../../api';
import type {
  AutoGeneration, CanonRule, ChapterGeneration, CommitDecomposePayload, CorrectionBody, CorrectionStats,
  DecomposePreview, GenerationJob, Grounding, NarrativeThread, OutlineNode, PublishGate, StructureTemplate, Work, WorkResolution,
} from './types';

// A3 decompose preview request (cycle 13).
export type DecomposeBody = {
  structure_template_id: string;
  premise: string;
  model_source: 'user_model' | 'platform_model';
  model_ref: string;
};

// Params for a chapter-level assembly (B2 chapter single-pass / B3 stitch).
export type ChapterAssembleParams = {
  modelRef: string;
  modelSource?: 'user_model' | 'platform_model';
  reasoning?: 'off' | 'auto' | 'low' | 'medium' | 'high';
  modelKind?: string;
  modelName?: string;
  persist?: boolean; // FE default false — show + human Accept, don't clobber the draft
};

// Params for an auto (diverge→converge) generation — mirrors the SSE generate
// body minus the streaming bits; `mode: 'auto'` is added by the api method.
export type AutoGenerateParams = {
  outlineNodeId: string;
  modelRef: string;
  modelSource?: 'user_model' | 'platform_model';
  operation?: string;
  guide?: string;
  reasoning?: 'off' | 'auto' | 'low' | 'medium' | 'high';
  modelKind?: string;
  modelName?: string;
};

const BASE = '/v1/composition';

export const compositionApi = {
  resolveWork(bookId: string, token: string): Promise<WorkResolution> {
    return apiJson<WorkResolution>(`${BASE}/books/${bookId}/work`, { token });
  },
  createWork(bookId: string, token: string): Promise<Work> {
    return apiJson<Work>(`${BASE}/books/${bookId}/work`, { method: 'POST', token });
  },
  getOutline(projectId: string, token: string, includeArchived = false): Promise<{ nodes: OutlineNode[]; scene_links: unknown[] }> {
    const qs = includeArchived ? '?include_archived=true' : '';
    return apiJson(`${BASE}/works/${projectId}/outline${qs}`, { token });
  },
  createNode(projectId: string, payload: Partial<OutlineNode> & { kind: string }, token: string): Promise<OutlineNode> {
    return apiJson(`${BASE}/works/${projectId}/outline/nodes`, { method: 'POST', body: JSON.stringify(payload), token });
  },
  // Patch an outline node (M9: set a scene's status — 'done' commits it for the
  // chapter-gate + emits composition.scene_committed server-side). T1.1b: pass
  // `version` to send If-Match → the BE 412s with NODE_VERSION_CONFLICT (carrying
  // .body.detail.current) on a stale edit. Omitting `version` keeps the legacy
  // self-acquiring behaviour (M9 useSetSceneStatus) — backward-compatible.
  patchNode(nodeId: string, patch: Partial<OutlineNode>, token: string, version?: number): Promise<OutlineNode> {
    return apiJson(`${BASE}/outline/nodes/${nodeId}`, {
      method: 'PATCH', body: JSON.stringify(patch), token,
      ...(version !== undefined ? { headers: { 'If-Match': String(version) } } : {}),
    });
  },
  // T1.1b — soft-archive an outline node (DELETE = archive, returns the archived
  // node; unconditional, no If-Match). Children are archived by the BE closure.
  archiveNode(nodeId: string, token: string): Promise<OutlineNode> {
    return apiJson(`${BASE}/outline/nodes/${nodeId}`, { method: 'DELETE', token });
  },
  // T1.1b — un-archive a node (inverse of DELETE). The BE restores the archived
  // subtree + archived ancestor chain so it reconnects to a visible root.
  restoreNode(nodeId: string, token: string): Promise<OutlineNode> {
    return apiJson(`${BASE}/outline/nodes/${nodeId}/restore`, { method: 'POST', token });
  },
  // T1.1c — drag-reorder + reparent. Places the node under `new_parent_id` after
  // `after_id` (null = first child). The BE computes the fractional rank +
  // renumbers scene story_order. Optional `version` → If-Match (412 on stale);
  // 400 BAD_REFERENCE on a reparent cycle / bad parent.
  reorderNode(
    nodeId: string,
    move: { new_parent_id: string | null; after_id: string | null },
    token: string,
    version?: number,
  ): Promise<OutlineNode> {
    return apiJson(`${BASE}/outline/nodes/${nodeId}/reorder`, {
      method: 'POST', body: JSON.stringify(move), token,
      ...(version !== undefined ? { headers: { 'If-Match': String(version) } } : {}),
    });
  },
  // A3 decompose planner (cycle 13). listTemplates → built-in + user structure
  // templates; decomposePreview → the proposed (NOT persisted) arc→chapter→scene
  // tree; commitDecompose → persist the edited tree (409 CHAPTER_ALREADY_PLANNED
  // carries .body.detail.chapter_ids → the hook resends with replace=true).
  listTemplates(token: string): Promise<StructureTemplate[]> {
    return apiJson<{ templates: StructureTemplate[] }>(`${BASE}/templates`, { token })
      .then((r) => r.templates);
  },
  decomposePreview(projectId: string, body: DecomposeBody, token: string): Promise<DecomposePreview> {
    return apiJson(`${BASE}/works/${projectId}/outline/decompose`, { method: 'POST', body: JSON.stringify(body), token });
  },
  commitDecompose(projectId: string, payload: CommitDecomposePayload, token: string): Promise<unknown> {
    return apiJson(`${BASE}/works/${projectId}/outline/decompose/commit`, { method: 'POST', body: JSON.stringify(payload), token });
  },
  // M9 chapter-gate — is the chapter publishable (all scenes done)?
  publishGate(projectId: string, chapterId: string, token: string): Promise<PublishGate> {
    return apiJson(`${BASE}/works/${projectId}/chapters/${chapterId}/publish-gate`, { token });
  },
  getGrounding(projectId: string, nodeId: string, guide: string, token: string): Promise<Grounding> {
    const qs = guide ? `?guide=${encodeURIComponent(guide)}` : '';
    return apiJson(`${BASE}/works/${projectId}/scenes/${nodeId}/grounding${qs}`, { token });
  },
  // The full URL for the SSE generate POST (used by useCompositionStream's fetch).
  generateUrl(projectId: string): string {
    return `${apiBase()}${BASE}/works/${projectId}/generate`;
  },
  // V1 slice 3 — auto (diverge→converge): NON-streaming POST that returns the
  // winner + all K candidate texts (the human-gate cards).
  generateAuto(projectId: string, params: AutoGenerateParams, token: string): Promise<AutoGeneration> {
    return apiJson(`${BASE}/works/${projectId}/generate`, {
      method: 'POST', token,
      body: JSON.stringify({
        mode: 'auto',
        outline_node_id: params.outlineNodeId,
        model_source: params.modelSource ?? 'user_model',
        model_ref: params.modelRef,
        operation: params.operation ?? 'draft_scene',
        guide: params.guide ?? '',
        reasoning: params.reasoning ?? 'auto',
        model_kind: params.modelKind,
        model_name: params.modelName,
      }),
    });
  },
  // Patch the Work (LOOM chapter-assembly: set settings.assembly_mode). NOTE the
  // server REPLACES the whole settings blob — the caller MUST merge the existing
  // settings (see useChapterAssembly.setAssemblyMode) so it never drops
  // critic_model_*/reasoning_engine/etc.
  patchWork(projectId: string, patch: { settings?: Record<string, unknown>; status?: string }, token: string): Promise<Work> {
    return apiJson(`${BASE}/works/${projectId}`, { method: 'PATCH', body: JSON.stringify(patch), token });
  },
  // B2 chapter single-pass — generate a whole chapter from its decompose plan.
  generateChapter(projectId: string, chapterId: string, params: ChapterAssembleParams, token: string): Promise<ChapterGeneration> {
    return apiJson(`${BASE}/works/${projectId}/chapters/${chapterId}/generate`, {
      method: 'POST', token,
      body: JSON.stringify({
        model_source: params.modelSource ?? 'user_model', model_ref: params.modelRef,
        reasoning: params.reasoning ?? 'auto', model_kind: params.modelKind, model_name: params.modelName,
        persist: params.persist ?? false,
      }),
    });
  },
  // B3 stitch — merge a chapter's done scene drafts into one seamless chapter.
  stitchChapter(projectId: string, chapterId: string, params: ChapterAssembleParams, token: string): Promise<ChapterGeneration> {
    return apiJson(`${BASE}/works/${projectId}/chapters/${chapterId}/stitch`, {
      method: 'POST', token,
      body: JSON.stringify({
        model_source: params.modelSource ?? 'user_model', model_ref: params.modelRef,
        reasoning: params.reasoning ?? 'auto', model_kind: params.modelKind, model_name: params.modelName,
        persist: params.persist ?? false,
      }),
    });
  },
  // V1 slice 3 — capture a human-gate correction (edit/pick_different/regenerate/
  // reject). 'accept' is intentionally NOT a kind (H2 self-reinforcement guard).
  submitCorrection(jobId: string, body: CorrectionBody, token: string): Promise<{ id: string }> {
    return apiJson(`${BASE}/jobs/${jobId}/correction`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },
  // V1 slice 5 — the eval-gate dashboard: per-mode correction rates for this Work.
  getCorrectionStats(projectId: string, token: string): Promise<CorrectionStats> {
    return apiJson(`${BASE}/works/${projectId}/correction-stats`, { token });
  },
  critique(jobId: string, passage: string, token: string): Promise<{ critic: GenerationJob['critic']; warning?: string }> {
    return apiJson(`${BASE}/jobs/${jobId}/critique`, {
      method: 'POST', body: JSON.stringify({ passage }), token,
    });
  },
  dismissViolation(jobId: string, ruleId: string, token: string): Promise<{ critic: GenerationJob['critic'] }> {
    return apiJson(`${BASE}/jobs/${jobId}/dismiss-violation`, {
      method: 'POST', body: JSON.stringify({ rule_id: ruleId }), token,
    });
  },
  listCanonRules(projectId: string, token: string): Promise<{ rules: CanonRule[] }> {
    return apiJson(`${BASE}/works/${projectId}/canon-rules`, { token });
  },
  createCanonRule(projectId: string, payload: Partial<CanonRule>, token: string): Promise<CanonRule> {
    return apiJson(`${BASE}/works/${projectId}/canon-rules`, { method: 'POST', body: JSON.stringify(payload), token });
  },
  patchCanonRule(ruleId: string, payload: Partial<CanonRule>, version: number, token: string): Promise<CanonRule> {
    return apiJson(`${BASE}/canon-rules/${ruleId}`, {
      method: 'PATCH', body: JSON.stringify(payload), token, headers: { 'If-Match': String(version) },
    });
  },
  deleteCanonRule(ruleId: string, token: string): Promise<CanonRule> {
    return apiJson(`${BASE}/canon-rules/${ruleId}`, { method: 'DELETE', token });
  },
  // T0.1 — read the narrative-thread ledger (FD-1 S4a). `open` = the unpaid-promise
  // debt (priority-ordered); `all` = the full ledger. `open_count` is the true debt
  // count (not capped by the list LIMIT). Read-only.
  listNarrativeThreads(
    projectId: string,
    status: 'open' | 'all',
    token: string,
  ): Promise<{ threads: NarrativeThread[]; open_count: number }> {
    return apiJson(`${BASE}/works/${projectId}/narrative-threads?status=${status}`, { token });
  },
};
