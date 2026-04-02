import { Sparkles } from 'lucide-react';

interface PromptDiffProps {
  oldPrompt: string;
  newPrompt: string;
  oldLabel?: string;
  newLabel?: string;
}

/**
 * Git-style line diff between two prompts.
 * Shows context lines (gray), deletions (red strikethrough), additions (green).
 */
export function PromptDiff({ oldPrompt, newPrompt, oldLabel = 'Previous', newLabel = 'Current' }: PromptDiffProps) {
  if (!oldPrompt && !newPrompt) return null;
  if (oldPrompt === newPrompt) {
    return (
      <div className="px-4 py-3">
        <p className="text-[10px] text-muted-foreground/50">Prompts are identical</p>
      </div>
    );
  }

  const diff = computeLineDiff(oldPrompt, newPrompt);

  return (
    <div className="border-t px-4 py-3">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold">
        <Sparkles className="h-3 w-3 text-info" />
        AI Prompt Diff ({oldLabel} → {newLabel})
      </div>
      <div className="rounded-md bg-secondary p-3 font-mono text-[11px] leading-relaxed">
        {diff.map((line, i) => (
          <div key={i} className="py-px">
            {line.type === 'context' && (
              <span className="text-muted-foreground">{line.text}</span>
            )}
            {line.type === 'del' && (
              <span className="text-destructive">
                -<span className="rounded bg-destructive/15 px-0.5 line-through">{line.text}</span>
              </span>
            )}
            {line.type === 'add' && (
              <span className="text-success">
                +<span className="rounded bg-success/10 px-0.5">{line.text}</span>
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

type DiffLine = { type: 'context' | 'del' | 'add'; text: string };

/** Simple line-by-line diff (no external library). Good enough for short prompts. */
function computeLineDiff(oldText: string, newText: string): DiffLine[] {
  const oldLines = oldText.split('\n');
  const newLines = newText.split('\n');
  const result: DiffLine[] = [];

  // Use a simple LCS-based approach for short texts
  const maxLen = Math.max(oldLines.length, newLines.length);

  if (maxLen <= 50) {
    // For short texts, use naive O(n*m) LCS
    const lcs = computeLCS(oldLines, newLines);
    let oi = 0, ni = 0, li = 0;

    while (oi < oldLines.length || ni < newLines.length) {
      if (li < lcs.length && oi < oldLines.length && oldLines[oi] === lcs[li]) {
        if (ni < newLines.length && newLines[ni] === lcs[li]) {
          result.push({ type: 'context', text: ` ${lcs[li]}` });
          oi++; ni++; li++;
        } else if (ni < newLines.length) {
          result.push({ type: 'add', text: newLines[ni] });
          ni++;
        }
      } else if (oi < oldLines.length) {
        // Check if this old line appears later as a context match
        if (li < lcs.length && oldLines[oi] !== lcs[li]) {
          result.push({ type: 'del', text: oldLines[oi] });
          oi++;
        } else if (li >= lcs.length) {
          result.push({ type: 'del', text: oldLines[oi] });
          oi++;
        }
      } else if (ni < newLines.length) {
        result.push({ type: 'add', text: newLines[ni] });
        ni++;
      }
    }
  } else {
    // Fallback: show all old as deletions, all new as additions
    for (const line of oldLines) result.push({ type: 'del', text: line });
    for (const line of newLines) result.push({ type: 'add', text: line });
  }

  return result;
}

/** Compute Longest Common Subsequence of two string arrays */
function computeLCS(a: string[], b: string[]): string[] {
  const m = a.length, n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }

  const result: string[] = [];
  let i = m, j = n;
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) {
      result.unshift(a[i - 1]);
      i--; j--;
    } else if (dp[i - 1][j] > dp[i][j - 1]) {
      i--;
    } else {
      j--;
    }
  }
  return result;
}
