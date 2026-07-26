// Agent Extensibility Registry — FE types (P1 slice: skills + proposals).
// Mirrors services/agent-registry-service response shapes.

export type SkillTier = 'system' | 'user' | 'book';
export type SkillStatus = 'draft' | 'published' | 'archived';

export interface Skill {
  skill_id: string;
  tier: SkillTier;
  slug: string;
  description: string;
  body_md: string;
  surfaces: string[];
  status: SkillStatus;
  source: string;
  used_count: number;
  created_at: string;
  updated_at: string;
}

export interface SkillList {
  items: Skill[];
  total: number;
  limit: number;
  offset: number;
}

export type ProposalStatus = 'pending' | 'approved' | 'rejected' | 'expired';

export interface Proposal {
  proposal_id: string;
  action: 'create' | 'update';
  slug: string;
  description: string;
  body_md: string;
  status: ProposalStatus;
  reject_reason: string;
  from_session_id: string;
  from_session_label: string;
  created_at: string;
  expires_at: string;
}

export interface ProposalList {
  items: Proposal[];
  total: number;
  limit: number;
  offset: number;
}

export interface UsageCounters {
  plugins: number;
  skills: { used: number; limit: number };
  mcp_servers: { used: number; limit: number };
  commands: { used: number; limit: number };
  proposals_pending: number;
  // S-12 badge: the split of proposals_pending (optional — back-compat with older responses).
  skill_proposals_pending?: number;
  workflow_proposals_pending?: number;
}

// ── P3: external MCP servers ────────────────────────────────────────────────
export type McpServerStatus = 'active' | 'pending' | 'suspended' | 'error';
export type McpAuthKind = 'none' | 'bearer' | 'oauth2';

export interface ScanFinding {
  tool: string;
  field: string;
  marker: string;
  severity: 'high' | 'medium';
  snippet: string;
}
export interface ScannedToolSummary {
  name: string;
  description: string;
  flagged: boolean;
}
export interface ScanResult {
  scanned_at?: string;
  clean?: boolean;
  tool_count?: number;
  findings?: ScanFinding[];
  tools?: ScannedToolSummary[];
}
export interface HealthResult {
  ok?: boolean;
  checked_at?: string;
  error?: string;
  tool_count?: number;
  latency_ms?: number;
}

