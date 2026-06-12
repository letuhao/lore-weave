import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Pencil } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import type { TimelineEvent } from '../api';
import { useUpdateEvent } from '../hooks/useEventMutations';

// Phase B C-FE — event edit dialog. Mirrors EntityEditDialog: diff-only
// payload, If-Match via event.version, 412 → conflict toast + close (the hook
// already re-invalidated the timeline so a re-open sees the fresh baseline).

export interface EventEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  event: TimelineEvent;
}

// event_date_iso is the STRUCTURED timeline sort/filter axis (lexicographic),
// so it must stay a partial-precision ISO date — YYYY | YYYY-MM | YYYY-MM-DD.
// Free text like "summer 1880" would silently corrupt date ordering/filtering
// (adversary C-FE F1). Empty is allowed (= no change; see submit).
const ISO_DATE_RE = /^\d{4}(-\d{2}(-\d{2})?)?$/;

export function EventEditDialog({ open, onOpenChange, event }: EventEditDialogProps) {
  const { t } = useTranslation('knowledge');
  const [title, setTitle] = useState(event.title);
  const [summary, setSummary] = useState(event.summary ?? '');
  const [timeCue, setTimeCue] = useState(event.time_cue ?? '');
  const [dateIso, setDateIso] = useState(event.event_date_iso ?? '');

  useEffect(() => {
    if (open) {
      setTitle(event.title);
      setSummary(event.summary ?? '');
      setTimeCue(event.time_cue ?? '');
      setDateIso(event.event_date_iso ?? '');
    }
  }, [open, event.id, event.title, event.summary, event.time_cue, event.event_date_iso]);

  const mutation = useUpdateEvent({
    onSuccess: () => {
      toast.success(t('events.edit.success'));
      onOpenChange(false);
    },
    onError: (err) => {
      const status = (err as Error & { status?: number }).status;
      if (status === 412) {
        toast.error(t('events.edit.conflict'));
        onOpenChange(false);
        return;
      }
      toast.error(t('events.edit.failed', { error: err.message }));
    },
  });

  const submit = async () => {
    const trimmedDate = dateIso.trim();
    // F1: validate the structured date axis (non-empty must be ISO).
    if (trimmedDate && !ISO_DATE_RE.test(trimmedDate)) {
      toast.error(t('events.edit.invalidDate'));
      return;
    }
    const payload = {
      title: title !== event.title ? title : undefined,
      summary: summary !== (event.summary ?? '') ? summary : undefined,
      time_cue: timeCue !== (event.time_cue ?? '') ? timeCue : undefined,
      // F2: only send a VALID non-empty changed date. Empty = no-change —
      // clearing the date axis to "" would sort before all real dates and
      // escape NULL-exclusion in date-range filters, so it's not supported here.
      event_date_iso:
        trimmedDate && trimmedDate !== (event.event_date_iso ?? '') ? trimmedDate : undefined,
    };
    if (
      payload.title === undefined
      && payload.summary === undefined
      && payload.time_cue === undefined
      && payload.event_date_iso === undefined
    ) {
      onOpenChange(false);
      return;
    }
    try {
      await mutation.update({
        eventId: event.id,
        payload,
        ifMatchVersion: event.version,
      });
    } catch {
      // surfaced via onError toast; swallow handled rejection.
    }
  };

  const canSubmit = !!title.trim() && !mutation.isPending;

  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => {
        if (!o && !mutation.isPending) onOpenChange(o);
      }}
      title={t('events.edit.title')}
      description={t('events.edit.description')}
      footer={
        <>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={mutation.isPending}
            className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t('events.edit.cancel')}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit}
            data-testid="event-edit-confirm"
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Pencil className="h-3 w-3" />
            {mutation.isPending ? t('events.edit.saving') : t('events.edit.save')}
          </button>
        </>
      }
    >
      <div className="space-y-3 text-[12px]">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('events.edit.field.title')}
          </span>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={300}
            className="rounded-md border bg-input px-3 py-2 text-xs outline-none focus:border-ring"
            data-testid="event-edit-title"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {t('events.edit.field.summary')}
          </span>
          <textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            rows={4}
            maxLength={4000}
            className="rounded-md border bg-input px-3 py-2 text-xs outline-none focus:border-ring"
            data-testid="event-edit-summary"
          />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-medium text-muted-foreground">
              {t('events.edit.field.timeCue')}
            </span>
            <input
              type="text"
              value={timeCue}
              onChange={(e) => setTimeCue(e.target.value)}
              maxLength={300}
              className="rounded-md border bg-input px-3 py-2 text-xs outline-none focus:border-ring"
              data-testid="event-edit-timecue"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-medium text-muted-foreground">
              {t('events.edit.field.dateIso')}
            </span>
            <input
              type="text"
              value={dateIso}
              onChange={(e) => setDateIso(e.target.value)}
              maxLength={20}
              placeholder={t('events.edit.dateIsoPlaceholder')}
              className="rounded-md border bg-input px-3 py-2 font-mono text-xs outline-none focus:border-ring"
              data-testid="event-edit-dateiso"
            />
          </label>
        </div>
      </div>
    </FormDialog>
  );
}
