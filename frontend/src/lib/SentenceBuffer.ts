/**
 * SentenceBuffer — accumulates LLM token deltas and emits complete sentences
 * for the streaming TTS pipeline.
 *
 * Design ref: REALTIME_VOICE_PIPELINE.md §5
 */

export type SentenceCallback = (sentence: string) => void;

export interface SentenceBufferOptions {
  /** Minimum chars before a boundary triggers emission (default 10) */
  minLength?: number;
  /** Force-split at this length if no boundary found (default 300) */
  maxLength?: number;
  /** Wait this long before flushing short sentences (default 500ms) */
  shortTimeoutMs?: number;
}

// Sentence-ending punctuation + optional trailing quotes/parens
// Note: \n is NOT included — paragraph breaks handled separately (SB-01 fix)
const BOUNDARY_RE = /([.!?。！？]["'」）)\s]*)/;

// Paragraph break — double newline or single newline followed by content
const PARAGRAPH_RE = /(\n\s*\n|\n(?=[A-Z\u4e00-\u9fff]))/;

// Common abbreviations that end with "." but aren't sentence ends
const ABBREVIATIONS = new Set([
  'Mr', 'Mrs', 'Ms', 'Dr', 'Prof', 'Sr', 'Jr', 'St', 'Ave', 'Blvd',
  'vs', 'etc', 'i.e', 'e.g', 'a.m', 'p.m',
]);

export class SentenceBuffer {
  private buffer = '';
  private onSentence: SentenceCallback;
  private shortTimer: ReturnType<typeof setTimeout> | null = null;
  private streamComplete = false;
  private cancelled = false; // SB-03: prevent reuse after cancel

  private readonly minLength: number;
  private readonly maxLength: number;
  private readonly shortTimeoutMs: number;

  constructor(onSentence: SentenceCallback, options: SentenceBufferOptions = {}) {
    this.onSentence = onSentence;
    this.minLength = options.minLength ?? 10;
    this.maxLength = options.maxLength ?? 300;
    this.shortTimeoutMs = options.shortTimeoutMs ?? 500;
  }

  /** Add a token delta from the LLM stream */
  addToken(token: string): void {
    if (this.cancelled) return; // SB-03
    this.buffer += token;
    this.clearShortTimer();
    this.tryFlush();
  }

  /** Mark the LLM stream as complete — flush everything remaining */
  markStreamComplete(): void {
    this.streamComplete = true;
    this.clearShortTimer();
    this.tryFlush();
    this.flush();
  }

  /** Cancel everything — used on barge-in or deactivation */
  cancel(): void {
    this.clearShortTimer();
    this.buffer = '';
    this.streamComplete = false;
    this.cancelled = true; // SB-03
  }

  /** Reset for reuse (after cancel, for a new stream) */
  reset(): void {
    this.cancel();
    this.cancelled = false;
    this.streamComplete = false; // SB-05
  }

  /** Force-flush whatever is in the buffer */
  flush(): void {
    this.clearShortTimer();
    const remaining = this.buffer.trim();
    if (remaining.length > 0) {
      this.onSentence(remaining);
    }
    this.buffer = '';
    this.streamComplete = false; // SB-05
  }

  /** Current buffer contents (for debugging/display) */
  get pending(): string {
    return this.buffer;
  }

  // ── Internal ──────────────────────────────────────────────────────

  private tryFlush(): void {
    // SB-04 + SB-06: use while-loop instead of recursion
    while (this.buffer.length > 0) {
      // Force-split very long text without boundaries
      if (this.buffer.length > this.maxLength) {
        const splitAt = this.findSplitPoint(this.buffer, this.maxLength);
        const chunk = this.buffer.slice(0, splitAt).trim();
        this.buffer = this.buffer.slice(splitAt).trimStart();
        if (chunk) this.onSentence(chunk);
        continue;
      }

      // Check for paragraph break first (SB-01: handle \n separately)
      const paraMatch = this.buffer.match(PARAGRAPH_RE);
      if (paraMatch && paraMatch.index !== undefined) {
        const sentence = this.buffer.slice(0, paraMatch.index).trim();
        this.buffer = this.buffer.slice(paraMatch.index + paraMatch[0].length);
        if (sentence.length > 0) {
          this.onSentence(sentence);
          continue;
        }
      }

      // Scan for sentence boundary (skip abbreviations)
      const emitted = this.tryBoundaryFlush();
      if (!emitted) break;
    }
  }

  /** Try to find and emit at a sentence boundary. Returns true if emitted. */
  private tryBoundaryFlush(): boolean {
    let searchFrom = 0;
    while (searchFrom < this.buffer.length) {
      const sub = this.buffer.slice(searchFrom);
      const match = sub.match(BOUNDARY_RE);
      if (!match || match.index === undefined) return false;

      const boundaryEnd = searchFrom + match.index + match[0].length;
      const sentence = this.buffer.slice(0, boundaryEnd).trim();

      // SB-02: check abbreviation on trimmed sentence
      if (this.isAbbreviation(sentence)) {
        searchFrom = boundaryEnd;
        continue;
      }

      const rest = this.buffer.slice(boundaryEnd);

      if (sentence.length >= this.minLength || this.streamComplete) {
        this.buffer = rest;
        this.onSentence(sentence);
        return true;
      } else {
        this.startShortTimer();
        return false;
      }
    }
    return false;
  }

  /** Find a natural split point near maxLen (comma > semicolon > space > hard cut) */
  private findSplitPoint(text: string, maxLen: number): number {
    const halfMax = Math.floor(maxLen * 0.5);
    for (const char of [',', ';', ':', ' ']) {
      const idx = text.lastIndexOf(char, maxLen);
      if (idx > halfMax) return idx + 1;
    }
    return maxLen;
  }

  /** Check if the "." at the end is an abbreviation, not a sentence end */
  private isAbbreviation(sentence: string): boolean {
    const trimmed = sentence.trimEnd(); // SB-02: use trimmed version
    if (!trimmed.endsWith('.')) return false;
    const words = trimmed.split(/\s+/);
    const lastWord = words[words.length - 1]?.replace(/\.$/, '');
    if (!lastWord) return false;
    return ABBREVIATIONS.has(lastWord);
  }

  private startShortTimer(): void {
    if (this.shortTimer || this.cancelled) return; // SB-03
    this.shortTimer = setTimeout(() => {
      this.shortTimer = null;
      if (this.cancelled) return; // SB-03
      const pending = this.buffer.trim();
      if (pending) {
        this.buffer = '';
        this.onSentence(pending);
      }
    }, this.shortTimeoutMs);
  }

  private clearShortTimer(): void {
    if (this.shortTimer) {
      clearTimeout(this.shortTimer);
      this.shortTimer = null;
    }
  }
}
