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
const BOUNDARY_RE = /([.!?。！？\n]["'」）)\s]*)/;

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
    this.buffer += token;
    this.clearShortTimer();
    this.tryFlush();
  }

  /** Mark the LLM stream as complete — flush everything remaining */
  markStreamComplete(): void {
    this.streamComplete = true;
    this.clearShortTimer();
    // Try boundary-based flush first (streamComplete bypasses minLength)
    this.tryFlush();
    // Then flush any remaining text that has no boundary
    this.flush();
  }

  /** Cancel everything — used on barge-in or deactivation */
  cancel(): void {
    this.clearShortTimer();
    this.buffer = '';
    this.streamComplete = false;
  }

  /** Force-flush whatever is in the buffer */
  flush(): void {
    this.clearShortTimer();
    const remaining = this.buffer.trim();
    if (remaining.length > 0) {
      this.onSentence(remaining);
    }
    this.buffer = '';
  }

  /** Current buffer contents (for debugging/display) */
  get pending(): string {
    return this.buffer;
  }

  // ── Internal ──────────────────────────────────────────────────────

  private tryFlush(): void {
    // Force-split very long text without boundaries
    if (this.buffer.length > this.maxLength) {
      this.forceSplit();
      return;
    }

    // Scan for the first real sentence boundary (skip abbreviations)
    let searchFrom = 0;
    while (searchFrom < this.buffer.length) {
      const sub = this.buffer.slice(searchFrom);
      const match = sub.match(BOUNDARY_RE);
      if (!match || match.index === undefined) return; // No boundary found

      const boundaryEnd = searchFrom + match.index + match[0].length;
      const sentence = this.buffer.slice(0, boundaryEnd).trim();

      // Check for false boundary (abbreviation like "Dr." "Mr.")
      if (this.isAbbreviation(sentence)) {
        // Skip past this boundary and keep looking
        searchFrom = boundaryEnd;
        continue;
      }

      const rest = this.buffer.slice(boundaryEnd);

      // Check minimum length
      if (sentence.length >= this.minLength || this.streamComplete) {
        this.buffer = rest;
        this.onSentence(sentence);
        // Recursively check if rest has more boundaries
        if (this.buffer.length > 0) {
          this.tryFlush();
        }
      } else {
        // Short sentence — wait for more tokens or timeout
        this.startShortTimer();
      }
      return;
    }
  }

  private forceSplit(): void {
    const splitAt = this.findSplitPoint(this.buffer, this.maxLength);
    const chunk = this.buffer.slice(0, splitAt).trim();
    this.buffer = this.buffer.slice(splitAt).trimStart();
    if (chunk) {
      this.onSentence(chunk);
    }
    // Continue checking remainder
    if (this.buffer.length > this.maxLength) {
      this.forceSplit();
    }
  }

  /** Find a natural split point near maxLen (comma > space > hard cut) */
  private findSplitPoint(text: string, maxLen: number): number {
    const halfMax = Math.floor(maxLen * 0.5);

    // Prefer comma
    const commaIdx = text.lastIndexOf(',', maxLen);
    if (commaIdx > halfMax) return commaIdx + 1;

    // Prefer semicolon / colon
    const semiIdx = text.lastIndexOf(';', maxLen);
    if (semiIdx > halfMax) return semiIdx + 1;
    const colonIdx = text.lastIndexOf(':', maxLen);
    if (colonIdx > halfMax) return colonIdx + 1;

    // Fall back to space
    const spaceIdx = text.lastIndexOf(' ', maxLen);
    if (spaceIdx > halfMax) return spaceIdx + 1;

    // Hard cut
    return maxLen;
  }

  /** Check if the "." at the end is an abbreviation, not a sentence end */
  private isAbbreviation(sentence: string): boolean {
    if (!sentence.endsWith('.')) return false;
    // Extract the last word before the period
    const words = sentence.trimEnd().split(/\s+/);
    const lastWord = words[words.length - 1]?.replace(/\.$/, '');
    if (!lastWord) return false;
    return ABBREVIATIONS.has(lastWord);
  }

  private startShortTimer(): void {
    if (this.shortTimer) return; // Already waiting
    this.shortTimer = setTimeout(() => {
      this.shortTimer = null;
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
