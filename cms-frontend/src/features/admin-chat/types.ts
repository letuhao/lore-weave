// T4d — types for the CMS admin chat panel. A focused mirror of the main-FE
// chat types, scoped to what the System-tier admin assistant needs.

export interface ChatSession {
  session_id: string;
  title: string;
  model_source: string;
  model_ref: string;
  status: 'active' | 'archived';
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  message_id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  created_at: string;
  // Tool chips accumulated during the assistant turn (live) — admin propose +
  // the pending confirm card.
  tool_calls?: ToolCallRecord[];
}

// One tool invocation surfaced during an assistant turn. A `pending` record is
// the suspended glossary_confirm_action awaiting the admin's Confirm/Cancel —
// it carries the runId/toolCallId to resume and the confirm args.
export interface ToolCallRecord {
  tool: string;
  ok: boolean;
  pending?: boolean;
  runId?: string;
  toolCallId?: string;
  args?: Record<string, unknown>;
}

// The outcome the FE reports back to chat-service on resume (H6 truthful resume).
export type AdminToolOutcome = 'action_done' | 'token_expired' | 'action_error' | 'cancelled';

// A current-state preview row from POST /actions/admin/preview (non-consuming).
export interface ActionPreviewRow {
  label: string;
  value: string;
  note?: string;
}

export interface ActionPreview {
  title?: string;
  destructive?: boolean;
  preview_rows?: ActionPreviewRow[];
}

export interface UserModelOption {
  user_model_id: string;
  provider_kind: string;
  provider_model_name: string;
  alias?: string | null;
  is_favorite: boolean;
}
