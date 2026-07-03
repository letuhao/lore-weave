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
}
