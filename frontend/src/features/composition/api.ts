// LOOM Composition (M8) — gateway calls. Relative /v1 rides the Vite proxy →
// gateway (dev :3123) / nginx (prod). The generate SSE stream is NOT here — it
// uses a raw fetch+ReadableStream in useCompositionStream (apiJson can't stream).
import { apiBase, apiJson } from '../../api';
import type {
  CanonRule, GenerationJob, Grounding, OutlineNode, PublishGate, Work, WorkResolution,
} from './types';

const BASE = '/v1/composition';

export const compositionApi = {
  resolveWork(bookId: string, token: string): Promise<WorkResolution> {
    return apiJson<WorkResolution>(`${BASE}/books/${bookId}/work`, { token });
  },
  createWork(bookId: string, token: string): Promise<Work> {
    return apiJson<Work>(`${BASE}/books/${bookId}/work`, { method: 'POST', token });
  },
  getOutline(projectId: string, token: string): Promise<{ nodes: OutlineNode[]; scene_links: unknown[] }> {
    return apiJson(`${BASE}/works/${projectId}/outline`, { token });
  },
  createNode(projectId: string, payload: Partial<OutlineNode> & { kind: string }, token: string): Promise<OutlineNode> {
    return apiJson(`${BASE}/works/${projectId}/outline/nodes`, { method: 'POST', body: JSON.stringify(payload), token });
  },
  // Patch an outline node (M9: set a scene's status — 'done' commits it for the
  // chapter-gate + emits composition.scene_committed server-side).
  patchNode(nodeId: string, patch: Partial<OutlineNode>, token: string): Promise<OutlineNode> {
    return apiJson(`${BASE}/outline/nodes/${nodeId}`, { method: 'PATCH', body: JSON.stringify(patch), token });
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
  getJob(jobId: string, token: string): Promise<GenerationJob> {
    return apiJson(`${BASE}/jobs/${jobId}`, { token });
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
};
