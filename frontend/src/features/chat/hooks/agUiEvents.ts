// ARCH-1 C4 — AG-UI protocol event names + the event shapes the chat client
// consumes. chat-service emits these over SSE when a request carries
// `x-loreweave-stream-format: agui` (see services/chat-service C3).
//
// We deliberately do NOT depend on `@ag-ui/core` for this: that package pulls
// `zod@^3` for runtime schemas, but the frontend already runs `zod@4` (a
// breaking major), so adding it would install a second nested copy of zod just
// to deliver an enum + a handful of types we reference in one switch. Per the
// "only add a library if it reduces maintenance; don't import what we won't
// use" rule, we instead pin the exact wire strings here. The values are the
// canonical AG-UI `EventType` SCREAMING_SNAKE strings, so this stays a faithful
// single source for the subset we handle; if we later need the full protocol
// (validation, all 25+ events) we can revisit the package then.

/** AG-UI event `type` wire values (subset the chat client handles). */
export const AgUiEventType = {
  RUN_STARTED: 'RUN_STARTED',
  RUN_FINISHED: 'RUN_FINISHED',
  RUN_ERROR: 'RUN_ERROR',
  TEXT_MESSAGE_START: 'TEXT_MESSAGE_START',
  TEXT_MESSAGE_CONTENT: 'TEXT_MESSAGE_CONTENT',
  TEXT_MESSAGE_END: 'TEXT_MESSAGE_END',
  REASONING_START: 'REASONING_START',
  REASONING_MESSAGE_START: 'REASONING_MESSAGE_START',
  REASONING_MESSAGE_CONTENT: 'REASONING_MESSAGE_CONTENT',
  REASONING_MESSAGE_END: 'REASONING_MESSAGE_END',
  REASONING_END: 'REASONING_END',
  TOOL_CALL_START: 'TOOL_CALL_START',
  TOOL_CALL_ARGS: 'TOOL_CALL_ARGS',
  TOOL_CALL_END: 'TOOL_CALL_END',
  TOOL_CALL_RESULT: 'TOOL_CALL_RESULT',
  CUSTOM: 'CUSTOM',
} as const;

export type AgUiEventType = (typeof AgUiEventType)[keyof typeof AgUiEventType];

// ── Event payloads (camelCase wire fields) ─────────────────────────────────
// Only the fields the chat client reads are typed; AG-UI events may carry more
// (e.g. timestamp), which we ignore.

interface BaseEvent {
  type: string;
}

export interface RunStartedEvent extends BaseEvent {
  type: 'RUN_STARTED';
  threadId: string;
  runId: string;
}

export interface RunFinishedEvent extends BaseEvent {
  type: 'RUN_FINISHED';
  result?: {
    finishReason?: string;
    usage?: { promptTokens?: number; completionTokens?: number };
    timing?: { responseTimeMs?: number; timeToFirstTokenMs?: number };
    messageId?: string;
  };
}

export interface RunErrorEvent extends BaseEvent {
  type: 'RUN_ERROR';
  message: string;
  code?: string;
}

export interface TextMessageContentEvent extends BaseEvent {
  type: 'TEXT_MESSAGE_CONTENT';
  messageId: string;
  delta: string;
}

export interface ReasoningMessageContentEvent extends BaseEvent {
  type: 'REASONING_MESSAGE_CONTENT';
  messageId: string;
  delta: string;
}

export interface ToolCallStartEvent extends BaseEvent {
  type: 'TOOL_CALL_START';
  toolCallId: string;
  toolCallName: string;
  parentMessageId?: string;
}

export interface ToolCallResultEvent extends BaseEvent {
  type: 'TOOL_CALL_RESULT';
  messageId: string;
  toolCallId: string;
  content: string;
  role?: string;
}

/** CUSTOM is AG-UI's app-specific channel. C3 uses it for two LoreWeave
 *  signals: `memoryMode` (the knowledge-context mode) and `persisted` (the
 *  saved message/output ids). `value` is an arbitrary object per the spec. */
export interface CustomEvent extends BaseEvent {
  type: 'CUSTOM';
  name: string;
  value: Record<string, unknown>;
}

/** A parsed AG-UI event the client may receive. Framing-only events
 *  (TEXT_MESSAGE_START/END, REASONING_* boundaries, TOOL_CALL_ARGS/END) carry
 *  no state the client needs, so they are typed loosely as BaseEvent. */
export type AgUiEvent =
  | RunStartedEvent
  | RunFinishedEvent
  | RunErrorEvent
  | TextMessageContentEvent
  | ReasoningMessageContentEvent
  | ToolCallStartEvent
  | ToolCallResultEvent
  | CustomEvent
  | BaseEvent;
