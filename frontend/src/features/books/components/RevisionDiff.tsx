// Pure diff renderer (view). Renders the server line-diff either inline
// (git-style unified) or side-by-side with word-level highlights. No data
// fetching, no state — receives the diff + mode and renders.
import { useMemo } from 'react';
import type { DiffLine } from '../types';
import { alignSideBySide, type WordToken } from '../lib/wordDiff';
import type { CompareViewMode } from '../hooks/useRevisionCompare';

type Props = {
  diff: DiffLine[];
  mode: CompareViewMode;
};

export function RevisionDiff({ diff, mode }: Props) {
  if (mode === 'inline') return <InlineDiff diff={diff} />;
  return <SideBySideDiff diff={diff} />;
}

function InlineDiff({ diff }: { diff: DiffLine[] }) {
  return (
    <div data-testid="diff-inline" className="overflow-x-auto rounded-md border font-mono text-xs">
      {diff.map((l, idx) => {
        const cls =
          l.op === 'insert'
            ? 'bg-success/10 text-success'
            : l.op === 'delete'
              ? 'bg-destructive/10 text-destructive'
              : 'text-muted-foreground';
        const sign = l.op === 'insert' ? '+' : l.op === 'delete' ? '−' : ' ';
        return (
          <div key={idx} data-op={l.op} className={`flex whitespace-pre-wrap px-2 py-0.5 ${cls}`}>
            <span className="mr-2 select-none opacity-60">{sign}</span>
            <span className="flex-1 break-words">{l.text || ' '}</span>
          </div>
        );
      })}
    </div>
  );
}

function SideBySideDiff({ diff }: { diff: DiffLine[] }) {
  const rows = useMemo(() => alignSideBySide(diff), [diff]);
  return (
    <div data-testid="diff-sxs" className="grid grid-cols-2 gap-px overflow-x-auto rounded-md border bg-border font-mono text-xs">
      {rows.map((row, idx) => (
        <Row key={idx} row={row} />
      ))}
    </div>
  );
}

function Row({ row }: { row: ReturnType<typeof alignSideBySide>[number] }) {
  const leftTint =
    row.type === 'delete' || row.type === 'change' ? 'bg-destructive/10' : 'bg-background';
  const rightTint =
    row.type === 'insert' || row.type === 'change' ? 'bg-success/10' : 'bg-background';
  return (
    <>
      <div data-side="left" data-type={row.type} className={`whitespace-pre-wrap break-words px-2 py-0.5 ${leftTint}`}>
        {row.left ? <Cell text={row.left.text} words={row.left.words} kind="del" /> : ' '}
      </div>
      <div data-side="right" data-type={row.type} className={`whitespace-pre-wrap break-words px-2 py-0.5 ${rightTint}`}>
        {row.right ? <Cell text={row.right.text} words={row.right.words} kind="ins" /> : ' '}
      </div>
    </>
  );
}

function Cell({ text, words, kind }: { text: string; words?: WordToken[]; kind: 'del' | 'ins' }) {
  if (!words) return <>{text || ' '}</>;
  const hl = kind === 'ins' ? 'bg-success/30' : 'bg-destructive/30';
  return (
    <>
      {words.map((tok, i) =>
        tok.changed ? (
          <span key={i} data-changed="true" className={`rounded-sm ${hl}`}>
            {tok.text}
          </span>
        ) : (
          <span key={i}>{tok.text}</span>
        ),
      )}
    </>
  );
}
