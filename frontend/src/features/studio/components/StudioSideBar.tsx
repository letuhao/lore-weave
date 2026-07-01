// Side bar (fixed slot, collapsible) — hosts the active navigator. In the skeleton the body
// is a per-view STUB; real navigators (Manuscript tree first) are separate later components.
import { useTranslation } from 'react-i18next';
import { PanelLeftClose } from 'lucide-react';
import type { ActivityView } from '../types';

interface Props {
  activeView: ActivityView;
  onCollapse: () => void;
}

export function StudioSideBar({ activeView, onCollapse }: Props) {
  const { t } = useTranslation('studio');
  return (
    <div
      data-testid="studio-sidebar"
      className="flex w-[250px] flex-shrink-0 flex-col border-r bg-card"
    >
      <div className="flex h-[34px] flex-shrink-0 items-center justify-between border-b px-3">
        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
          {t(`activity.${activeView}`, { defaultValue: activeView })}
        </span>
        <button
          type="button"
          onClick={onCollapse}
          title={t('sidebar.collapse', { defaultValue: 'Collapse' })}
          className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <PanelLeftClose className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Per-view stub — the real navigator for each view is a later component. */}
      <div className="flex flex-1 flex-col items-center justify-center gap-1.5 p-6 text-center">
        <p className="text-xs font-medium text-foreground/70">
          {t(`navStub.${activeView}.title`, { defaultValue: activeView })}
        </p>
        <p className="max-w-[200px] text-[11px] leading-relaxed text-muted-foreground">
          {t(`navStub.${activeView}.body`, { defaultValue: 'Built next.' })}
        </p>
      </div>
    </div>
  );
}
