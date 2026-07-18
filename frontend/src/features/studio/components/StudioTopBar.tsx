// Top bar (fixed) — book context + a command-palette affordance. Generate / Save / model
// controls arrive with the panels that need them (skeleton keeps this informational).
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, LayoutDashboard, Search, Settings } from 'lucide-react';
import { StudioLayoutButton } from './StudioLayoutButton';

interface Props {
  bookId: string;
  bookTitle: string;
  /** Opens Quick Open (#06a). The affordance shows locations only — tools live in ⌘⇧P. */
  onOpenQuickOpen?: () => void;
}

export function StudioTopBar({ bookId, bookTitle, onOpenQuickOpen }: Props) {
  const { t } = useTranslation('studio');
  return (
    <div className="flex h-11 flex-shrink-0 items-center gap-2 border-b bg-card px-3">
      <Link
        to="/books"
        className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
        title={t('back', { defaultValue: 'Back to books' })}
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

      {/* Quick Open affordance (#06a) — locations only (chapters/scenes/arcs); tools live in ⌘⇧P. */}
      <button
        type="button"
        onClick={onOpenQuickOpen}
        data-testid="studio-command-palette"
        title={t('palette.quickOpenTitle', { defaultValue: 'Go to chapter, scene, arc' })}
        className="flex h-7 w-[280px] max-w-[32vw] items-center gap-2 rounded-md border bg-background/60 px-2.5 text-xs text-muted-foreground/70 hover:bg-secondary/50 hover:text-muted-foreground"
      >
        <Search className="h-3 w-3" />
        <span className="truncate">{t('palette.placeholder', { defaultValue: 'Go to chapter, scene, arc…' })}</span>
        <kbd className="ml-auto rounded border border-border px-1.5 py-px font-mono text-[10px]">⌘P</kbd>
      </button>

      {/* Panel-layout preset menu — arranges the open dock panels into N columns / a grid
          (ultrawide-friendly, well past the ~2×2 users reach by hand). */}
      <StudioLayoutButton />

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
