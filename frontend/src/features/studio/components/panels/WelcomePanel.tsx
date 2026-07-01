// The default dockview panel — a placeholder until real tools are added. Rendered inside a
// dock group, so it can already be split / stacked / floated / popped out.
import { useTranslation } from 'react-i18next';
import { LayoutDashboard } from 'lucide-react';
import type { IDockviewPanelProps } from 'dockview-react';

export function WelcomePanel(_props: IDockviewPanelProps) {
  const { t } = useTranslation('studio');
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
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
    </div>
  );
}
