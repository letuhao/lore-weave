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

/**
 * Check text for grammar/spelling issues via LanguageTool.
 * Returns empty array on any error (grammar check is best-effort).
 */
export async function checkGrammar(
  text: string,
  language = 'auto',
): Promise<GrammarMatch[]> {
  if (!text.trim()) return [];
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
    if (!res.ok) return [];
    const data = (await res.json()) as { matches: LTMatch[] };
    return data.matches.map((m) => ({
      message: m.message,
      offset: m.offset,
      length: m.length,
      replacements: m.replacements.slice(0, 5).map((r) => r.value),
      rule: { id: m.rule.id, description: m.rule.description },
    }));
  } catch {
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
