// LOOM Composition (M8) — gateway calls. Relative /v1 rides the Vite proxy →
// gateway (dev :3123) / nginx (prod). The generate SSE stream is NOT here — it
// uses a raw fetch+ReadableStream in useCompositionStream (apiJson can't stream).
import { apiBase, apiJson } from '../../api';
import type {
  AutoGeneration, CanonRule, ChapterGeneration, CommitDecomposePayload, CorrectionBody, CorrectionStats,
  DecomposePreview, DeriveBody, DerivativeContextResponse, GenerationJob, Grounding, GroundingItemType, NarrativeThread, OutlineNode, PinAction, ProgressStats, PublishGate, ReferenceList, ReferenceSearch, ReferenceSource, SceneLink, SceneLinkKind, StructureTemplate, StyleProfile, StyleScope, VoiceProfile, Work, WorkResolution,
} from './types';
import type { MotifBindingsResponse } from './motif/types';

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

// LLM re-arch Phase 3 M4 — when COMPOSITION_WORKER_ENABLED is on, the auto /
// chapter / stitch endpoints answer 202 `{ job_id, status: 'pending' }` (the
// worker runs the compute) instead of the inline result. The submit+poll is
// hidden inside the api methods so the hooks/components keep their "await the
// result" contract: flag-off (inline 200) returns directly; flag-on polls
// GET /jobs/{id} to terminal and maps job.result to the same shape.
const JOB_POLL_INTERVAL_MS = 2000;
// ~10min budget — MUST exceed worst-case worker wall-clock (multi-LLM
// diverge→converge→canon-reflect; chapter single-pass). Under the backend's
// chapter_inflight_stale_secs (900s) sweeper window so a slow job is still
// polled, not abandoned (the M2 #1 orphaned-result lesson).
const JOB_POLL_MAX = 300;
const _sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function _pollJob(jobId: string, token: string, signal?: AbortSignal): Promise<GenerationJob> {
  let job = await compositionApi.getJob(jobId, token);
  for (
    let i = 0;
    i < JOB_POLL_MAX && (job.status === 'pending' || job.status === 'running');
    i++
  ) {
    if (signal?.aborted) return job; // a newer start / unmount stops the loop
    await _sleep(JOB_POLL_INTERVAL_MS);
    if (signal?.aborted) return job;
    job = await compositionApi.getJob(jobId, token);
  }
  return job;
}

// If the POST answered with a still-active job (worker 202 / a replay of a
// running job), poll to terminal and map job.result via `map`; else (inline 200,
// already completed) return the response verbatim. A failed job throws with its
// stored error; a job still active after the budget throws (never a false-green).
async function _resolveJob<T extends { job_id: string; status: string }>(
  resp: T, token: string, map: (job: GenerationJob) => T,
): Promise<T> {
  const r = resp as unknown as { job_id?: string; status?: string };
  if (r.job_id && (r.status === 'pending' || r.status === 'running')) {
    const job = await _pollJob(r.job_id, token);
    if (job.status === 'failed') {
      throw new Error((job.result as { error?: string } | null)?.error || 'generation failed');
    }
    if (job.status !== 'completed') {
      throw new Error('generation did not complete in time');
    }
    return map(job);
  }
  return resp;
}

