import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { BookPicker } from '@/components/shared/BookPicker';
import { FormDialog } from '@/components/shared/FormDialog';
import { useAddBookToWorld } from '../hooks/useAddBookToWorld';

// W5 (G1) — bring a book into the world. Two modes in one modal (design §5.1):
//   • Attach existing — pick a standalone book by title (reuses BookPicker) and
//     attach it.
//   • Create new — make a new book, then attach it (two-step, no orphan loss).
// Both panels stay mounted (CSS-hidden, not unmounted) so switching modes never
// drops the BookPicker's loaded list (FE rule: no conditional unmount).
interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  worldId: string | undefined;
}

export function AddBookToWorldModal({ open, onOpenChange, worldId }: Props) {
  const { t } = useTranslation('world');
  const { attach, createAndAttach, isPending, error } = useAddBookToWorld(worldId);

  const [mode, setMode] = useState<'attach' | 'create'>('attach');
  const [bookId, setBookId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');

  function close() {
    onOpenChange(false);
    // Reset on close so a reopen starts clean.
    setBookId(null);
    setTitle('');
    setDescription('');
    setMode('attach');
  }

  async function submit() {
    try {
      if (mode === 'attach') {
        if (!bookId) return;
        await attach(bookId);
      } else {
        if (!title.trim()) return;
        await createAndAttach({ title: title.trim(), description: description.trim() || undefined });
      }
      close();
    } catch {
      /* error surfaces via the hook's `error`; keep the modal open to retry */
    }
  }

  const canSubmit = mode === 'attach' ? !!bookId : !!title.trim();

  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => (o ? onOpenChange(true) : close())}
      title={t('populate.addBookTitle', { defaultValue: 'Add a book to this world' })}
      description={t('populate.addBookDesc', {
        defaultValue: 'Attach an existing book or create a new one — it joins the world’s timeline and graph.',
      })}
      footer={
        <>
          <button
            type="button"
            onClick={close}
            className="rounded-md border px-3 py-1.5 text-sm text-muted-foreground hover:bg-secondary"
          >
            {t('populate.cancel', { defaultValue: 'Cancel' })}
          </button>
          <button
            type="button"
            data-testid="add-book-submit"
            onClick={submit}
            disabled={!canSubmit || isPending}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {isPending
              ? t('populate.adding', { defaultValue: 'Adding…' })
              : mode === 'attach'
                ? t('populate.attach', { defaultValue: 'Attach book' })
                : t('populate.createAttach', { defaultValue: 'Create & add' })}
          </button>
        </>
      }
    >
      {/* Mode toggle. */}
      <div className="mb-4 inline-flex rounded-md border p-0.5 text-xs" role="tablist">
        {(['attach', 'create'] as const).map((m) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            data-testid={`add-book-mode-${m}`}
            onClick={() => setMode(m)}
            className={cn(
              'rounded px-3 py-1 font-medium transition-colors',
              mode === m ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {m === 'attach'
              ? t('populate.tabAttach', { defaultValue: 'Attach existing' })
              : t('populate.tabCreate', { defaultValue: 'Create new' })}
          </button>
        ))}
      </div>

      {/* Attach existing — BookPicker stays mounted (CSS-hidden when inactive). */}
      <div className={cn('space-y-1', mode === 'attach' ? '' : 'hidden')} data-testid="add-book-attach-panel">
        <label className="block text-xs font-medium text-muted-foreground">
          {t('populate.pickBook', { defaultValue: 'Book' })}
        </label>
        <BookPicker value={bookId} onChange={setBookId} />
      </div>

      {/* Create new. */}
      <div className={cn('space-y-3', mode === 'create' ? '' : 'hidden')} data-testid="add-book-create-panel">
        <div className="space-y-1">
          <label className="block text-xs font-medium text-muted-foreground" htmlFor="add-book-title">
            {t('populate.bookTitle', { defaultValue: 'Title' })}
          </label>
          <input
            id="add-book-title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t('populate.bookTitlePlaceholder', { defaultValue: 'New book title…' })}
            className="w-full rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring"
          />
        </div>
        <div className="space-y-1">
          <label className="block text-xs font-medium text-muted-foreground" htmlFor="add-book-desc">
            {t('populate.bookDesc', { defaultValue: 'Description (optional)' })}
          </label>
          <textarea
            id="add-book-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="w-full resize-y rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring"
          />
        </div>
      </div>

      {error && (
        <p className="mt-3 text-xs text-destructive" role="alert" data-testid="add-book-error">
          {t('populate.addFailed', { defaultValue: 'Couldn’t add the book: {{error}}', error: error.message })}
        </p>
      )}
    </FormDialog>
  );
}
