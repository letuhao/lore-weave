// LanguageTool API client
// Docs: https://languagetool.org/http-api/

export interface GrammarMatch {
  message: string;
  offset: number;
  length: number;
  replacements: string[];
  rule: { id: string; description: string };
}

interface LTMatch {
  message: string;
  offset: number;
  length: number;
  replacements: Array<{ value: string }>;
  rule: { id: string; description: string };
}

// ── Graceful-degrade circuit breaker ────────────────────────────────────────
// Grammar is best-effort and optional: the LanguageTool service may simply not
// be running (it's not a release blocker). Without a breaker, every paragraph
// blur / debounce fires another request to the dead service, spamming the
// browser console with failed-request logs. After one failure we "open" the
// breaker for a cooldown window — `checkGrammar` then short-circuits to `[]`
// without hitting the network. A later success auto-closes it (self-healing).
const BREAKER_COOLDOWN_MS = 60_000;
let breakerOpenUntil = 0;

/** True when LanguageTool is presumed reachable (breaker closed). For UI/tests. */
export function grammarServiceAvailable(): boolean {
  return Date.now() >= breakerOpenUntil;
}

/** Test-only: reset the circuit breaker between cases. No-op in normal use. */
export function __resetGrammarBreaker(): void {
  breakerOpenUntil = 0;
}

/**
 * Check text for grammar/spelling issues via LanguageTool.
 * Returns empty array on any error (grammar check is best-effort).
 * When the service has recently failed, short-circuits without a request
 * (see the circuit breaker above) so a missing LT service degrades quietly.
 */
export async function checkGrammar(
  text: string,
  language = 'auto',
): Promise<GrammarMatch[]> {
  if (!text.trim()) return [];
  // Breaker open → skip the request entirely (no console-500 spam).
  if (Date.now() < breakerOpenUntil) return [];
  const params = new URLSearchParams({
    text,
    language,
    enabledOnly: 'false',
  });
  try {
    const res = await fetch('/languagetool/v2/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: params.toString(),
    });
    if (!res.ok) {
      // 5xx (or a proxy gateway error) means the service is unhealthy → back
      // off. A 4xx is a problem with this specific request (e.g. text too
      // long) — return empty but keep the breaker closed so other paragraphs
      // still get checked.
      if (res.status >= 500) breakerOpenUntil = Date.now() + BREAKER_COOLDOWN_MS;
      return [];
    }
    const data = (await res.json()) as { matches: LTMatch[] };
    breakerOpenUntil = 0; // success → close the breaker
    return data.matches.map((m) => ({
      message: m.message,
      offset: m.offset,
      length: m.length,
      replacements: m.replacements.slice(0, 5).map((r) => r.value),
      rule: { id: m.rule.id, description: m.rule.description },
    }));
  } catch {
    // Network error / service down → back off so we stop hammering it.
    breakerOpenUntil = Date.now() + BREAKER_COOLDOWN_MS;
    return [];
  }
}

// ── Decoration helpers ──────────────────────────────────────────────────────

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeAttr(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/**
 * Wrap grammar matches in <span class="grammar-issue"> with title tooltip.
 * Returns HTML string safe for innerHTML.
 */
export function decorateText(text: string, matches: GrammarMatch[]): string {
  if (!matches.length) return escapeHtml(text);

  // Filter overlapping matches — keep the first by offset
  const sorted = [...matches].sort((a, b) => a.offset - b.offset);
  const filtered: GrammarMatch[] = [];
  let lastEnd = 0;
  for (const m of sorted) {
    if (m.offset >= lastEnd) {
      filtered.push(m);
      lastEnd = m.offset + m.length;
    }
  }

  let html = '';
  let pos = 0;
  for (const m of filtered) {
    if (m.offset > pos) html += escapeHtml(text.slice(pos, m.offset));
    const matched = text.slice(m.offset, m.offset + m.length);
    const tip =
      m.message +
      (m.replacements.length ? ` \u2192 ${m.replacements.join(', ')}` : '');
    html += `<span class="grammar-issue" title="${escapeAttr(tip)}">${escapeHtml(matched)}</span>`;
    pos = m.offset + m.length;
  }
  if (pos < text.length) html += escapeHtml(text.slice(pos));
  return html;
}

/** Plain-text safe for innerHTML (no decorations). */
export { escapeHtml };

// ── Paragraph position tracking (for source-mode grammar) ───────────────────

export interface ParagraphInfo {
  index: number;
  start: number;
  end: number;
  text: string;
}

/**
 * Split text into paragraphs by double newlines, tracking byte offsets.
 * Returns array of { index, start, end, text }.
 */
export function splitParagraphsWithPositions(text: string): ParagraphInfo[] {
  const result: ParagraphInfo[] = [];
  const re = /\n\n+/g;
  let lastEnd = 0;
  let idx = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(text)) !== null) {
    const paraText = text.slice(lastEnd, match.index);
    if (paraText.trim()) {
      result.push({ index: idx++, start: lastEnd, end: match.index, text: paraText });
    }
    lastEnd = match.index + match[0].length;
  }
  // Last paragraph
  if (lastEnd < text.length) {
    const paraText = text.slice(lastEnd);
    if (paraText.trim()) {
      result.push({ index: idx, start: lastEnd, end: text.length, text: paraText });
    }
  }
  if (result.length === 0 && text.trim()) {
    result.push({ index: 0, start: 0, end: text.length, text });
  }
  return result;
}

/**
 * Find the paragraph index containing `cursor`, plus indices of
 * the paragraph before and after (clamped to bounds).
 * Returns up to 3 indices to check.
 */
export function getParagraphsAroundCursor(
  paragraphs: ParagraphInfo[],
  cursor: number,
): number[] {
  if (paragraphs.length === 0) return [];

  // Find the paragraph containing cursor
  let hit = 0;
  for (let i = 0; i < paragraphs.length; i++) {
    if (cursor <= paragraphs[i].end) {
      hit = i;
      break;
    }
    hit = i; // default to last if cursor is past all paragraphs
  }

  const indices = new Set<number>();
  if (hit > 0) indices.add(hit - 1);
  indices.add(hit);
  if (hit < paragraphs.length - 1) indices.add(hit + 1);
  return Array.from(indices);
}
