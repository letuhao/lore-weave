// Client-side parsing/sorting for the chapter-import review screen.
//
// The OS-provided FileList order is not numeric (and a folder pick via
// webkitdirectory is unordered), so we natural-sort by the leading numeric
// prefix of the filename (e.g. 0001-八百年后.txt → 1). Titles are previewed from
// the content's CJK chapter header (第N章 …) — the backend re-derives/validates,
// and any inline edit here is sent as an override.

export interface ParsedChapter {
  /** stable client id (filename + index) for React keys + selection */
  id: string;
  file: File;
  filename: string;
  /** previewed/edited title sent as an override to the bulk endpoint */
  title: string;
  /** byte size of the file */
  size: number;
  /** full text content (read once, kept in memory for the import) */
  content: string;
  /** excluded from import when false */
  included: boolean;
}

/** Leading integer of a filename ("0012-foo.txt" → 12), or null if none. */
function leadingNumber(name: string): number | null {
  const m = name.match(/^\D*(\d+)/);
  return m ? parseInt(m[1], 10) : null;
}

/** Numeric-aware filename comparator: numeric prefix first, then locale string. */
export function naturalCompare(a: string, b: string): number {
  const na = leadingNumber(a);
  const nb = leadingNumber(b);
  if (na !== null && nb !== null && na !== nb) return na - nb;
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
}

const CJK_HEADER = /^\s*第\s*\d+\s*[章节回卷]\s*(.+?)\s*$/;

/** Preview a chapter title: CJK header in content → filename after first dash →
 *  filename (sans extension). Capped to 120 chars. */
export function parseChapterTitle(filename: string, content: string): string {
  const lines = content.split('\n', 6);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    const m = line.match(CJK_HEADER);
    if (m) return cap(m[1].trim());
    return cap(line); // first non-empty line, if not a header
  }
  const base = filename.replace(/\.[^.]+$/, '');
  const dash = base.indexOf('-');
  return cap(dash >= 0 ? base.slice(dash + 1) : base);
}

function cap(s: string): string {
  return s.length > 120 ? s.slice(0, 120) : s;
}

const ALLOWED = ['.txt'];

/** Keep only importable plain-text files (folder picks include everything). */
export function filterTxtFiles(files: File[]): File[] {
  return files.filter((f) => ALLOWED.some((ext) => f.name.toLowerCase().endsWith(ext)));
}

/**
 * Read + parse the selected .txt files into sorted ParsedChapter rows, reporting
 * progress (0..1) as files are read. Reads sequentially to keep memory bounded
 * and progress monotonic for very large folders (4000+).
 */
export async function readChapters(
  files: File[],
  onProgress?: (done: number, total: number) => void,
): Promise<ParsedChapter[]> {
  const sorted = [...files].sort((a, b) => naturalCompare(a.name, b.name));
  const out: ParsedChapter[] = [];
  for (let i = 0; i < sorted.length; i++) {
    const file = sorted[i];
    const content = await file.text();
    out.push({
      id: `${file.name}#${i}`,
      file,
      filename: file.name,
      title: parseChapterTitle(file.name, content),
      size: file.size,
      content,
      included: true,
    });
    onProgress?.(i + 1, sorted.length);
  }
  return out;
}
