// The author's marked problems, with the actions that CLOSE them (atom-edit Phase D / F3).
//
// Phase D gave the author a way to MARK a passage and see it highlighted, and nothing else: every
// close (resolve / dismiss / reopen) and the removal lived on the API and the co-writer's MCP tool
// only. The agent could close the author's own annotation; the author could not. This is that
// missing door.
//
// Render-only — the mutations live in `useErrorBlockActions`.
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import type { ErrorBlock } from '../errorBlocks';
import type { ErrorBlockActions } from '../hooks/useErrorBlockActions';

const KIND_TONE: Record<string, string> = {
  continuity: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  fact: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200',
  logic: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200',
};

function Row({ block, actions, drifted, t }: {
  block: ErrorBlock; actions: ErrorBlockActions; drifted: boolean;
  t: (k: string, o?: { defaultValue?: string }) => string;
}) {
  const remove = () => actions.remove(block.id, (id) => {
    toast.success(t('errorBlocks.removed', { defaultValue: 'Mark removed.' }), {
      // The list read filters archived rows and there is no archive browser, so this toast is the
      // only way back — the same reachability rule the canon-rule and scene-link undos follow.
      action: {
        label: t('errorBlocks.undo', { defaultValue: 'Undo' }),
        onClick: () => actions.restore(id, () =>
          toast.error(t('errorBlocks.undoFailed', { defaultValue: 'Could not restore the mark.' }))),
      },
    });
  });

  const closed = block.status === 'resolved' || block.status === 'dismissed';
  return (
    <li data-testid="error-block-row" data-status={block.status} className="rounded border border-neutral-200 p-1.5 text-[11px] dark:border-neutral-700">
      <div className="flex items-center gap-1">
        <span className={`rounded px-1 py-0.5 text-[10px] ${KIND_TONE[block.kind] ?? 'bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300'}`}>
          {block.kind}
        </span>
        {/* Drift is SURFACED, never hidden: the prose it pointed at changed, so it is no longer
            drawn in the document and this row is the only place it still exists. */}
        {drifted && (
          <span data-testid="error-block-drifted" className="rounded bg-neutral-200 px-1 py-0.5 text-[10px] text-neutral-700 dark:bg-neutral-700 dark:text-neutral-200">
            {t('errorBlocks.drifted', { defaultValue: 'text changed' })}
          </span>
        )}
        <span className="ml-auto flex items-center gap-1">
          {closed ? (
            <button type="button" data-testid={`error-block-reopen-${block.id}`} disabled={actions.busy}
              className="rounded border px-1 py-0.5 hover:bg-neutral-100 disabled:opacity-50 dark:hover:bg-neutral-800"
              onClick={() => actions.reopen(block.id)}>
              {t('errorBlocks.reopen', { defaultValue: 'Reopen' })}
            </button>
          ) : (
            <>
              <button type="button" data-testid={`error-block-resolve-${block.id}`} disabled={actions.busy}
                className="rounded border px-1 py-0.5 hover:bg-neutral-100 disabled:opacity-50 dark:hover:bg-neutral-800"
                onClick={() => actions.resolve(block.id)}>
                {t('errorBlocks.resolve', { defaultValue: 'Fixed' })}
              </button>
              <button type="button" data-testid={`error-block-dismiss-${block.id}`} disabled={actions.busy}
                className="rounded border px-1 py-0.5 hover:bg-neutral-100 disabled:opacity-50 dark:hover:bg-neutral-800"
                onClick={() => actions.dismiss(block.id)}>
                {t('errorBlocks.dismiss', { defaultValue: 'Leave it' })}
              </button>
            </>
          )}
          <button type="button" data-testid={`error-block-remove-${block.id}`} disabled={actions.busy}
            aria-label={t('errorBlocks.remove', { defaultValue: 'Remove mark' })}
            className="rounded px-1 text-neutral-500 hover:text-destructive disabled:opacity-50"
            onClick={remove}>×</button>
        </span>
      </div>
      <p className="mt-1 truncate italic text-neutral-500 dark:text-neutral-400" title={block.quote}>“{block.quote}”</p>
      <p className="text-neutral-700 dark:text-neutral-200">{block.note}</p>
    </li>
  );
}

export function ErrorBlockList({ blocks, driftedIds, actions }: {
  blocks: ErrorBlock[]; driftedIds: string[]; actions: ErrorBlockActions;
}) {
  const { t } = useTranslation('studio');
  if (blocks.length === 0) return null;   // no marks, no panel — this is the writer's manuscript
  const drifted = new Set(driftedIds);
  return (
    <div data-testid="error-block-list" className="max-h-40 shrink-0 overflow-auto border-t border-neutral-200 p-2 dark:border-neutral-700">
      <p className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">
        {t('errorBlocks.title', { defaultValue: 'Marked problems' })} ({blocks.length})
      </p>
      <ul className="space-y-1">
        {blocks.map((b) => (
          <Row key={b.id} block={b} actions={actions} drifted={drifted.has(b.id)} t={t} />
        ))}
      </ul>
    </div>
  );
}
