// Top bar (fixed) — book context + a command-palette affordance. Generate / Save / model
// controls arrive with the panels that need them (skeleton keeps this informational).
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, LayoutDashboard, Search, Settings } from 'lucide-react';

interface Props {
  bookId: string;
  bookTitle: string;
}

export function StudioTopBar({ bookId, bookTitle }: Props) {
  const { t } = useTranslation('studio');
  return (
    <div className="flex h-11 flex-shrink-0 items-center gap-2 border-b bg-card px-3">
      <Link
        to={`/books/${bookId}`}
        className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
        title={t('back', { defaultValue: 'Back to book' })}
      >
        <ArrowLeft className="h-4 w-4" />
      </Link>
      <div className="flex items-center gap-1.5 text-[13px]">
        <LayoutDashboard className="h-3.5 w-3.5 text-primary" />
        <span className="font-semibold">{t('title', { defaultValue: 'Writing Studio' })}</span>
        {bookTitle && (
          <>
            <span className="text-border">/</span>
            <span className="truncate text-muted-foreground">{bookTitle}</span>
          </>
        )}
      </div>

      <div className="flex-1" />

      {/* Command palette affordance — behaviour lands in a later component (#06). Disabled
          so it reads as "coming", never a dead button that looks live. */}
      <button
        type="button"
        disabled
        data-testid="studio-command-palette"
        title={t('palette.soon', { defaultValue: 'Command palette — coming soon' })}
        className="flex h-7 w-[280px] max-w-[32vw] cursor-default items-center gap-2 rounded-md border bg-background/60 px-2.5 text-xs text-muted-foreground/70"
      >
        <Search className="h-3 w-3" />
        <span className="truncate">{t('palette.placeholder', { defaultValue: 'Go to chapter, scene, tool…' })}</span>
        <kbd className="ml-auto rounded border border-border px-1.5 py-px font-mono text-[10px]">⌘P</kbd>
      </button>

      <Link
        to={`/books/${bookId}/settings`}
        className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
        title={t('settings', { defaultValue: 'Book settings' })}
      >
        <Settings className="h-4 w-4" />
      </Link>
    </div>
  );
}
