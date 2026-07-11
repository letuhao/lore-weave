// Frontend-tool liveness injection (Track D · WS-D5).
//
// PROBLEM this solves. The 12 client-executed "frontend tools" (ui_navigate,
// ui_open_studio_panel, propose_edit, confirm_action, …) span two services and
// two languages joined only by the LLM. G3 (call-shape + the resolver never
// silently no-ops) is proven deterministically by the pure-resolver contract
// tests (frontendToolContract.test.ts + test_frontend_tools_contract.py). But
// G4 — "the REAL browser resolver actually executes the tool and the
// suspend→resume round-trip closes" — needs the live browser
// (agent-gui-loop-needs-live-browser-smoke-not-raw-stream).
//
// We must NOT depend on a local model *choosing* to emit a given frontend tool
// (S06 showed that choice is non-deterministic). So this helper INJECTS a
// suspended frontend-tool call by intercepting the chat send and fulfilling it
// with a canned AG-UI SSE stream whose frames are byte-compatible with
// chat-service's AgUiEmitter (services/chat-service/app/services/stream_events.py:
// tool_call_pending + finish(status="suspended")). The FE then runs its REAL
// executor/resolver/card, and we assert the DOM/router effect + capture the
// resume POST to /tool-results. The only simulated part is the *trigger*; every
// line of FE execution under test is real.
import type { Page, Route } from '@playwright/test';

export interface SuspendedToolInjection {
  tool: string;
  args: Record<string, unknown>;
  /** assistant prose shown in the bubble before the pending card/executor. */
  text?: string;
  runId?: string;
  toolCallId?: string;
  messageId?: string;
}

// Stable-ish ids without Math.random (deterministic across a spec run is fine;
// uniqueness within a page is all we need).
let _seq = 0;
function id(prefix: string): string {
  _seq += 1;
  return `${prefix}-tle-${_seq.toString(16).padStart(4, '0')}`;
}

function sse(obj: unknown): string {
  return `data: ${JSON.stringify(obj)}\n\n`;
}

/**
 * The canned AG-UI stream for a turn that ends SUSPENDED on a frontend tool.
 * Mirrors AgUiEmitter: TEXT_MESSAGE_* (optional prose) → TOOL_CALL_START/ARGS/END
 * (NO RESULT — that's the whole point of a client-executed tool) → RUN_FINISHED
 * with result.status="suspended" + pendingToolCall. runChatStream.ts:414-445
 * reads exactly this to push a `{pending:true, runId, toolCallId, args}` record.
 */
export function buildSuspendedSSE(inj: Required<Omit<SuspendedToolInjection, 'args' | 'tool'>> & { tool: string; args: Record<string, unknown> }): string {
  const { tool, args, text, runId, toolCallId, messageId } = inj;
  const frames: string[] = [];
  frames.push(sse({ type: 'RUN_STARTED', threadId: 'tle-thread', runId }));
  frames.push(sse({ type: 'TEXT_MESSAGE_START', messageId, role: 'assistant' }));
  if (text) frames.push(sse({ type: 'TEXT_MESSAGE_CONTENT', messageId, delta: text }));
  frames.push(sse({ type: 'TEXT_MESSAGE_END', messageId }));
  // The client-executed tool: START/ARGS/END, then a SUSPENDED finish. The
  // toolCallId on ARGS MUST equal pendingToolCall.toolCallId — the FE reads
  // openToolArgs.get(p.toolCallId) to recover the proposal payload.
  frames.push(sse({ type: 'TOOL_CALL_START', toolCallId, toolCallName: tool, parentMessageId: messageId }));
  frames.push(sse({ type: 'TOOL_CALL_ARGS', toolCallId, delta: JSON.stringify(args) }));
  frames.push(sse({ type: 'TOOL_CALL_END', toolCallId }));
  frames.push(
    sse({
      type: 'RUN_FINISHED',
      result: {
        finishReason: 'tool_calls',
        usage: { promptTokens: 0, completionTokens: 0 },
        timing: {},
        status: 'suspended',
        pendingToolCall: { runId, toolCallId, toolName: tool },
        messageId,
      },
    }),
  );
  return frames.join('');
}

/** A clean, non-suspended finish for the resume (POST /tool-results) response. */
export function buildResumeSSE(text = 'Done.'): string {
  const messageId = id('msg-resume');
  return (
    sse({ type: 'RUN_STARTED', threadId: 'tle-thread', runId: id('run-resume') }) +
    sse({ type: 'TEXT_MESSAGE_START', messageId, role: 'assistant' }) +
    sse({ type: 'TEXT_MESSAGE_CONTENT', messageId, delta: text }) +
    sse({ type: 'TEXT_MESSAGE_END', messageId }) +
    sse({ type: 'CUSTOM', name: 'persisted', value: { messageId } }) +
    sse({ type: 'RUN_FINISHED', result: { finishReason: 'stop', usage: {}, timing: {}, status: 'success', messageId } })
  );
}

export interface InjectionHandles {
  /** resolves with the JSON body the FE POSTed to /tool-results (outcome/result). */
  resumeBody: Promise<Record<string, unknown>>;
  /** the ids used, for assertions. */
  runId: string;
  toolCallId: string;
}

/**
 * Arm the next chat send to suspend on `tool`, and capture the resume round-trip.
 *
 * - Intercepts the next `POST /v1/chat/sessions/*​/messages` → fulfils with the
 *   suspended SSE (the FE then executes the tool).
 * - Intercepts `POST /v1/chat/sessions/*​/tool-results` → captures the request
 *   body (proof the FE completed the round-trip) and fulfils with a clean finish.
 *
 * Returns a promise for the captured /tool-results body — awaiting it proves the
 * FE actually executed the tool and closed the loop (a silent no-op never posts).
 */
export async function installFrontendToolSuspend(page: Page, inj: SuspendedToolInjection): Promise<InjectionHandles> {
  const runId = inj.runId ?? id('run');
  const toolCallId = inj.toolCallId ?? id('call');
  const messageId = inj.messageId ?? id('msg');

  const sseBody = buildSuspendedSSE({
    tool: inj.tool,
    args: inj.args,
    text: inj.text ?? '',
    runId,
    toolCallId,
    messageId,
  });

  let resolveResume!: (b: Record<string, unknown>) => void;
  const resumeBody = new Promise<Record<string, unknown>>((r) => {
    resolveResume = r;
  });

  // The send (POST) → suspend. GET /messages (history load) must pass through —
  // only the POST send is the trigger. Un-route after the first POST so nothing else
  // is re-suspended.
  await page.route('**/v1/chat/sessions/*/messages*', async (route: Route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    await page.unroute('**/v1/chat/sessions/*/messages*');
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'x-loreweave-stream-format': 'agui', 'cache-control': 'no-cache' },
      body: sseBody,
    });
  });

  await page.route('**/v1/chat/sessions/*/tool-results*', async (route: Route) => {
    let parsed: Record<string, unknown> = {};
    try {
      parsed = JSON.parse(route.request().postData() ?? '{}');
    } catch {
      parsed = {};
    }
    resolveResume(parsed);
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'x-loreweave-stream-format': 'agui', 'cache-control': 'no-cache' },
      body: buildResumeSSE(),
    });
  });

  return { resumeBody, runId, toolCallId };
}
