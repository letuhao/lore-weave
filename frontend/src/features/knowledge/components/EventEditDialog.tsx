import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Pencil, Plus } from 'lucide-react';
import { FormDialog } from '@/components/shared';
import type { EventCreatePayload, TimelineEvent } from '../api';
import { useCreateEvent, useUpdateEvent } from '../hooks/useEventMutations';

// Phase B C-FE — event edit dialog. Mirrors EntityEditDialog: diff-only
// payload, If-Match via event.version, 412 → conflict toast + close (the hook
// already re-invalidated the timeline so a re-open sees the fresh baseline).
//
// D-KG-EVENT-CREATE-ROUTE — the SAME dialog also authors a NEW event when given
// `create` context instead of an `event` (the Character-Arc "+ Add event"). One
// of `event` / `create` must be supplied; `create` (when present) wins.

export interface EventCreateContext {
  projectId: string;
  chapterId?: string | null;
  /** Seed participants (e.g. the focused character's name) so the new event
   *  lands on that character's arc. */
  participants?: string[];
}

export interface EventEditDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Edit mode — the existing event to correct. Omit to author a new one. */
  event?: TimelineEvent;
  /** Create mode — the context to author a new event into. */
  create?: EventCreateContext;
}

// event_date_iso is the STRUCTURED timeline sort/filter axis (lexicographic),
// so it must stay a partial-precision ISO date — YYYY | YYYY-MM | YYYY-MM-DD.
// Free text like "summer 1880" would silently corrupt date ordering/filtering
// (adversary C-FE F1). Empty is allowed (= no change; see submit).
const ISO_DATE_RE = /^\d{4}(-\d{2}(-\d{2})?)?$/;

export function EventEditDialog({ open, onOpenChange, event, create }: EventEditDialogProps) {
  const { t } = useTranslation('knowledge');
  const isCreate = create != null;
  const [title, setTitle] = useState(event?.title ?? '');
  const [summary, setSummary] = useState(event?.summary ?? '');
  const [timeCue, setTimeCue] = useState(event?.time_cue ?? '');
  const [dateIso, setDateIso] = useState(event?.event_date_iso ?? '');

  useEffect(() => {
    if (open) {
      // Create mode opens blank; edit mode seeds from the event.
      setTitle(event?.title ?? '');
      setSummary(event?.summary ?? '');
      setTimeCue(event?.time_cue ?? '');
      setDateIso(event?.event_date_iso ?? '');
    }
  }, [open, event?.id, event?.title, event?.summary, event?.time_cue, event?.event_date_iso]);

  const updateMutation = useUpdateEvent({
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

  const createMutation = useCreateEvent({
    onSuccess: () => {
      toast.success(t('events.create.success', { defaultValue: 'Event added.' }));
      onOpenChange(false);
    },
    onError: (err) =>
      toast.error(t('events.create.failed', { defaultValue: 'Add failed: {{error}}', error: err.message })),
  });

  const pending = isCreate ? createMutation.isPending : updateMutation.isPending;

  const submit = async () => {
    const trimmedDate = dateIso.trim();
    // F1: validate the structured date axis (non-empty must be ISO).
    if (trimmedDate && !ISO_DATE_RE.test(trimmedDate)) {
      toast.error(t('events.edit.invalidDate'));
      return;
    }

    if (isCreate && create) {
      const trimmedTitle = title.trim();
      if (!trimmedTitle) return;
      const payload: EventCreatePayload = {
        project_id: create.projectId,
        title: trimmedTitle,
        ...(summary.trim() ? { summary: summary.trim() } : {}),
        ...(timeCue.trim() ? { time_cue: timeCue.trim() } : {}),
        ...(trimmedDate ? { event_date_iso: trimmedDate } : {}),
        ...(create.chapterId ? { chapter_id: create.chapterId } : {}),
        ...(create.participants && create.participants.length
          ? { participants: create.participants }
          : {}),
      };
      try {
        await createMutation.create(payload);
      } catch {
        // surfaced via onError toast; swallow the handled rejection.
      }
      return;
    }

    if (!event) return;
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
      await updateMutation.update({
        eventId: event.id,
        payload,
        ifMatchVersion: event.version,
      });
    } catch {
      // surfaced via onError toast; swallow handled rejection.
    }
  };

  const canSubmit = !!title.trim() && !pending;

  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => {
        if (!o && !pending) onOpenChange(o);
      }}
      title={isCreate ? t('events.create.title', { defaultValue: 'Add event' }) : t('events.edit.title')}
      description={
        isCreate
          ? t('events.create.description', { defaultValue: 'Author a new timeline event for this character.' })
          : t('events.edit.description')
      }
      footer={
        <>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={pending}
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
            {isCreate ? <Plus className="h-3 w-3" /> : <Pencil className="h-3 w-3" />}
            {pending
              ? (isCreate ? t('events.create.saving', { defaultValue: 'Adding…' }) : t('events.edit.saving'))
              : (isCreate ? t('events.create.save', { defaultValue: 'Add event' }) : t('events.edit.save'))}
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
