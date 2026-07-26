import { useTranslation } from 'react-i18next';
import { Globe2 } from 'lucide-react';
import { toast } from 'sonner';
import { WorldPicker } from '@/components/shared/WorldPicker';
import { useBookWorldLink } from '../hooks/useBookWorldLink';

// W6 (G3) — the book-side world cross-link. Lets a user group this book into a
// world (or move/clear it) by NAME via the shared WorldPicker, and — when it's
// in a world — open that world's workspace. The picker IS the control: a pick
// attaches, clearing detaches; both reload the book so the backlink reflects it.
interface Props {
  bookId: string;
  /** The book's current world (from the book read), or null when standalone. */
  worldId: string | null | undefined;
  /** Reload the book after a link/unlink so `world_id` (and this section) update. */
  onChanged: () => void;
  /**
   * 17_translation_enrichment_sharing_settings_docks.md DOCK-7 fix — "Open in world" used to
   * render a raw react-router `<Link>` here, which this component is now used by BOTH the
   * classic `SettingsTab` route AND the `BookSettingsPanel` studio dock (dockable-gui.md DOCK-7
   * bans `<Link>`/`useNavigate` inside a panel's component tree). Instead of branching on
   * `useOptionalStudioHost()` internally, the caller injects the navigation behavior — mirrors
   * `OverviewSection`'s `onOpenBook`/`onOpenWorld` shape (dockable-gui.md DOCK-7 precedent):
   * `SettingsTab` passes a `useNavigate()`-based handler, `BookSettingsPanel` passes a
   * `followStudioLink`-based one. This component itself never imports react-router or the
   * studio host.
   */
  onOpenWorld: (worldId: string) => void;
}

export function BookWorldSection({ bookId, worldId, onChanged, onOpenWorld }: Props) {
  const { t } = useTranslation('books');
  const { link, unlink, isPending } = useBookWorldLink(bookId);
  const current = worldId ?? null;

  async function handleChange(next: string | null) {
    try {
      if (next && next !== current) await link(next);
      else if (!next && current) await unlink(current);
      else return; // no-op (re-selected the same world)
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div data-testid="book-world-section">
      <div className="mb-4 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {t('settings.world.title', { defaultValue: 'World' })}
      </div>
      <p className="mb-2 text-[11px] text-muted-foreground">
        {t('settings.world.hint', {
          defaultValue: 'Group this book into a world to roll it into the world’s graph and timeline.',
        })}
      </p>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <WorldPicker value={current} onChange={handleChange} disabled={isPending} />
        </div>
        {current && (
          <button
            type="button"
            onClick={() => onOpenWorld(current)}
            data-testid="book-open-in-world"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-primary/40 bg-primary/5 px-3 py-2 text-xs font-medium text-primary hover:bg-primary/10"
          >
            <Globe2 className="h-3.5 w-3.5" />
            {t('settings.world.open', { defaultValue: 'Open in world' })}
          </button>
        )}
      </div>
    </div>
  );
}
