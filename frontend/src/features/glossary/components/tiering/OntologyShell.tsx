import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Layers, Grid3x3, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ManageWorkspace } from './ManageWorkspace';
import { MatrixScreen } from './MatrixScreen';
import { SyncScreen } from './SyncScreen';

type OntologyTab = 'manage' | 'matrix' | 'sync';

/** G6f host for the tiered ontology screens — a tab bar (Manage / Matrix / Sync) over
 *  the book-local ontology, with a back link to the entity list. Replaces the old flat
 *  KindEditor + GenreGroupsPanel views. */
export function OntologyShell({ bookId, onClose }: { bookId: string; onClose: () => void }) {
  const { t } = useTranslation('glossaryTiering');
  const [tab, setTab] = useState<OntologyTab>('manage');

  const tabs: { key: OntologyTab; label: string; icon: typeof Layers }[] = [
    { key: 'manage', label: t('manage.tab_manage'), icon: Layers },
    { key: 'matrix', label: t('manage.tab_matrix'), icon: Grid3x3 },
    { key: 'sync', label: t('manage.tab_sync'), icon: RefreshCw },
  ];

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center gap-3">
        <button
          onClick={onClose}
          className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {t('shell.back_to_entities')}
        </button>
        <div className="flex items-center gap-1 rounded-lg border bg-card p-1">
          {tabs.map((tb) => (
            <button
              key={tb.key}
              onClick={() => setTab(tb.key)}
              data-testid={`ontology-tab-${tb.key}`}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                tab === tb.key ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <tb.icon className="h-3.5 w-3.5" />
              {tb.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'manage' && <ManageWorkspace bookId={bookId} />}
      {tab === 'matrix' && <MatrixScreen bookId={bookId} />}
      {tab === 'sync' && <SyncScreen bookId={bookId} />}
    </div>
  );
}
