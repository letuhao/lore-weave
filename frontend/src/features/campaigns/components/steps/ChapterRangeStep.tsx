import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '../../../books/api';
import type { WizardForm } from '../../hooks/useCampaignWizard';

interface Props {
  form: WizardForm;
  setField: <K extends keyof WizardForm>(key: K, value: WizardForm[K]) => void;
}

/** Step 2 (view): chapter range over the book's PUBLISHED chapters (the ingest
 *  precondition). Blank from/to = whole book. Shows the in-range count. */
export function ChapterRangeStep({ form, setField }: Props) {
  const { t } = useTranslation('campaigns');
  const { accessToken } = useAuth();

  const chapters = useQuery({
    queryKey: ['campaign-wizard', 'chapters', form.bookId],
    // The chapter-list endpoint caps a page at 100, so a single limit:5000 request
    // silently returned only the first 100 — the in-range/published counts then
    // under-reported on books >100 chapters. Loop-fetch every page instead.
    queryFn: async () => {
      const items: Chapter[] = [];
      const pageSize = 100;
      for (let offset = 0; ; offset += pageSize) {
        const r = await booksApi.listChapters(accessToken!, form.bookId!, { limit: pageSize, offset });
        items.push(...r.items);
        if (r.items.length < pageSize || items.length >= r.total) break;
      }
      return { items, total: items.length };
    },
    enabled: !!accessToken && !!form.bookId,
  });

  const published = useMemo(
    () => (chapters.data?.items ?? []).filter(
      (c) => c.editorial_status === 'published' && c.lifecycle_state === 'active',
    ),
    [chapters.data],
  );

  const inRange = useMemo(
    () => published.filter((c) => {
      if (form.chapterFrom !== null && c.sort_order < form.chapterFrom) return false;
      if (form.chapterTo !== null && c.sort_order > form.chapterTo) return false;
      return true;
    }).length,
    [published, form.chapterFrom, form.chapterTo],
  );

  const numField = 'w-28 rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring';
  const parseNum = (v: string) => (v.trim() === '' ? null : Number(v));

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        {t('range.intro', {
          defaultValue: '{{count}} published chapters in this book. Leave blank to run the whole book.',
          count: published.length,
        })}
      </p>
      <div className="flex items-end gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            {t('range.from', { defaultValue: 'From (sort order)' })}
          </span>
          <input type="number" className={numField}
            value={form.chapterFrom ?? ''}
            onChange={(e) => setField('chapterFrom', parseNum(e.target.value))} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            {t('range.to', { defaultValue: 'To (sort order)' })}
          </span>
          <input type="number" className={numField}
            value={form.chapterTo ?? ''}
            onChange={(e) => setField('chapterTo', parseNum(e.target.value))} />
        </label>
      </div>
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">
          {t('range.gating', { defaultValue: 'Translation pacing' })}
        </span>
        <select
          className="w-full max-w-md rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring"
          value={form.gatingMode}
          onChange={(e) => setField('gatingMode', e.target.value as WizardForm['gatingMode'])}
        >
          <option value="phase_barrier">
            {t('range.gatingPhaseBarrier', {
              defaultValue: 'Phase barrier — highest quality (finish all knowledge extraction before any translation)',
            })}
          </option>
          <option value="cold_start">
            {t('range.gatingColdStart', {
              defaultValue: 'Cold start — faster (translate each chapter as soon as its knowledge is ready)',
            })}
          </option>
        </select>
      </label>
      {form.chapterFrom !== null && form.chapterTo !== null && form.chapterFrom > form.chapterTo ? (
        <span className="text-[11px] text-destructive">
          {t('range.invalid', { defaultValue: 'From must be ≤ To.' })}
        </span>
      ) : (
        <span className="text-sm font-medium">
          {t('range.inRange', { defaultValue: '{{count}} chapters selected', count: inRange })}
        </span>
      )}
      {chapters.data && published.length === 0 && (
        <span className="text-[11px] text-destructive">
          {t('range.nonekPublished', { defaultValue: 'No published chapters — ingest/publish first.' })}
        </span>
      )}
    </div>
  );
}
