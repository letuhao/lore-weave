// AG-UI protocol event subset the admin chat client consumes (ported from the
// main FE — frontend/src/features/chat/hooks/agUiEvents.ts). chat-service emits
// these over SSE when a request carries `x-loreweave-stream-format: agui`.

export const AgUiEventType = {
  RUN_STARTED: 'RUN_STARTED',
  RUN_FINISHED: 'RUN_FINISHED',
  RUN_ERROR: 'RUN_ERROR',
  TEXT_MESSAGE_CONTENT: 'TEXT_MESSAGE_CONTENT',
  REASONING_MESSAGE_CONTENT: 'REASONING_MESSAGE_CONTENT',
  TOOL_CALL_START: 'TOOL_CALL_START',
  TOOL_CALL_ARGS: 'TOOL_CALL_ARGS',
  TOOL_CALL_END: 'TOOL_CALL_END',
  TOOL_CALL_RESULT: 'TOOL_CALL_RESULT',
  CUSTOM: 'CUSTOM',
} as const;

export type AgUiEventType = (typeof AgUiEventType)[keyof typeof AgUiEventType];

export interface TextMessageContentEvent {
  type: 'TEXT_MESSAGE_CONTENT';
  messageId: string;
  delta: string;
}

export interface ToolCallStartEvent {
  type: 'TOOL_CALL_START';
  toolCallId: string;
  toolCallName: string;
}

export interface ToolCallArgsEvent {
  type: 'TOOL_CALL_ARGS';
  toolCallId: string;
  delta?: string;
}

export interface ToolCallResultEvent {
  type: 'TOOL_CALL_RESULT';
  toolCallId: string;
  content: string;
}

export interface RunFinishedEvent {
  type: 'RUN_FINISHED';
  result?: {
    messageId?: string;
    status?: string;
    pendingToolCall?: { runId: string; toolCallId: string; toolName: string };
  };
}

export interface RunErrorEvent {
  type: 'RUN_ERROR';
  message: string;
  code?: string;
}

export interface AgUiCustomEvent {
  type: 'CUSTOM';
  name: string;
  value: Record<string, unknown>;
}
