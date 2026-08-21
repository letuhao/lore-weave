// Top bar (fixed) — book context + a command-palette affordance. Generate / Save / model
// controls arrive with the panels that need them (skeleton keeps this informational).
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { ArrowLeft, CircleHelp, LayoutDashboard, Search, Settings, PanelsTopLeft } from 'lucide-react';
import { StudioLayoutButton } from './StudioLayoutButton';
import { PanelPicker } from '../layout/PanelPicker';

interface Props {
  bookId: string;
  bookTitle: string;
  /** Opens Quick Open (#06a). The affordance shows locations only — tools live in ⌘⇧P. */
  onOpenQuickOpen?: () => void;
  /** Opens the catalog-driven User Guide panel. */
  onOpenGuide?: () => void;
}

function PanelPickerButton() {
  const { t } = useTranslation('studio');
  const [open, setOpen] = useState(false);
  return <div className="relative"><button type="button" onClick={() => setOpen((v) => !v)} data-testid="studio-panel-button" aria-haspopup="menu" aria-expanded={open} title={t('panelsPicker.title', { defaultValue: 'Workspace panels' })} className={`flex h-7 w-7 items-center justify-center rounded-md ${open ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-secondary hover:text-foreground'}`}><PanelsTopLeft className="h-4 w-4" /></button>{open && <><div className="fixed inset-0 z-40" data-testid="studio-panel-backdrop" onClick={() => setOpen(false)} /><div className="absolute right-0 top-full z-50 mt-1"><PanelPicker /></div></>}</div>;
}

export function StudioTopBar({ bookId, bookTitle, onOpenQuickOpen, onOpenGuide }: Props) {
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
      <PanelPickerButton />
      <StudioLayoutButton />

      <button
        type="button"
        onClick={onOpenGuide}
        data-testid="studio-help-button"
        title={t('userGuide.open', { defaultValue: 'Open user guide' })}
        aria-label={t('userGuide.open', { defaultValue: 'Open user guide' })}
        className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
      >
        <CircleHelp className="h-4 w-4" />
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
