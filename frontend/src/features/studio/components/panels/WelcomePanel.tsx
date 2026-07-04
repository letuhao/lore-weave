// The default dockview panel — seeded once per book with no saved layout (useStudioLayout).
// #19 Wave 1 extends it in place (mechanic unchanged): reads the account's onboarding role pref
// to render tailored quick-open links + an Open User Guide action. The role picker overlay and
// guided tour are NOT started from here (both are one-shot cross-panel actions and this is a
// true dockview panel, isolated from StudioFrameInner's tree per DOCK-4) — reachable instead via
// the Command Palette's "Studio: Choose Your Focus" / "Studio: Start Guided Tour", which live in
// the same component tree as the tour/onboarding hooks and need no bus plumbing.
import { useTranslation } from 'react-i18next';
import { LayoutDashboard, BookOpen } from 'lucide-react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useStudioHost } from '../../host/StudioHostProvider';
import { useStudioOnboarding } from '../../onboarding/useStudioOnboarding';
import { getStudioPanelDef } from '../../panels/catalog';
import type { StudioRole } from '../../onboarding/types';

/** Per-role highlight panels for the Welcome quick-links row (#19 spec role→highlight table). */
const ROLE_HIGHLIGHTS: Record<StudioRole, string[]> = {
  writer: ['compose', 'editor', 'planner'],
  worldbuilder: ['glossary', 'wiki', 'knowledge'],
  translator: ['translation', 'enrichment-compose'],
  enricher: ['enrichment-gaps', 'enrichment-sources'],
  manager: ['sharing', 'book-settings'],
};
const DEFAULT_HIGHLIGHTS = ['compose', 'editor'];

export function WelcomePanel(_props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { role, isLoading } = useStudioOnboarding();

  // Gate on isLoading so returning users never see the generic default flash before their role
  // resolves (#19 G6) — today's static copy renders in the meantime, matching prior behavior.
  const highlightIds = !isLoading && role ? (ROLE_HIGHLIGHTS[role] ?? DEFAULT_HIGHLIGHTS) : DEFAULT_HIGHLIGHTS;
  const highlights = highlightIds.map((id) => getStudioPanelDef(id)).filter((d): d is NonNullable<typeof d> => !!d);

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <LayoutDashboard className="h-8 w-8 text-muted-foreground/50" />
      <p className="text-sm font-medium text-foreground/80">
        {t('welcome.title', { defaultValue: 'Writing Studio' })}
      </p>
      <p className="max-w-sm text-xs text-muted-foreground">
        {t('welcome.body', {
          defaultValue:
            'A dockable workspace for this book. Panels (compose, planner, cast, quality…) will be added here one at a time. Drag tabs to split, stack, float, or pop out into their own window.',
        })}
      </p>

      {!isLoading && highlights.length > 0 && (
        <div className="mt-1 flex flex-wrap items-center justify-center gap-2" data-testid="welcome-highlights">
          {highlights.map((def) => (
            <button
              key={def.id}
              type="button"
              data-testid={`welcome-highlight-${def.id}`}
              onClick={() => host.openPanel(def.id, { title: t(def.titleKey, { defaultValue: def.id }) })}
              className="rounded-md border px-2.5 py-1 text-xs font-medium transition-colors hover:border-primary hover:bg-secondary"
            >
              {t(def.titleKey, { defaultValue: def.id })}
            </button>
          ))}
        </div>
      )}

      <button
        type="button"
        data-testid="welcome-open-user-guide"
        onClick={() => host.openPanel('user-guide', { title: t('panels.user-guide.title', { defaultValue: 'User Guide' }) })}
        className="mt-1 inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
      >
        <BookOpen className="h-3.5 w-3.5" />
        {t('welcome.openUserGuide', { defaultValue: 'Open the User Guide' })}
      </button>
      <p className="text-[11px] text-muted-foreground/60">
        {t('welcome.paletteHint', { defaultValue: '⌘⇧P → "Choose Your Focus" or "Start Guided Tour" anytime' })}
      </p>
    </div>
  );
}
