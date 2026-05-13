import type { TileMapSkeleton } from '../data/types';
import { callLlm, LlmHttpError, LlmNetworkError, LlmResponseError } from './client';
import { buildInitialMessages, buildRetryMessages } from './prompts';
import { validateSkeleton } from './validator';
import type {
  AttemptRecord,
  ChatMessage,
  LlmCallOptions,
  LlmGenerationResult,
} from './types';

const MAX_ATTEMPTS = 3;

export interface SkeletonGenOptions extends LlmCallOptions {
  /** Optional progress callback — fires once per attempt with status */
  onProgress?: (info: { attempt: number; phase: 'calling' | 'parsing' | 'validating' | 'retrying' | 'done' | 'failed'; detail?: string }) => void;
}

/**
 * Orchestrate L1 skeleton generation:
 *   1. Build initial messages (system + few-shot + user)
 *   2. Call LLM
 *   3. Parse JSON from response
 *   4. Validate against schema + semantic rules
 *   5. If invalid AND attempts left: build retry messages with errors → goto 2
 *   6. Return last successful result OR final failure
 *
 * Result includes full attempt history for debugging + total tokens used.
 */
export async function generateSkeleton(
  userPrompt: string,
  opts: SkeletonGenOptions,
): Promise<LlmGenerationResult<TileMapSkeleton>> {
  const attempts: AttemptRecord[] = [];
  let messages = buildInitialMessages(userPrompt);
  let totalTokens = 0;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const startedAt = performance.now();
    const record: AttemptRecord = {
      attempt,
      prompt_messages_count: messages.length,
      succeeded: false,
      duration_ms: 0,
    };

    opts.onProgress?.({ attempt, phase: 'calling', detail: `messages=${messages.length}` });

    let raw: string;
    let tokens: number | undefined;
    try {
      const resp = await callLlm(messages, opts);
      raw = resp.content.trim();
      tokens = resp.tokens;
      record.raw_response = raw.slice(0, 500); // truncate for record
      record.tokens = tokens;
      if (tokens) totalTokens += tokens;
    } catch (e) {
      record.parse_error = formatError(e);
      record.duration_ms = performance.now() - startedAt;
      attempts.push(record);
      opts.onProgress?.({ attempt, phase: 'failed', detail: record.parse_error });
      // Hard failures (network, HTTP) — don't retry; user needs to fix infra
      if (
        e instanceof LlmNetworkError ||
        e instanceof LlmHttpError ||
        e instanceof LlmResponseError
      ) {
        return { ok: false, attempts, total_tokens: totalTokens };
      }
      // Other exceptions — also fail
      return { ok: false, attempts, total_tokens: totalTokens };
    }

    // Strip common LLM markdown wrapping (just in case response_format json_object isn't honored)
    raw = stripJsonFences(raw);

    opts.onProgress?.({ attempt, phase: 'parsing' });
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      record.parse_error = `JSON.parse failed: ${formatError(e)}`;
      record.duration_ms = performance.now() - startedAt;
      attempts.push(record);

      if (attempt >= MAX_ATTEMPTS) {
        opts.onProgress?.({ attempt, phase: 'failed', detail: 'max retries; last was JSON parse error' });
        return { ok: false, attempts, total_tokens: totalTokens };
      }

      messages = buildRetryMessages(messages, raw, [
        `Your previous response was not valid JSON. Parse error: ${record.parse_error}. ` +
          `Output ONLY a JSON object — no markdown, no explanation.`,
      ]);
      opts.onProgress?.({ attempt, phase: 'retrying', detail: 'JSON parse error' });
      continue;
    }

    opts.onProgress?.({ attempt, phase: 'validating' });
    const validation = validateSkeleton(parsed);
    if (validation.valid && validation.value) {
      record.succeeded = true;
      record.duration_ms = performance.now() - startedAt;
      attempts.push(record);
      opts.onProgress?.({ attempt, phase: 'done' });
      return {
        ok: true,
        value: validation.value,
        attempts,
        total_tokens: totalTokens,
      };
    }

    record.validation_errors = validation.errors;
    record.duration_ms = performance.now() - startedAt;
    attempts.push(record);

    if (attempt >= MAX_ATTEMPTS) {
      opts.onProgress?.({ attempt, phase: 'failed', detail: `validation: ${validation.errors.length} errors` });
      return { ok: false, attempts, total_tokens: totalTokens };
    }

    messages = buildRetryMessages(messages, raw, validation.errors);
    opts.onProgress?.({ attempt, phase: 'retrying', detail: `${validation.errors.length} errors` });
  }

  return { ok: false, attempts, total_tokens: totalTokens };
}

// ─── Helpers ─────────────────────────────────────────────────────────────

/**
 * Strip ```json ... ``` markdown fences if LLM wrapped JSON despite instruction.
 * Idempotent — returns input unchanged if no fences detected.
 */
function stripJsonFences(s: string): string {
  let out = s.trim();
  // Remove leading ```json or ``` fence
  out = out.replace(/^```(?:json)?\s*\n?/i, '');
  // Remove trailing ``` fence
  out = out.replace(/\n?```\s*$/i, '');
  return out.trim();
}

function formatError(e: unknown): string {
  if (e instanceof Error) return `${e.name}: ${e.message}`;
  return String(e);
}

// Re-export for convenience
export { callLlm, probeLlm } from './client';
export type { ChatMessage } from './types';
