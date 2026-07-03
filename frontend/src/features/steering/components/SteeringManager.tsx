// Container view for the steering feature: wires useSteering (logic) to the list + editor
// (render-only). Holds only view-selection state (which entry, if any, is being edited).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSteering, classifySteeringError, type SteeringErrorKind } from '../hooks/useSteering';
import type { SteeringEntry, SteeringInput } from '../types';
import { SteeringList } from './SteeringList';
import { SteeringEditor } from './SteeringEditor';

export function SteeringManager({ bookId }: { bookId: string }) {
  const { t } = useTranslation('studio');
  const steering = useSteering(bookId);
  const [editing, setEditing] = useState<SteeringEntry | 'new' | null>(null);
  const [errorKind, setErrorKind] = useState<SteeringErrorKind>(null);

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

  const toggle = (e: SteeringEntry) => { void steering.updateEntry(e.id, { enabled: !e.enabled }).catch(() => {}); };
  const remove = (e: SteeringEntry) => {
    if (window.confirm(t('steering.confirmDelete', { name: e.name }))) {
      void steering.deleteEntry(e.id).catch(() => {});
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
