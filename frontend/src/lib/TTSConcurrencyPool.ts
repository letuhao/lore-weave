/**
 * TTSConcurrencyPool — limits concurrent TTS requests to avoid overwhelming
 * the TTS service. Queues overflow requests and processes them as slots free up.
 *
 * Design ref: REALTIME_VOICE_PIPELINE.md §6.4
 */

export interface TTSRequestOptions {
  text: string;
  modelRef: string;
  voice?: string;
  speed?: number;
  token: string;
}

export interface TTSConcurrencyPoolOptions {
  /** Max concurrent TTS requests (default 2) */
  maxConcurrent?: number;
  /** Called when a sentence TTS fails (sentence is skipped) */
  onError?: (text: string, error: Error) => void;
}

interface QueueItem {
  options: TTSRequestOptions;
  resolve: (audio: ArrayBuffer) => void;
  reject: (err: Error) => void;
}

export class TTSConcurrencyPool {
  private inFlight = 0;
  private queue: QueueItem[] = [];
  private abortControllers: AbortController[] = [];
  private readonly maxConcurrent: number;
  private readonly onError?: (text: string, error: Error) => void;

  constructor(options: TTSConcurrencyPoolOptions = {}) {
    this.maxConcurrent = options.maxConcurrent ?? 2;
    this.onError = options.onError;
  }

  /** Submit a sentence for TTS. Returns the audio ArrayBuffer. */
  async submit(options: TTSRequestOptions): Promise<ArrayBuffer> {
    if (this.inFlight < this.maxConcurrent) {
      return this.execute(options);
    }
    // Queue and wait for a slot
    return new Promise((resolve, reject) => {
      this.queue.push({ options, resolve, reject });
    });
  }

  /** Cancel all in-flight and queued requests */
  cancelAll(): void {
    for (const c of this.abortControllers) {
      c.abort();
    }
    this.abortControllers = [];
    for (const q of this.queue) {
      q.reject(new Error('cancelled'));
    }
    this.queue = [];
    this.inFlight = 0;
  }

  /** Number of in-flight requests */
  get active(): number {
    return this.inFlight;
  }

  /** Number of queued requests */
  get queued(): number {
    return this.queue.length;
  }

  // ── Internal ──────────────────────────────────────────────────────

  private async execute(options: TTSRequestOptions): Promise<ArrayBuffer> {
    this.inFlight++;
    const controller = new AbortController();
    this.abortControllers.push(controller);

    try {
      const params = new URLSearchParams({
        model_source: 'user_model',
        model_ref: options.modelRef,
      });

      const resp = await fetch(
        `/v1/model-registry/proxy/v1/audio/speech?${params}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${options.token}`,
          },
          body: JSON.stringify({
            model: 'auto',
            voice: options.voice || 'auto',
            input: options.text,
            response_format: 'wav',
            speed: options.speed || 1.0,
          }),
          signal: controller.signal,
        },
      );

      if (!resp.ok) {
        const detail = await resp.text().catch(() => resp.statusText);
        throw new Error(`TTS ${resp.status}: ${detail.slice(0, 200)}`);
      }

      return await resp.arrayBuffer();
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        this.onError?.(options.text, err as Error);
      }
      throw err;
    } finally {
      this.inFlight--;
      this.abortControllers = this.abortControllers.filter((c) => c !== controller);
      this.processNext(options);
    }
  }

  private processNext(templateOptions: TTSRequestOptions): void {
    if (this.queue.length === 0) return;
    const next = this.queue.shift()!;
    this.execute(next.options)
      .then(next.resolve)
      .catch(next.reject);
  }
}
