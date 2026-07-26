import { useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Globe2 } from 'lucide-react';
import { useWorld } from '../hooks/useWorld';
import { WorldLorePanel } from '../components/WorldLorePanel';
import { WorldGraphSection } from '../components/WorldGraphSection';
import { WorldTimelineSection } from '../components/WorldTimelineSection';
import { LivingWorldTree } from '../components/LivingWorldTree';
import { WorldPopulateActions } from '../components/WorldPopulateActions';
import { WorldMapsSection } from '../components/WorldMapsSection';

// C21 — the world WORKSPACE. A prose-less worldbuilding surface: it resolves the
// world's bible chapter (the lore anchor) and presents lore authoring + a
// read-only graph. It NEVER surfaces the book/chapter/manuscript mechanic — no
// editor, no chapter list, no draft text. The bible book/chapter exist only as
// the anchor the lore hangs off (hidden plumbing).
export function WorldWorkspacePage() {
  const { t } = useTranslation('world');
  const { worldId } = useParams<{ worldId: string }>();
  const { world, bibleBookId, bibleChapterId, isLoading, isError } = useWorld(worldId);

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6" data-testid="world-workspace">
      <Link
        to="/worlds"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        {t('workspace.back', { defaultValue: 'All worlds' })}
      </Link>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t('workspace.loading', { defaultValue: 'Loading world…' })}</p>
      ) : isError || !world ? (
        <p className="text-sm text-destructive" data-testid="world-load-error">
          {t('workspace.error', { defaultValue: 'World not found.' })}
        </p>
      ) : (
        <>
          <header className="space-y-1">
            <h1 className="flex items-center gap-2 font-serif text-2xl font-semibold">
              <Globe2 className="h-6 w-6 text-muted-foreground" />
              {world.name}
            </h1>
            {world.description && <p className="text-sm text-muted-foreground">{world.description}</p>}
          </header>

          {/* Lore authoring against the bible chapter. */}
          <WorldLorePanel bibleBookId={bibleBookId} bibleChapterId={bibleChapterId} />

          {/* C28 (M6) — the living-world timeline tree: canon trunk + dị bản
              branches as a navigable what-if map (read-only; reuses GraphCanvas). */}
          <section className="space-y-2" data-testid="living-world-section">
            <h2 className="font-medium">{t('living.heading', { defaultValue: 'Living world' })}</h2>
            <p className="text-xs text-muted-foreground">
              {t('living.subtitle', {
                defaultValue: 'Your world’s canon and its what-if branches as a navigable timeline. Click a work to open it.',
              })}
            </p>
            {/* G1 — populate the world without leaving the workspace. */}
            <WorldPopulateActions worldId={worldId} />
            <LivingWorldTree worldId={worldId} />
          </section>

          {/* W10 — the world's maps: base image + region polygons + marker pins, view-only. */}
          <WorldMapsSection worldId={worldId} />

          {/* Read-only world graph — the W2 rollup union (G4). */}
          <WorldGraphSection worldId={worldId} />

          {/* Read-only world timeline — the rollup union (D-WORLD-TIMELINE-ROLLUP). */}
          <WorldTimelineSection worldId={worldId} />
        </>
      )}
    </div>
  );
}
