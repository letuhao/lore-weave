// Container view for the steering feature: wires useSteering (logic) to the list + editor
// (render-only). Holds only view-selection state (which entry, if any, is being edited).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { steeringApi } from '../api';
import { toast } from 'sonner';
import { useSteering, classifySteeringError, type SteeringErrorKind } from '../hooks/useSteering';
import type { SteeringEntry, SteeringInput } from '../types';
import { SteeringList } from './SteeringList';
import { SteeringEditor } from './SteeringEditor';

export function SteeringManager({ bookId }: { bookId: string }) {
  const { t } = useTranslation('studio');
  const steering = useSteering(bookId);
  const [editing, setEditing] = useState<SteeringEntry | 'new' | null>(null);
  const [errorKind, setErrorKind] = useState<SteeringErrorKind>(null);
  // T12 — the budget, read from chat-service where the cap and the estimator actually live.
  // Refetched alongside the entry list so editing a rule updates the number that matters.
  const { accessToken } = useAuth();
  const budget = useQuery({
    queryKey: ['steering-budget', bookId, steering.entries.length],
    queryFn: () => steeringApi.budget(accessToken!, bookId),
    enabled: !!accessToken && !!bookId,
  });

  const startAdd = () => { setErrorKind(null); setEditing('new'); };
  const startEdit = (e: SteeringEntry) => { setErrorKind(null); setEditing(e); };
  const cancel = () => { setErrorKind(null); setEditing(null); };

  const submit = async (payload: SteeringInput) => {
    try {
      if (editing === 'new') await steering.createEntry(payload);
      else if (editing) await steering.updateEntry(editing.id, payload);
      setEditing(null);
      setErrorKind(null);
    } catch (err) {
      setErrorKind(classifySteeringError(err));
    }
  };

  // review-impl M1: surface the failure (esp. 403 for a VIEW-only collaborator)
  // instead of swallowing it — a silent no-op toggle/delete misleads the user.
  const toastError = (err: unknown) => {
    const kind = classifySteeringError(err);
    toast.error(t(`steering.error.${kind ?? 'other'}`));
  };
  const toggle = (e: SteeringEntry) => {
    void steering.updateEntry(e.id, { enabled: !e.enabled }).catch(toastError);
  };
  const remove = (e: SteeringEntry) => {
    if (window.confirm(t('steering.confirmDelete', { name: e.name }))) {
      void steering.deleteEntry(e.id).catch(toastError);
      if (editing !== 'new' && editing?.id === e.id) cancel();
    }
  };

  return (
    <div data-testid="steering-manager" className="flex h-full min-h-0 flex-col">
      <div className="flex-shrink-0 border-b px-3 py-2">
        <h2 className="text-[13px] font-semibold">{t('steering.heading')}</h2>
        <p className="text-[11px] text-muted-foreground">{t('steering.subheading')}</p>
      </div>

      {steering.isLoading ? (
        <p className="p-6 text-center text-[12px] text-muted-foreground">{t('steering.loading')}</p>
      ) : steering.isError ? (
        <p data-testid="steering-load-error" className="p-6 text-center text-[12px] text-destructive">
          {t('steering.loadError')}
        </p>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col overflow-auto">
          {/* T12 — the cap USED to eat rules in silence. A 2026-09-06 run wrote 8 and the model
              generated against 3 for the whole run, including losing the locked arc outline; the
              only trace was a line in a container's stderr. OUT-5: never silently truncate, report
              the cap. Shown HERE, while the author is editing rules, because that is when they can
              act on it — a mid-turn toast only reports the generation it already spoiled. */}
          {budget.data?.over_budget && (
            <div
              role="status"
              data-testid="steering-over-budget"
              className="mx-3 mt-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-2.5 py-2 text-[11px] text-amber-700 dark:text-amber-300"
            >
              {t('steering.overBudget', {
                defaultValue:
                  'Your rules total ~{{total}} tokens, over the ~{{cap}} that reach the model. '
                  + '{{dropped}} will be left out of every turn: {{names}}. Shorten or disable a rule '
                  + 'so the ones that matter get through.',
                total: budget.data.total_tokens,
                cap: budget.data.cap_tokens,
                dropped: budget.data.would_drop,
                names: budget.data.would_drop_names.join(', '),
              })}
            </div>
          )}
          <SteeringList
            entries={steering.entries}
            atCap={steering.atCap}
            onAdd={startAdd}
            onEdit={startEdit}
            onToggleEnabled={toggle}
            onDelete={remove}
          />
          {editing !== null && (
            <div className="border-t">
              <SteeringEditor
                key={editing === 'new' ? 'new' : editing.id}
                initial={editing === 'new' ? null : editing}
                saving={steering.isMutating}
                errorKind={errorKind}
                onSubmit={submit}
                onCancel={cancel}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
