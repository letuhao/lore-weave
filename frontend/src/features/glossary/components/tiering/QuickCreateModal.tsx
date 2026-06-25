import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';

export type QuickCreatePayload = {
  name: string;
  icon?: string;
  code?: string;
  color?: string;
};

type Props = {
  kind: 'genre' | 'kind';
  /** 'create' (default) opens an empty form; 'edit' prefills from `initial`
   *  and hides the code field (code is the stable key — not patchable). */
  mode?: 'create' | 'edit';
  initial?: { name?: string; icon?: string; code?: string; color?: string };
  onCreate: (payload: QuickCreatePayload) => Promise<void>;
  onClose: () => void;
};

// BE default kind/genre color (services/glossary-service createBook*Core).
const DEFAULT_COLOR = '#6366f1';

/** D-GKA-FE-QUICKCREATE-MODAL — small modal to add OR edit a book-tier genre or kind,
 *  replacing the old `window.prompt()`. Name is required; icon/code/color are optional.
 *  The new design dropped the per-kind color picker the old draft had (the `color`
 *  field exists end-to-end in the BE + types) — this restores it for both create and
 *  edit. The parent's `guard()` toasts errors, so on a throw we keep the modal open
 *  and just clear the busy flag. Dismissal is blocked while a write is in flight. */
export function QuickCreateModal({ kind, mode = 'create', initial, onCreate, onClose }: Props) {
  const { t } = useTranslation('glossaryTiering');
  const isEdit = mode === 'edit';
  const [name, setName] = useState(initial?.name ?? '');
  const [icon, setIcon] = useState(initial?.icon ?? '');
  const [code, setCode] = useState(initial?.code ?? '');
  const [color, setColor] = useState(initial?.color || DEFAULT_COLOR);
  const [error, setError] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const close = () => { if (!submitting) onClose(); };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, submitting]);

  const submit = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError(true);
      return;
    }
    setError(false);
    setSubmitting(true);
    try {
      // On edit we always send name/icon/color so a cleared icon or a recolour
      // takes effect; code is the stable key and is omitted. On create, blank
      // optional fields are omitted (the BE applies its defaults).
      const payload: QuickCreatePayload = { name: trimmed, color };
      if (isEdit) {
        payload.icon = icon.trim();
      } else {
        if (icon.trim()) payload.icon = icon.trim();
        if (code.trim()) payload.code = code.trim();
      }
      await onCreate(payload);
      onClose();
    } catch {
      setSubmitting(false);
    }
  };

  const title = isEdit
    ? kind === 'genre' ? t('quickcreate.edit_genre') : t('quickcreate.edit_kind')
    : kind === 'genre' ? t('quickcreate.title_genre') : t('quickcreate.title_kind');

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={close} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="flex w-full max-w-sm flex-col rounded-xl border bg-background shadow-2xl" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-start justify-between border-b bg-card px-5 py-4">
            <h2 className="text-sm font-semibold">{title}</h2>
            <button onClick={close} disabled={submitting} className="rounded-md p-1 hover:bg-secondary disabled:opacity-40" aria-label={t('quickcreate.cancel')}>
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-3 p-5">
            <label className="block space-y-1">
              <span className="text-xs font-medium text-muted-foreground">{t('quickcreate.name')}</span>
              <input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void submit(); }}
                placeholder={t('quickcreate.name_placeholder')}
                className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm"
              />
              {error && <span className="text-xs text-destructive">{t('quickcreate.name_required')}</span>}
            </label>
            <label className="block space-y-1">
              <span className="text-xs font-medium text-muted-foreground">{t('quickcreate.icon')}</span>
              <input value={icon} onChange={(e) => setIcon(e.target.value)} className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm" />
            </label>
            {/* Color picker — restores the per-kind/genre colour the old design had.
                Native swatch + a read-only hex so the value is legible. */}
            <div className="block space-y-1">
              <span className="text-xs font-medium text-muted-foreground">{t('quickcreate.color')}</span>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={color}
                  onChange={(e) => setColor(e.target.value)}
                  aria-label={t('quickcreate.color')}
                  data-testid="quickcreate-color"
                  className="h-8 w-12 cursor-pointer rounded border bg-background p-0.5"
                />
                <span className="font-mono text-[11px] uppercase text-muted-foreground">{color}</span>
              </div>
            </div>
            {/* Code is the stable key — only settable at create time. */}
            {!isEdit && (
              <label className="block space-y-1">
                <span className="text-xs font-medium text-muted-foreground">{t('quickcreate.code')}</span>
                <input value={code} onChange={(e) => setCode(e.target.value)} className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm" />
                <span className="text-[11px] text-muted-foreground">{t('quickcreate.code_hint')}</span>
              </label>
            )}
          </div>

          <div className="flex justify-end gap-2 border-t px-5 py-3">
            <button onClick={close} disabled={submitting} className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary disabled:opacity-50">
              {t('quickcreate.cancel')}
            </button>
            <button
              onClick={() => void submit()}
              disabled={submitting}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {submitting
                ? isEdit ? t('quickcreate.saving') : t('quickcreate.creating')
                : isEdit ? t('quickcreate.save') : t('quickcreate.create')}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
