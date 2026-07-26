import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, HelpCircle, MapPin, Wand2 } from 'lucide-react';
import { toast } from 'sonner';
import type { EntityKind, UnknownEntity } from '../types';
import { useUnknownReview } from '../hooks/useUnknownReview';
import { ResolveKindModal, type ResolveResult } from './ResolveKindModal';

type Props = {
  bookId: string;
  kinds: EntityKind[];
  onClose: () => void;
};

export function UnknownEntitiesPanel({ bookId, kinds, onClose }: Props) {
  const { t } = useTranslation('glossaryEditor');
  const { items, total, isLoading, error, resolve } = useUnknownReview(bookId);
  const [active, setActive] = useState<UnknownEntity | null>(null);

  // Reassign targets: real kinds only (never the hidden 'unknown' bucket itself).
  const targetKinds = useMemo(
    () => kinds.filter((k) => !k.is_hidden && k.code !== 'unknown').sort((a, b) => a.sort_order - b.sort_order),
    [kinds],
  );

  // How many unknown entities share each source kind code (drives "merge all").
  const countByCode = useMemo(() => {
    const m = new Map<string, number>();
    for (const e of items) {
      if (e.source_kind_code) m.set(e.source_kind_code, (m.get(e.source_kind_code) ?? 0) + 1);
    }
    return m;
  }, [items]);

  const handleResolve = async (entity: UnknownEntity, r: ResolveResult) => {
    const outcome = await resolve(entity, r);
    if (outcome.action === 'merged') {
      toast.success(t('unknown.toast_merged', { count: outcome.count, code: outcome.code }));
    } else {
      toast.success(t('unknown.toast_reassigned', { name: outcome.name || t('unknown.unnamed') }));
    }
    setActive(null);
  };

  return (
    <div className="flex h-full flex-col">
      {/* Top bar */}
      <div className="flex items-center gap-3 border-b px-4 py-3">
        <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <h3 className="text-sm font-semibold">{t('unknown.title')}</h3>
        <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">{total}</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <p className="mb-4 max-w-2xl text-xs text-muted-foreground">{t('unknown.intro')}</p>

        {items.length < total && (
          <p className="mb-3 rounded-md border border-amber-400/30 bg-amber-400/10 px-3 py-1.5 text-[11px] text-amber-600">
            {t('unknown.truncated', { shown: items.length, total })}
          </p>
        )}

        {isLoading && (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="h-14 animate-pulse rounded-md bg-secondary" />)}
          </div>
        )}

        {error && <p className="text-sm text-destructive">{(error as Error).message}</p>}

        {!isLoading && !error && items.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-16 text-center">
            <HelpCircle className="h-8 w-8 text-muted-foreground/50" />
            <p className="text-sm font-medium">{t('unknown.empty_title')}</p>
            <p className="max-w-sm text-xs text-muted-foreground">{t('unknown.empty_desc')}</p>
          </div>
        )}

        {items.length > 0 && (
          <div className="divide-y rounded-lg border">
            {items.map((e) => (
              <div key={e.entity_id} className="flex items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{e.name || t('unknown.unnamed')}</div>
                  <div className="mt-0.5 flex items-center gap-2 text-[10px] text-muted-foreground">
                    {e.source_kind_code ? (
                      <span className="rounded bg-amber-400/15 px-1.5 py-0.5 font-mono text-amber-500">
                        {t('unknown.arrived_as', { code: e.source_kind_code })}
                      </span>
                    ) : (
                      <span className="italic">{t('unknown.no_source_code')}</span>
                    )}
                    <span className="rounded bg-secondary px-1.5 py-0.5">{t(`unknown.status_${e.status}`)}</span>
                    {e.scope_label && (
                      <span className="inline-flex items-center gap-0.5 rounded bg-violet-500/15 px-1.5 py-0.5 text-violet-400">
                        <MapPin className="h-2.5 w-2.5" />
                        {e.scope_label}
                      </span>
                    )}
                    <span>{new Date(e.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
                <button
                  onClick={() => setActive(e)}
                  data-testid={`unknown-resolve-${e.entity_id}`}
                  className="inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/5 px-2.5 py-1 text-[11px] font-medium text-primary hover:bg-primary/10 transition-colors"
                >
                  <Wand2 className="h-3 w-3" />
                  {t('unknown.resolve')}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {active && (
        <ResolveKindModal
          entity={active}
          kinds={targetKinds}
          sameCodeCount={active.source_kind_code ? (countByCode.get(active.source_kind_code) ?? 1) : 1}
          onResolve={(r) => handleResolve(active, r)}
          onClose={() => setActive(null)}
        />
      )}
    </div>
  );
}