export const compositionApi = {
  resolveWork(bookId: string, token: string): Promise<WorkResolution> {
    return apiJson<WorkResolution>(`${BASE}/books/${bookId}/work`, { token });
  },
  createWork(bookId: string, token: string): Promise<Work> {
    return apiJson<Work>(`${BASE}/books/${bookId}/work`, { method: 'POST', token });
  },
  // D-C16: address a Work by its surrogate id — the ONLY handle a pending
  // null-project Work has (the resolveWork query excludes pending works, so a
  // freshly-created greenfield Work created during a knowledge outage is
  // otherwise unreachable until backfill).
  getWorkById(workId: string, token: string): Promise<Work> {
    return apiJson<Work>(`${BASE}/works/by-id/${workId}`, { token });
  },
  // D-C16: self-healing backfill — retry binding the knowledge project onto a
  // pending Work. 200 → the (now project-backed) Work; throws on 409
  // STILL_PENDING (knowledge still down) so the caller keeps polling.
  resolveWorkProject(workId: string, token: string): Promise<Work> {
    return apiJson<Work>(`${BASE}/works/by-id/${workId}/resolve-project`, {
      method: 'POST', token,
    });
  },
  // C24 (dị bản M0) — spawn a DERIVATIVE Work that diverges from a SOURCE Work at
  // a chapter-level `branch_point` (G3). The BE (C23) mints the derivative its OWN
  // fresh knowledge project_id (G2 — its own Neo4j delta partition), persists the
  // divergence_spec + entity_override[], and returns the new (derivative) Work —
  // which carries `source_work_id` + `branch_point` so the studio banner (DPS2)
  // can render the dị bản context. NO chapter clone (COW; reference spine stays
  // read-only). The path keys on the SOURCE Work's project_id (C23 route).
  deriveWork(sourceProjectId: string, body: DeriveBody, token: string): Promise<Work> {
    return apiJson<Work>(`${BASE}/works/${sourceProjectId}/derive`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },
  // WS-B2 — the DURABLE derivative-context read-back. Surfaces the persisted
  // divergence_spec + entity_override[] (the SAME substrate the packer applies)
  // for a derivative Work, so the studio banner/chips/popover + was→now grounding
  // deltas survive a reload (no longer derive-time-cache-only). is_derivative=false
  // for a greenfield Work (everything else empty).
  getDerivativeContext(projectId: string, token: string): Promise<DerivativeContextResponse> {
    return apiJson<DerivativeContextResponse>(`${BASE}/works/${projectId}/derivative-context`, { token });
  },
  getOutline(projectId: string, token: string, includeArchived = false): Promise<{ nodes: OutlineNode[]; scene_links: SceneLink[] }> {
    const qs = includeArchived ? '?include_archived=true' : '';
    return apiJson(`${BASE}/works/${projectId}/outline${qs}`, { token });
  },
  // D-MOTIF-FE-PLANNERVIEW-WIRING (Shape A) — the POST-commit per-scene motif binding
  // for a committed chapter: { node_id: BoundMotif | null } (null = free-form). The
  // planner renders MotifBindingCard per committed scene from this map.
  getMotifBindings(projectId: string, chapterId: string, token: string): Promise<MotifBindingsResponse> {
    return apiJson(`${BASE}/works/${projectId}/outline/motif-bindings?chapter_id=${encodeURIComponent(chapterId)}`, { token });
  },
  // T1.3 Scene Graph — create a typed scene edge. 201 → the new link; 409
  // SCENE_LINK_EXISTS on a duplicate (from,to,kind); 400 BAD_REFERENCE if either
  // endpoint isn't the caller's node in this project.
  createSceneLink(
    projectId: string,
    body: { from_node_id: string; to_node_id: string; kind: SceneLinkKind; label: string },
    token: string,
  ): Promise<SceneLink> {
    return apiJson(`${BASE}/works/${projectId}/scene-links`, { method: 'POST', body: JSON.stringify(body), token });
  },
  // T1.3 — hard-delete a scene edge (edges have no archive; 204 / 404).
  deleteSceneLink(linkId: string, token: string): Promise<void> {
    return apiJson(`${BASE}/scene-links/${linkId}`, { method: 'DELETE', token });
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
  async decomposePreview(projectId: string, body: DecomposeBody, token: string): Promise<DecomposePreview> {
    const resp = await apiJson<DecomposePreview & { job_id?: string; status?: string }>(
      `${BASE}/works/${projectId}/outline/decompose`, { method: 'POST', body: JSON.stringify(body), token });
    // M4: flag-on → 202 pending; the worker stores the decompose tree in
    // job.result. The whole result IS the DecomposePreview (no merge with the job
    // envelope, unlike auto/chapter). flag-off → the inline tree verbatim.
    const r = resp as { job_id?: string; status?: string };
    if (r.job_id && (r.status === 'pending' || r.status === 'running')) {
      const job = await _pollJob(r.job_id, token);
      if (job.status === 'failed') {
        throw new Error((job.result as { error?: string } | null)?.error || 'decompose failed');
      }
      if (job.status !== 'completed') throw new Error('decompose did not complete in time');
      return job.result as unknown as DecomposePreview;
    }
    return resp;
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
  // T4.2 — server-SSOT writing progress. `today` is the client's LOCAL date
  // (YYYY-MM-DD) so streaks honor the writer's midnight, not UTC.
  getProgress(projectId: string, today: string, token: string): Promise<ProgressStats> {
    return apiJson(`${BASE}/works/${projectId}/progress?today=${encodeURIComponent(today)}`, { token });
  },
  // T4.2 — report the active chapter's current total word count (a snapshot keyed
  // to the local date). Idempotent per (chapter, date). Fired best-effort on save.
  reportProgress(
    projectId: string, body: { chapter_id: string; words: number; date: string }, token: string,
  ): Promise<{ ok: boolean; date: string; words: number }> {
    return apiJson(`${BASE}/works/${projectId}/progress/report`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },
  // T4.2 — capture a chapter's PRE-EXISTING word count the first time it's opened
  // (insert-once server-side) so its first daily snapshot counts only NEW words.
  baselineProgress(
    projectId: string, body: { chapter_id: string; words: number }, token: string,
  ): Promise<{ ok: boolean }> {
    return apiJson(`${BASE}/works/${projectId}/progress/baseline`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },
  // T3.5 — style profiles (per-scope density/pace) + voice profiles (per-character tags).
  getStyleProfiles(projectId: string, token: string): Promise<{ items: StyleProfile[] }> {
    return apiJson(`${BASE}/works/${projectId}/style-profiles`, { token });
  },
  putStyleProfile(projectId: string, body: StyleProfile, token: string): Promise<StyleProfile> {
    return apiJson(`${BASE}/works/${projectId}/style-profile`, {
      method: 'PUT', body: JSON.stringify(body), token,
    });
  },
  deleteStyleProfile(
    projectId: string, scopeType: StyleScope, scopeId: string, token: string,
  ): Promise<{ removed: boolean }> {
    const qs = `?scope_type=${scopeType}&scope_id=${encodeURIComponent(scopeId)}`;
    return apiJson(`${BASE}/works/${projectId}/style-profile${qs}`, { method: 'DELETE', token });
  },
  getVoiceProfiles(projectId: string, token: string): Promise<{ items: VoiceProfile[] }> {
    return apiJson(`${BASE}/works/${projectId}/voice-profiles`, { token });
  },
  putVoiceProfile(projectId: string, body: VoiceProfile, token: string): Promise<VoiceProfile> {
    return apiJson(`${BASE}/works/${projectId}/voice-profiles`, {
      method: 'PUT', body: JSON.stringify(body), token,
    });
  },
  deleteVoiceProfile(
    projectId: string, entityId: string, token: string,
  ): Promise<{ removed: boolean }> {
    return apiJson(`${BASE}/works/${projectId}/voice-profiles/${entityId}`, { method: 'DELETE', token });
  },
  // T3.4 — pin / exclude / clear ('none') one addressable grounding item for a scene.
  setGroundingPin(
    projectId: string, nodeId: string,
    body: { item_type: GroundingItemType; item_id: string; action: PinAction },
    token: string,
  ): Promise<{ item_type: string; item_id: string; action: string }> {
    return apiJson(`${BASE}/works/${projectId}/scenes/${nodeId}/grounding-pins`, {
      method: 'PUT', body: JSON.stringify(body), token,
    });
  },
  // T3.6 — the author's reference shelf (per-Work, embedded via provider-registry).
  listReferences(projectId: string, token: string): Promise<ReferenceList> {
    return apiJson(`${BASE}/works/${projectId}/references`, { token });
  },
  // `modelRef`/`modelSource` set the Work's embedding model on the FIRST add
  // (write-through); ignored once the Work already has one.
  addReference(
    projectId: string,
    body: { content: string; title?: string; author?: string; source_url?: string;
            model_ref?: string; model_source?: string },
    token: string,
  ): Promise<ReferenceSource> {
    return apiJson(`${BASE}/works/${projectId}/references`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },
  deleteReference(referenceId: string, token: string): Promise<{ id: string; deleted: boolean }> {
    return apiJson(`${BASE}/references/${referenceId}`, { method: 'DELETE', token });
  },
  // Per-scene semantic retrieval. `q` overrides the auto query (scene synopsis/beat).
  searchReferences(
    projectId: string, nodeId: string, token: string, q?: string,
  ): Promise<ReferenceSearch> {
    const qs = q ? `?q=${encodeURIComponent(q)}` : '';
    return apiJson(`${BASE}/works/${projectId}/scenes/${nodeId}/references${qs}`, { token });
  },
  // The full URL for the SSE generate POST (used by useCompositionStream's fetch).
  generateUrl(projectId: string): string {
    return `${apiBase()}${BASE}/works/${projectId}/generate`;
  },
  // T3.2 — the SSE selection-edit POST (rewrite/expand/describe over a selection).
  selectionEditUrl(projectId: string): string {
    return `${apiBase()}${BASE}/works/${projectId}/selection-edit`;
  },
  // V1 slice 3 — auto (diverge→converge): NON-streaming POST that returns the
  // winner + all K candidate texts (the human-gate cards).
  async generateAuto(projectId: string, params: AutoGenerateParams, token: string): Promise<AutoGeneration> {
    const resp = await apiJson<AutoGeneration>(`${BASE}/works/${projectId}/generate`, {
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
    // M4: flag-on → 202 pending; poll then shape job.result like the inline JSON.
    return _resolveJob(resp, token, (job) => ({
      job_id: job.id, mode: 'auto', status: job.status,
      ...(job.result as Record<string, unknown>),
    }) as AutoGeneration);
  },
  // M4 — GET /jobs/{id} poll target (the worker writes job.result on completion).
  getJob(jobId: string, token: string): Promise<GenerationJob> {
    return apiJson(`${BASE}/jobs/${jobId}`, { token });
  },
  // M4 — poll a job to terminal (used by the SSE consumer's 202 fallback when a
  // stream endpoint answers a batch job instead). Stops early if `signal` aborts.
  awaitJob(jobId: string, token: string, signal?: AbortSignal): Promise<GenerationJob> {
    return _pollJob(jobId, token, signal);
  },
  // M4 Option A accept-step — persist a worker-computed chapter result to the book
  // draft with the caller's bearer (the worker has none). Idempotent; 422 if the
  // job has no chapter_id/text, 409 if not completed.
  persistJob(
    jobId: string, token: string, commitMessage?: string,
  ): Promise<{ job_id: string; persisted: boolean; draft_version?: number | null; persist_error?: string | null; already?: boolean }> {
    return apiJson(`${BASE}/jobs/${jobId}/persist`, {
      method: 'POST', token,
      body: JSON.stringify(commitMessage ? { commit_message: commitMessage } : {}),
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
  async generateChapter(projectId: string, chapterId: string, params: ChapterAssembleParams, token: string): Promise<ChapterGeneration> {
    const resp = await apiJson<ChapterGeneration>(`${BASE}/works/${projectId}/chapters/${chapterId}/generate`, {
      method: 'POST', token,
      body: JSON.stringify({
        model_source: params.modelSource ?? 'user_model', model_ref: params.modelRef,
        reasoning: params.reasoning ?? 'auto', model_kind: params.modelKind, model_name: params.modelName,
        persist: params.persist ?? false,
      }),
    });
    // M4: flag-on → 202 pending. The worker computes + stores (persisted=false,
    // Option A); the FE accepts via persistJob. flag-off → inline result verbatim.
    return _resolveJob(resp, token, (job) => ({
      job_id: job.id, status: job.status, ...(job.result as Record<string, unknown>),
    }) as ChapterGeneration);
  },
  // B3 stitch — merge a chapter's done scene drafts into one seamless chapter.
  async stitchChapter(projectId: string, chapterId: string, params: ChapterAssembleParams, token: string): Promise<ChapterGeneration> {
    const resp = await apiJson<ChapterGeneration>(`${BASE}/works/${projectId}/chapters/${chapterId}/stitch`, {
      method: 'POST', token,
      body: JSON.stringify({
        model_source: params.modelSource ?? 'user_model', model_ref: params.modelRef,
        reasoning: params.reasoning ?? 'auto', model_kind: params.modelKind, model_name: params.modelName,
        persist: params.persist ?? false,
      }),
    });
    return _resolveJob(resp, token, (job) => ({
      job_id: job.id, status: job.status, ...(job.result as Record<string, unknown>),
    }) as ChapterGeneration);
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