export interface McpServer {
  mcp_server_id: string;
  tier: SkillTier;
  display_name: string;
  endpoint_url: string;
  transport: string;
  tool_name_prefix: string;
  status: McpServerStatus;
  auth_kind: McpAuthKind;
  is_external: boolean;
  has_secret: boolean;
  egress_allowlist?: string[];
  scan_result?: ScanResult;
  last_health?: HealthResult;
  last_scanned_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface McpServerList {
  items: McpServer[];
  total: number;
  limit: number;
  offset: number;
}

export interface OAuthConfig {
  authorization_endpoint: string;
  token_endpoint: string;
  client_id: string;
  scopes?: string[];
}

export interface CreateMcpServerReq {
  display_name: string;
  endpoint_url: string;
  auth_kind?: McpAuthKind;
  bearer_token?: string;
  egress_allowlist?: string[];
  oauth?: OAuthConfig;
  tier?: 'user' | 'book';
  book_id?: string;
}

// ── P4: slash commands + declarative hooks ──────────────────────────────────
export interface SlashCommand {
  command_id: string;
  tier: SkillTier;
  name: string;
  description: string;
  arg_schema: Record<string, unknown>;
  template_md: string;
  expand_side: 'server' | 'client';
  enabled: boolean;
  created_at: string;
  updated_at: string;
}
export interface CommandList {
  items: SlashCommand[];
  total: number;
  limit: number;
  offset: number;
}
export interface CreateCommandReq {
  name: string;
  description?: string;
  template_md: string;
  expand_side?: 'server' | 'client';
  arg_schema?: Record<string, unknown>;
  tier?: 'user' | 'book';
  book_id?: string;
}

export interface Plugin {
  plugin_id: string;
  tier: SkillTier;
  name: string;
  version: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
}
export interface PluginList {
  items: Plugin[];
  total: number;
  limit: number;
  offset: number;
}
export interface CascadePreview {
  skills: number;
  mcp_servers: number;
  commands: number;
  hooks: number;
  subagents: number;
}
// A portable plugin bundle (manifest + prompt-only members).
export interface PluginBundle {
  manifest: { name: string; version: string; description?: string };
  skills?: unknown[];
  commands?: unknown[];
  hooks?: unknown[];
}

export type HookEvent = 'pre_tool_call' | 'post_tool_call' | 'pre_turn' | 'post_turn';
export type HookActionKind = 'deny' | 'require_approval' | 'annotate' | 'inject_text';
export interface HookAction {
  kind: HookActionKind;
  message?: string;
  text?: string;
}
export interface Hook {
  hook_id: string;
  tier: SkillTier;
  name: string;
  description: string;
  on_event: HookEvent;
  match: Record<string, unknown>;
  action: HookAction;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}
export interface HookList {
  items: Hook[];
  total: number;
  limit: number;
  offset: number;
}
export interface CreateHookReq {
  name?: string;
  description?: string;
  on_event: HookEvent;
  match?: Record<string, unknown>;
  action: HookAction;
  priority?: number;
  tier?: 'user' | 'book';
  book_id?: string;
}

// ── P5: subagent personas (REG-P5-01) — a named persona (system_prompt) with a
// tool_scope (glob subset of the user's catalog) + an optional model_ref. The
// runtime (`run_subagent`) resolves + runs these; this is the authoring GUI.
export interface Subagent {
  subagent_id: string;
  tier: SkillTier;
  name: string;
  description: string;
  system_prompt: string;
  tool_scope: string[]; // allowed tool-name globs, e.g. ["glossary_*","kg_*"]
  model_ref: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}
export interface SubagentList {
  items: Subagent[];
  total: number;
  limit: number;
  offset: number;
}
export interface CreateSubagentReq {
  name: string;
  description?: string;
  system_prompt: string;
  tool_scope?: string[];
  model_ref?: string;
  tier?: 'user' | 'book';
  book_id?: string;
}

// ── Activity log (REG-X-01) — the append-only registry audit, owner-scoped.
export interface AuditEntry {
  audit_id: string;
  at: string;
  actor_kind: 'user' | 'agent' | 'admin' | 'system';
  kind: string;
  action: string;
  target_id: string | null;
  target_name: string;
  tier: string | null;
  detail: Record<string, unknown>;
}
export interface AuditList {
  items: AuditEntry[];
  total: number;
  limit: number;
  offset: number;
}

// ── Official-registry ingest — admin curation queue (REG-P5-03).
export type IngestStatus = 'pending' | 'approved' | 'rejected' | 'revoked_upstream';
export interface IngestEntry {
  ingest_id: string;
  source: string;
  registry_id: string;
  name: string;
  description: string;
  version: string;
  endpoint_url: string;
  status: IngestStatus;
  approved_server_id: string | null;
  reject_reason: string;
  first_seen_at: string;
  updated_at: string;
}
export interface IngestQueueList {
  items: IngestEntry[];
  total: number;
  limit: number;
  offset: number;
}
export interface IngestPullCounts {
  fetched: number;
  new: number;
  updated: number;
  skipped_no_remote: number;
  truncated: boolean;
}

// Track C WS-3 — the tool-consent allowlist (chat-service `user_tool_approvals`).
// `mutation` = "may write my data"; `spend` = "may cost me money" — two ORTHOGONAL
// consents, separately granted and separately revocable.
export type ApprovalKind = 'mutation' | 'spend';
export type ToolDecision = 'allow' | 'deny';
export interface ToolPermission {
  tool_name: string;
  kind: ApprovalKind;
  decision: ToolDecision;
  created_at: string;
}
export interface ToolPermissionList {
  permissions: ToolPermission[];
}

// The chat-service tool catalog (GET /v1/chat/tools/catalog) — backs the permissions
// panel's tool PICKER, so a user cannot block a tool that does not exist.
export interface ToolCatalogItem {
  name: string;
  domain: string;
  tier: string;
  description: string;
  visibility: string;
}
export interface ToolCatalogResponse {
  items: ToolCatalogItem[];
}
