import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowRight } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import { useEntities } from '../hooks/useEntities';
import { useDebouncedValue } from '../hooks/useDebouncedValue';

// S-05b (F1) — the entity picker that replaces the re_target `window.prompt("…entity
// id")` dead-end. A novelist cannot know a UUID; here they SEARCH their own entities
// and pick one, exactly like CreateRelationDialog's object typeahead (same hooks —
// useEntities({search}) + useDebouncedValue + FormDialog). On pick it hands the id
// back to the caller (TriageQueue), which fires resolve(re_target, {target_entity_id}).

export interface TriageRetargetDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  /** Called with the chosen entity id when the user confirms. */
  onPick: (entityId: string) => void;
}

export function TriageRetargetDialog({
  open,
  onOpenChange,
  projectId,
  onPick,
}: TriageRetargetDialogProps) {
  const { t } = useTranslation('knowledge');
  const [pickedId, setPickedId] = useState('');
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (open) {
      setPickedId('');
      setQuery('');
    }
  }, [open]);

  const debounced = useDebouncedValue(query, 300);
  const { entities } = useEntities({
    project_id: projectId,
    search: debounced.length >= 2 ? debounced : undefined,
    limit: 20,
    offset: 0,
  });

  const confirm = () => {
    if (!pickedId) return;
    onPick(pickedId);
    onOpenChange(false);
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('triage.retarget.title')}
      description={t('triage.retarget.description')}
      footer={
        <>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary"
          >
            {t('triage.retarget.cancel')}
          </button>
          <button
            type="button"
            onClick={confirm}
            disabled={!pickedId}
            data-testid="triage-retarget-confirm"
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <ArrowRight className="h-3 w-3" />
            {t('triage.retarget.confirm')}
          </button>
        </>
      }
    >
      <div className="space-y-2 text-[12px]">
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPickedId('');
          }}
          placeholder={t('triage.retarget.searchPlaceholder')}
          className="w-full rounded-md border bg-input px-3 py-2 text-xs outline-none focus:border-ring"
          data-testid="triage-retarget-search"
        />
        {debounced.length >= 2 && (
          <ul
            className="max-h-40 overflow-y-auto rounded-md border"
            data-testid="triage-retarget-list"
          >
            {entities.length === 0 && (
              <li className="px-3 py-2 text-[11px] text-muted-foreground">
                {t('triage.retarget.noMatches')}
              </li>
            )}
            {entities.map((e) => (
              <li key={e.id}>
                <button
                  type="button"
                  onClick={() => {
                    setPickedId(e.id);
                    setQuery(e.name);
                  }}
                  data-testid={`triage-retarget-option-${e.id}`}
                  className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-xs transition-colors hover:bg-secondary ${
                    pickedId === e.id ? 'bg-primary/10' : ''
                  }`}
                >
                  <span>{e.name}</span>
                  <span className="text-[10px] capitalize text-muted-foreground">
                    {e.kind}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </FormDialog>
  );
}
