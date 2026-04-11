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
  /** Max concurrent TTS requests (default 2, min 1) */
  maxConcurrent?: number;
  /** Max queued requests before rejecting (default 20) */
  maxQueueDepth?: number;
  /** Called when a sentence TTS fails (sentence is skipped) */
  onError?: (text: string, error: Error) => void;
  /** Called when a sentence TTS completes (durationMs, audioSizeBytes) */
  onComplete?: (durationMs: number, audioSizeBytes: number) => void;
}

interface QueueItem {
  options: TTSRequestOptions;
  resolve: (audio: ArrayBuffer) => void;
  reject: (err: Error) => void;
}

export class TTSConcurrencyPool {
  private inFlight = 0;
  private queue: QueueItem[] = [];
  private abortControllers = new Set<AbortController>(); // CP-05: use Set for cleaner lifecycle
  private readonly maxConcurrent: number;
  private readonly maxQueueDepth: number;
  private readonly onError?: (text: string, error: Error) => void;
  private readonly onComplete?: (durationMs: number, audioSizeBytes: number) => void;

  constructor(options: TTSConcurrencyPoolOptions = {}) {
    this.maxConcurrent = Math.max(1, options.maxConcurrent ?? 2); // CP-08: clamp min 1
    this.maxQueueDepth = options.maxQueueDepth ?? 20; // CP-06: bounded queue
    this.onError = options.onError;
    this.onComplete = options.onComplete;
  }

  /** Submit a sentence for TTS. Returns the audio ArrayBuffer. */
  async submit(options: TTSRequestOptions): Promise<ArrayBuffer> {
    if (this.inFlight < this.maxConcurrent) {
      return this.execute(options);
    }
    // CP-06: reject if queue is full
    if (this.queue.length >= this.maxQueueDepth) {
      const err = new Error('TTS queue full');
      this.onError?.(options.text, err);
      throw err;
    }
    return new Promise((resolve, reject) => {
      this.queue.push({ options, resolve, reject });
    });
  }

  /** Cancel all in-flight and queued requests */
  cancelAll(): void {
    // Abort in-flight requests — let their finally blocks decrement inFlight naturally (CP-02)
    for (const c of this.abortControllers) {
      c.abort();
    }
    // Don't clear abortControllers here — finally blocks will remove them (CP-05)
    // Don't set inFlight = 0 — finally blocks will decrement naturally (CP-02)

    // Reject and clear queued items
    for (const q of this.queue) {
      this.onError?.(q.options.text, new Error('cancelled')); // CP-07: notify on cancel
      q.reject(new Error('cancelled'));
    }
    this.queue = [];
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
    this.abortControllers.add(controller);
    const ttsStart = performance.now();
    const textPreview = options.text.slice(0, 50) + (options.text.length > 50 ? '...' : '');
    console.log(`[TTS] Requesting: "${textPreview}" (voice: ${options.voice})`);

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

      const audio = await resp.arrayBuffer();
      const ttsDuration = performance.now() - ttsStart;
      const audioKB = (audio.byteLength / 1024).toFixed(1);
      console.log(`[TTS] Done in ${ttsDuration.toFixed(0)}ms — ${audioKB}KB audio for "${textPreview}"`);
      this.onComplete?.(ttsDuration, audio.byteLength);
      return audio;
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        this.onError?.(options.text, err as Error);
      }
      throw err;
    } finally {
      this.abortControllers.delete(controller); // CP-05: remove from Set
      this.inFlight--;
      // CP-01: processNext is called AFTER inFlight decrement.
      // This is safe because processNext calls execute which increments inFlight
      // before yielding. The gap between -- and ++ is synchronous (no await),
      // so submit() cannot observe the decremented value in between.
      this.processNext();
    }
  }

  // CP-04: no parameter — reads from queue directly
  private processNext(): void {
    if (this.queue.length === 0) return;
    if (this.inFlight >= this.maxConcurrent) return; // CP-01: guard against over-allocation
    const next = this.queue.shift()!;
    // execute increments inFlight synchronously before first await
    this.execute(next.options)
      .then(next.resolve)
      .catch(next.reject);
  }
}
