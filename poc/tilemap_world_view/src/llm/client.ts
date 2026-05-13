import type {
  ChatCompletionRequest,
  ChatCompletionResponse,
  ChatMessage,
  LlmCallOptions,
} from './types';

const LLM_PROXY_PATH = '/api/llm/chat/completions';

/**
 * Single LLM call to local lmstudio (or any OpenAI-compatible endpoint).
 *
 * Proxied via Vite at /api/llm → http://localhost:1234/v1 (default).
 * Override endpoint via .env.local: VITE_LLM_ENDPOINT=http://...
 *
 * Returns raw response content. Higher-level orchestration (parsing, validation,
 * retry) lives in skeleton_generator.ts.
 */
export async function callLlm(
  messages: ChatMessage[],
  opts: LlmCallOptions,
): Promise<{ content: string; tokens?: number }> {
  // NOTE: response_format intentionally omitted for max compatibility.
  // Old lmstudio (<=0.2.x) supports `json_object`; new lmstudio (>=0.3.x) only
  // supports `json_schema` + `text`; OpenAI accepts both. Omitting falls back to
  // prompt-driven JSON output + stripJsonFences() in skeleton_generator.ts.
  //
  // max_tokens default 16000: handles thinking-mode reasoning models (Qwen 3,
  // DeepSeek R1, OpenAI o1) that may burn many tokens on internal reasoning.
  // Combined with `/no_think` directive in prompts.ts, output should normally fit
  // in 1500 tokens, but the larger budget catches edge cases where directive is
  // ignored or model can't disable thinking.
  const body: ChatCompletionRequest = {
    model: opts.model,
    messages,
    temperature: opts.temperature ?? 0.7,
    max_tokens: opts.maxTokens ?? 16000,
    stream: false,
  };

  let res: Response;
  try {
    res = await fetch(LLM_PROXY_PATH, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (e) {
    throw new LlmNetworkError(
      `Cannot reach LLM endpoint via /api/llm. Is lmstudio running on localhost:1234? ` +
        `Original: ${e instanceof Error ? e.message : String(e)}`,
    );
  }

  if (!res.ok) {
    const text = await res.text().catch(() => '<unreadable>');
    throw new LlmHttpError(`LLM HTTP ${res.status}: ${text}`, res.status);
  }

  let data: ChatCompletionResponse;
  try {
    data = (await res.json()) as ChatCompletionResponse;
  } catch (e) {
    throw new LlmResponseError(
      `LLM response was not valid JSON: ${e instanceof Error ? e.message : String(e)}`,
    );
  }

  if (!data.choices || data.choices.length === 0) {
    throw new LlmResponseError('LLM response had no choices');
  }
  const choice = data.choices[0];
  const content = choice.message?.content;
  if (typeof content !== 'string') {
    throw new LlmResponseError('LLM response message.content was not a string');
  }

  // Detect thinking-mode token burn — empty content + finish_reason="length"
  // means model used all output budget on internal reasoning (Qwen 3, DeepSeek R1, etc.)
  if (content.length === 0 && choice.finish_reason === 'length') {
    const reasoningTokens =
      (data.usage as { completion_tokens_details?: { reasoning_tokens?: number } } | undefined)
        ?.completion_tokens_details?.reasoning_tokens;
    throw new LlmResponseError(
      `LLM hit max_tokens with empty output (likely thinking-mode burn-through). ` +
        `Reasoning tokens used: ${reasoningTokens ?? '?'}. ` +
        `Fixes: (1) ensure prompt has /no_think directive (Qwen 3); ` +
        `(2) increase maxTokens; (3) switch to non-reasoning model variant.`,
    );
  }

  return {
    content,
    tokens: data.usage?.total_tokens,
  };
}

/** Probe LLM endpoint reachability — small request to verify connectivity. */
export async function probeLlm(opts: { model: string; signal?: AbortSignal }): Promise<{
  ok: boolean;
  message: string;
  endpoint: string;
}> {
  try {
    const res = await fetch('/api/llm/models', {
      method: 'GET',
      signal: opts.signal,
    });
    if (!res.ok) {
      return {
        ok: false,
        message: `Endpoint returned HTTP ${res.status}`,
        endpoint: LLM_PROXY_PATH,
      };
    }
    const data = await res.json().catch(() => ({}));
    const modelCount = Array.isArray(data?.data) ? data.data.length : 0;
    return {
      ok: true,
      message: `Reachable; ${modelCount} model(s) loaded`,
      endpoint: LLM_PROXY_PATH,
    };
  } catch (e) {
    return {
      ok: false,
      message: e instanceof Error ? e.message : String(e),
      endpoint: LLM_PROXY_PATH,
    };
  }
}

// ─── Error classes ───────────────────────────────────────────────────────

export class LlmNetworkError extends Error {
  constructor(msg: string) {
    super(msg);
    this.name = 'LlmNetworkError';
  }
}

export class LlmHttpError extends Error {
  constructor(
    msg: string,
    public status: number,
  ) {
    super(msg);
    this.name = 'LlmHttpError';
  }
}

export class LlmResponseError extends Error {
  constructor(msg: string) {
    super(msg);
    this.name = 'LlmResponseError';
  }
}
