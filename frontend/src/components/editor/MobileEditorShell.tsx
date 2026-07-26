// LOOM (M5a / D-T5.4-MOBILE) — the mobile chapter-editor shell: a two-level nav.
//
// PO decision (LOCKED 2026-06-26): mobile = ONE full component at a time + navigate
// between them. The bottom bar picks a top GROUP (Editor / Studio / History); inside the
// Studio group the MobilePanelSwitcher (in CompositionPanel) picks one studio panel.
//
// All three groups stay MOUNTED (CSS show/hide) so the editor doc, the hoisted co-writer
// stream, and the revision list keep their state across group switches — only a
// desktop↔mobile breakpoint flip swaps the whole shell (a different component tree).
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Pen, Sparkles, Clock } from 'lucide-react';

export type MobileGroup = 'editor' | 'studio' | 'history';

export function MobileEditorShell({ group, onGroupChange, header, editor, studio, history }: {
  group: MobileGroup;
  onGroupChange: (g: MobileGroup) => void;
  /** A compact top bar (breadcrumb / title / save) — rendered above the active group. */
  header: ReactNode;
  editor: ReactNode;
  studio: ReactNode;
  history: ReactNode;
}) {
  const { t } = useTranslation('editor');
  const groups: { id: MobileGroup; label: string; Icon: typeof Pen }[] = [
    { id: 'editor', label: t('mobile.editor', { defaultValue: 'Editor' }), Icon: Pen },
    { id: 'studio', label: t('mobile.studio', { defaultValue: 'Studio' }), Icon: Sparkles },
    { id: 'history', label: t('mobile.history', { defaultValue: 'History' }), Icon: Clock },
  ];
  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="mobile-editor-shell">
      {header}
      {/* One group visible at a time; all three stay mounted (state-preserving). The
          active group uses min-h-0 so its own scroll area works; the others are hidden. */}
      <div className="relative min-h-0 flex-1 overflow-hidden" data-testid={`mobile-group-${group}`}>
        <div className={group === 'editor' ? 'flex h-full flex-col' : 'hidden'}>{editor}</div>
        <div className={group === 'studio' ? 'flex h-full flex-col' : 'hidden'}>{studio}</div>
        <div className={group === 'history' ? 'flex h-full flex-col' : 'hidden'}>{history}</div>
      </div>
      {/* Bottom group bar. Uses safe-area padding so it clears the home indicator; the
          editor's own input sits above it (visualViewport handles the soft keyboard). */}
      <nav
        role="tablist"
        aria-label={t('mobile.nav', { defaultValue: 'Editor sections' })}
        className="flex shrink-0 border-t bg-card pb-[env(safe-area-inset-bottom)]"
        data-testid="mobile-group-bar"
      >
        {groups.map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={group === id}
            data-testid={`mobile-tab-${id}`}
            onClick={() => onGroupChange(id)}
            className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium transition-colors ${
              group === id ? 'text-primary' : 'text-muted-foreground'
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </nav>
    </div>
  );
}
