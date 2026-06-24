import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { BookPlus, GitBranch } from 'lucide-react';
import { useLivingWorld } from '../hooks/useLivingWorld';
import { AddBookToWorldModal } from './AddBookToWorldModal';

// W5 (G1) — the world-workspace POPULATE call-to-actions. Two affordances that
// let a user grow the world without leaving the workspace (design §5.1):
//   • "Add a book"      → AddBookToWorldModal (attach existing / create new).
//   • "Create a what-if" → routes to the divergence wizard, seeded with a canon
//     Work. Source selection (decision ⑦): 0 canon → disabled, guide to add a
//     book; exactly 1 → straight to its studio; >1 → a canon picker, then route.
//
// We route INTO the canon Work's composition panel (where the existing
// DivergenceWizardButton lives) rather than re-hosting the 4-step wizard here —
// "routes to the divergence wizard" per the design.
interface Props {
  worldId: string | undefined;
}

export function WorldPopulateActions({ worldId }: Props) {
  const { t } = useTranslation('world');
  const navigate = useNavigate();
  const { tree, isLoading } = useLivingWorld(worldId);

  const [addOpen, setAddOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close the canon-source picker on an outside click (consistent with the
  // shared pickers). Synchronization effect — not a useEffect-for-events.
  useEffect(() => {
    if (!pickerOpen) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setPickerOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [pickerOpen]);

  // Canon trunks are the valid what-if sources (a derivative needs a canon
  // source — the C23 invariant).
  const canon = useMemo(() => tree.nodes.filter((n) => n.isCanon), [tree.nodes]);

  function gotoWork(bookId: string, workId: string) {
    navigate(`/books/${bookId}?work=${encodeURIComponent(workId)}`);
  }

  function createWhatIf() {
    if (canon.length === 0) return; // button is disabled in this state
    if (canon.length === 1) {
      gotoWork(canon[0].bookId, canon[0].id);
      return;
    }
    setPickerOpen((v) => !v); // >1 → choose the source
  }

  const whatIfDisabled = isLoading || canon.length === 0;

  return (
    <div ref={rootRef} className="relative flex flex-wrap items-center gap-2" data-testid="world-populate-actions">
      <button
        type="button"
        data-testid="world-add-book"
        onClick={() => setAddOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-md border border-primary/40 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10"
      >
        <BookPlus className="h-3.5 w-3.5" />
        {t('populate.addBook', { defaultValue: 'Add a book' })}
      </button>

      <button
        type="button"
        data-testid="world-create-whatif"
        onClick={createWhatIf}
        disabled={whatIfDisabled}
        title={
          canon.length === 0
            ? t('populate.whatIfNeedsCanon', { defaultValue: 'Add a book with a canon work first — a what-if branches from canon.' })
            : t('populate.whatIfHint', { defaultValue: 'Branch a what-if from a canon work' })
        }
        className="inline-flex items-center gap-1.5 rounded-md border border-purple-300 px-3 py-1.5 text-xs font-medium text-purple-700 hover:bg-purple-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-purple-700 dark:text-purple-300 dark:hover:bg-purple-950/30"
      >
        <GitBranch className="h-3.5 w-3.5" />
        {t('populate.createWhatIf', { defaultValue: 'Create a what-if' })}
      </button>

      {/* >1 canon → choose the source Work to branch from. */}
      {pickerOpen && canon.length > 1 && (
        <ul
          role="listbox"
          data-testid="world-whatif-picker"
          className="absolute top-full left-0 z-20 mt-1 max-h-56 w-64 overflow-y-auto rounded-md border bg-card shadow-lg"
        >
          <li className="px-3 py-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            {t('populate.pickCanon', { defaultValue: 'Branch from…' })}
          </li>
          {canon.map((n) => (
            <li key={n.id} role="option" aria-selected={false}>
              <button
                type="button"
                onClick={() => { setPickerOpen(false); gotoWork(n.bookId, n.id); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-card-foreground/[0.04]"
              >
                <GitBranch className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="flex-1 truncate">{n.bookTitle}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <AddBookToWorldModal open={addOpen} onOpenChange={setAddOpen} worldId={worldId} />
    </div>
  );
}
