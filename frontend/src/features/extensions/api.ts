// Agent Extensibility Registry — FE API layer (P1 slice).
import { apiJson } from '@/api';
import type {
  Skill,
  SkillList,
  ProposalList,
  UsageCounters,
  McpServer,
  McpServerList,
  CreateMcpServerReq,
  ScanResult,
  HealthResult,
  SlashCommand,
  CommandList,
  CreateCommandReq,
  Hook,
  HookList,
  CreateHookReq,
  PluginList,
  CascadePreview,
  PluginBundle,
  Subagent,
  SubagentList,
  CreateSubagentReq,
  AuditList,
  IngestQueueList,
  IngestPullCounts,
  ApprovalKind,
  ToolDecision,
  ToolPermission,
  ToolPermissionList,
  ToolCatalogResponse,
} from './types';

const BASE = '/v1/agent-registry';
// The tool-consent allowlist is owned by chat-service (it is the tool loop's gate),
// not the registry — same page, different service.
const CHAT_BASE = '/v1/chat';

export const extensionsApi = {
  listSkills(
    token: string,
    params: { q?: string; tier?: string; sort?: string; limit?: number; offset?: number; book_id?: string } = {},
  ): Promise<SkillList> {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    if (params.tier) qs.set('tier', params.tier);
    if (params.sort) qs.set('sort', params.sort);
    if (params.book_id) qs.set('book_id', params.book_id);
    qs.set('limit', String(params.limit ?? 20));
    qs.set('offset', String(params.offset ?? 0));
    return apiJson<SkillList>(`${BASE}/skills?${qs.toString()}`, { token });
  },

  createSkill(
    token: string,
    body: { slug: string; description: string; body_md: string; surfaces?: string[]; status?: string; tier?: string; book_id?: string },
  ): Promise<Skill> {
    return apiJson<Skill>(`${BASE}/skills`, { method: 'POST', token, body: JSON.stringify(body) });
  },

  patchSkill(token: string, id: string, patch: Partial<Pick<Skill, 'description' | 'body_md' | 'surfaces' | 'status'>>): Promise<Skill> {
    return apiJson<Skill>(`${BASE}/skills/${id}`, { method: 'PATCH', token, body: JSON.stringify(patch) });
  },

  deleteSkill(token: string, id: string): Promise<void> {
    return apiJson<void>(`${BASE}/skills/${id}`, { method: 'DELETE', token });
  },

  setSkillEnabled(token: string, id: string, enabled: boolean): Promise<void> {
    return apiJson<void>(`${BASE}/skills/${id}/enablement`, {
      method: 'PUT',
      token,
      body: JSON.stringify({ enabled }),
    });
  },

  shadowCheck(token: string, slug: string): Promise<{ slug: string; shadows_system: boolean }> {
    return apiJson(`${BASE}/skills/shadow-check?slug=${encodeURIComponent(slug)}`, { token });
  },

  listProposals(
    token: string,
    params: { status?: string; sort?: string; limit?: number; offset?: number } = {},
  ): Promise<ProposalList> {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.sort) qs.set('sort', params.sort);
    qs.set('limit', String(params.limit ?? 20));
    qs.set('offset', String(params.offset ?? 0));
    return apiJson<ProposalList>(`${BASE}/proposals?${qs.toString()}`, { token });
  },

  approveProposal(token: string, id: string): Promise<{ proposal_id: string; status: string; slug: string }> {
    return apiJson(`${BASE}/proposals/${id}/approve`, { method: 'PUT', token });
  },

  rejectProposal(token: string, id: string, reason = ''): Promise<{ proposal_id: string; status: string }> {
    return apiJson(`${BASE}/proposals/${id}/reject`, {
      method: 'POST',
      token,
      body: JSON.stringify({ reason }),
    });
  },

  usage(token: string): Promise<UsageCounters> {
    return apiJson<UsageCounters>(`${BASE}/usage`, { token });
  },

  // ── P3: external MCP servers ──────────────────────────────────────────────
  listMcpServers(
    token: string,
    params: { status?: string; limit?: number; offset?: number; book_id?: string } = {},
  ): Promise<McpServerList> {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.book_id) qs.set('book_id', params.book_id);
    qs.set('limit', String(params.limit ?? 20));
    qs.set('offset', String(params.offset ?? 0));
    return apiJson<McpServerList>(`${BASE}/mcp-servers?${qs.toString()}`, { token });
  },

  getMcpServer(token: string, id: string): Promise<McpServer> {
    return apiJson<McpServer>(`${BASE}/mcp-servers/${id}`, { token });
  },

  createMcpServer(token: string, body: CreateMcpServerReq): Promise<McpServer> {
    return apiJson<McpServer>(`${BASE}/mcp-servers`, { method: 'POST', token, body: JSON.stringify(body) });
  },

  deleteMcpServer(token: string, id: string): Promise<void> {
    return apiJson<void>(`${BASE}/mcp-servers/${id}`, { method: 'DELETE', token });
  },

  setMcpEnabled(token: string, id: string, enabled: boolean): Promise<void> {
    return apiJson<void>(`${BASE}/mcp-servers/${id}/enablement`, { method: 'PUT', token, body: JSON.stringify({ enabled }) });
  },

  rescanMcpServer(token: string, id: string): Promise<{ mcp_server_id: string; status: string; scan_result: ScanResult; last_health: HealthResult; probe_error?: string }> {
    return apiJson(`${BASE}/mcp-servers/${id}/rescan`, { method: 'POST', token });
  },

  acceptRiskMcpServer(token: string, id: string): Promise<{ mcp_server_id: string; status: string; risk_accepted: boolean }> {
    return apiJson(`${BASE}/mcp-servers/${id}/accept-risk`, { method: 'POST', token });
  },

  startMcpOAuth(token: string, id: string): Promise<{ authorization_url: string; state: string }> {
    return apiJson(`${BASE}/mcp-servers/${id}/oauth/start`, { method: 'POST', token });
  },

  // ── P4: slash commands ────────────────────────────────────────────────────
  listCommands(token: string, params: { q?: string; limit?: number; offset?: number; book_id?: string } = {}): Promise<CommandList> {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    if (params.book_id) qs.set('book_id', params.book_id);
    qs.set('limit', String(params.limit ?? 50));
    qs.set('offset', String(params.offset ?? 0));
    return apiJson<CommandList>(`${BASE}/commands?${qs.toString()}`, { token });
  },
  createCommand(token: string, body: CreateCommandReq): Promise<SlashCommand> {
    return apiJson<SlashCommand>(`${BASE}/commands`, { method: 'POST', token, body: JSON.stringify(body) });
  },
  patchCommand(token: string, id: string, patch: Partial<SlashCommand>): Promise<SlashCommand> {
    return apiJson<SlashCommand>(`${BASE}/commands/${id}`, { method: 'PATCH', token, body: JSON.stringify(patch) });
  },
  deleteCommand(token: string, id: string): Promise<void> {
    return apiJson<void>(`${BASE}/commands/${id}`, { method: 'DELETE', token });
  },

  // ── P4: declarative hooks ─────────────────────────────────────────────────
  listHooks(token: string, params: { on_event?: string; limit?: number; offset?: number; book_id?: string } = {}): Promise<HookList> {
    const qs = new URLSearchParams();
    if (params.on_event) qs.set('on_event', params.on_event);
    if (params.book_id) qs.set('book_id', params.book_id);
    qs.set('limit', String(params.limit ?? 50));
    qs.set('offset', String(params.offset ?? 0));
    return apiJson<HookList>(`${BASE}/hooks?${qs.toString()}`, { token });
  },
  createHook(token: string, body: CreateHookReq): Promise<Hook> {
    return apiJson<Hook>(`${BASE}/hooks`, { method: 'POST', token, body: JSON.stringify(body) });
  },
  patchHook(token: string, id: string, patch: Partial<Hook>): Promise<Hook> {
    return apiJson<Hook>(`${BASE}/hooks/${id}`, { method: 'PATCH', token, body: JSON.stringify(patch) });
  },
  deleteHook(token: string, id: string): Promise<void> {
    return apiJson<void>(`${BASE}/hooks/${id}`, { method: 'DELETE', token });
  },

  // ── P5: plugins + bundles ─────────────────────────────────────────────────
  listPlugins(token: string, params: { q?: string; limit?: number; offset?: number } = {}): Promise<PluginList> {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    qs.set('limit', String(params.limit ?? 50));
    qs.set('offset', String(params.offset ?? 0));
    return apiJson<PluginList>(`${BASE}/plugins?${qs.toString()}`, { token });
  },
  deletePlugin(token: string, id: string): Promise<void> {
    return apiJson<void>(`${BASE}/plugins/${id}`, { method: 'DELETE', token });
  },
  cascadePreview(token: string, id: string): Promise<CascadePreview> {
    return apiJson<CascadePreview>(`${BASE}/plugins/${id}/cascade-preview`, { token });
  },
  exportBundle(token: string, id: string): Promise<PluginBundle> {
    return apiJson<PluginBundle>(`${BASE}/plugins/${id}/export`, { token });
  },
  importBundle(token: string, bundle: PluginBundle): Promise<{ plugin_id: string; name: string; imported: Record<string, number> }> {
    return apiJson(`${BASE}/plugins/import`, { method: 'POST', token, body: JSON.stringify(bundle) });
  },

  // ── P5: subagent personas ─────────────────────────────────────────────────
  listSubagents(token: string, params: { limit?: number; offset?: number; book_id?: string } = {}): Promise<SubagentList> {
    const qs = new URLSearchParams();
    if (params.book_id) qs.set('book_id', params.book_id);
    qs.set('limit', String(params.limit ?? 50));
    qs.set('offset', String(params.offset ?? 0));
    return apiJson<SubagentList>(`${BASE}/subagents?${qs.toString()}`, { token });
  },
  createSubagent(token: string, body: CreateSubagentReq): Promise<Subagent> {
    return apiJson<Subagent>(`${BASE}/subagents`, { method: 'POST', token, body: JSON.stringify(body) });
  },
  patchSubagent(token: string, id: string, patch: Partial<Pick<Subagent, 'description' | 'system_prompt' | 'tool_scope' | 'model_ref' | 'enabled'>>): Promise<Subagent> {
    return apiJson<Subagent>(`${BASE}/subagents/${id}`, { method: 'PATCH', token, body: JSON.stringify(patch) });
  },
  deleteSubagent(token: string, id: string): Promise<void> {
    return apiJson<void>(`${BASE}/subagents/${id}`, { method: 'DELETE', token });
  },

  // ── Activity log (registry audit) ─────────────────────────────────────────
  listAudit(token: string, params: { kind?: string; range?: '7d' | '30d'; limit?: number; offset?: number } = {}): Promise<AuditList> {
    const qs = new URLSearchParams();
    if (params.kind) qs.set('kind', params.kind);
    if (params.range) qs.set('range', params.range);
    qs.set('limit', String(params.limit ?? 50));
    qs.set('offset', String(params.offset ?? 0));
    return apiJson<AuditList>(`${BASE}/audit?${qs.toString()}`, { token });
  },

  // ── Official-registry ingest — admin curation (REG-P5-03). All admin-only; the
  // API returns 403 for a non-admin regardless of the FE show/hide gate.
  ingestPull(token: string): Promise<IngestPullCounts> {
    return apiJson<IngestPullCounts>(`${BASE}/admin/ingest/pull`, { method: 'POST', token });
  },
  listIngestQueue(token: string, params: { status?: string; limit?: number; offset?: number } = {}): Promise<IngestQueueList> {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    qs.set('limit', String(params.limit ?? 50));
    qs.set('offset', String(params.offset ?? 0));
    return apiJson<IngestQueueList>(`${BASE}/admin/ingest/queue?${qs.toString()}`, { token });
  },
  approveIngest(token: string, id: string): Promise<{ ingest_id: string; status: string; mcp_server_id?: string; linked_existing?: boolean }> {
    return apiJson(`${BASE}/admin/ingest/queue/${id}/approve`, { method: 'POST', token });
  },
  rejectIngest(token: string, id: string, reason = ''): Promise<{ ingest_id: string; status: string }> {
    return apiJson(`${BASE}/admin/ingest/queue/${id}/reject`, { method: 'POST', token, body: JSON.stringify({ reason }) });
  },

  // ── Track C WS-3 — the tool-consent allowlist. NOTE the different base: these live
  // on chat-service (/v1/chat), which owns `user_tool_approvals`, not the registry.
  listToolPermissions(token: string): Promise<ToolPermissionList> {
    return apiJson<ToolPermissionList>(`${CHAT_BASE}/tool-permissions`, { token });
  },
  setToolPermission(
    token: string, toolName: string, kind: ApprovalKind, decision: ToolDecision,
  ): Promise<ToolPermission> {
    return apiJson<ToolPermission>(`${CHAT_BASE}/tool-permissions/${encodeURIComponent(toolName)}`, {
      method: 'PUT', token, body: JSON.stringify({ kind, decision }),
    });
  },
  listToolCatalog(token: string): Promise<ToolCatalogResponse> {
    return apiJson<ToolCatalogResponse>(`${CHAT_BASE}/tools/catalog`, { token });
  },
  revokeToolPermission(token: string, toolName: string, kind: ApprovalKind): Promise<void> {
    return apiJson<void>(
      `${CHAT_BASE}/tool-permissions/${encodeURIComponent(toolName)}?kind=${kind}`,
      { method: 'DELETE', token },
    );
  },
};
