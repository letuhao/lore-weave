// Status bar (fixed) — ambient studio status + the bottom-panel toggle. Counts/model/save
// are informational placeholders in the skeleton; real values land with their producers.
// Contributed items (#11 F2 — registerStatusBarItem) render between the fixed chrome; each
// item component is self-contained (data + click), the bar only places it.
import { useTranslation } from 'react-i18next';
import { PanelBottom } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useStatusBarItems } from '../host/StudioHostProvider';

interface Props {
  bookLanguage?: string;
  bottomOpen: boolean;
  onToggleBottom: () => void;
}

export function StudioStatusBar({ bookLanguage, bottomOpen, onToggleBottom }: Props) {
  const { t } = useTranslation('studio');
  const leftItems = useStatusBarItems('left');
  const rightItems = useStatusBarItems('right');
  return (
    <div className="flex h-6 flex-shrink-0 items-center gap-3.5 border-t bg-card px-3 text-[11px] text-muted-foreground">
      <button
        type="button"
        data-testid="studio-toggle-bottom"
        onClick={onToggleBottom}
        title={t('bottom.toggle', { defaultValue: 'Toggle bottom panel' })}
        className={cn(
          'inline-flex items-center gap-1 rounded px-1 py-0.5 hover:bg-secondary hover:text-foreground',
          bottomOpen && 'text-primary',
        )}
      >
        <PanelBottom className="h-3 w-3" />
        {t('bottom.label', { defaultValue: 'Panel' })}
      </button>
      {bookLanguage && <span className="font-mono text-primary">{bookLanguage}</span>}
      {leftItems.map((i) => <i.component key={i.id} />)}
      <div className="flex-1" />
      {rightItems.map((i) => <i.component key={i.id} />)}
      {/* #12 M-H — word count is now a registered F2 item (WordCountStatusItem). The active-model
          indicator likewise belongs as a registered F2 producer, NOT a hardcoded stub: a static
          "no model" span always contradicted the real model shown in the editor's inline toolbar
          (S1 blackbox finding D-S1-MODEL-INDICATOR). Removed until a real producer registers one. */}
      {/* Palette hints (VS Code): ⌘P Quick Open · ⌘⇧P Command Palette. */}
      <span className="font-mono" title={t('palette.quickOpenTitle', { defaultValue: 'Go to chapter, scene, arc' })}>⌘P</span>
      <span className="font-mono" title={t('palette.commandPlaceholder', { defaultValue: 'Type a command…' })}>⌘⇧P</span>
    </div>
  );
}
