import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';

type Props = {
  kind: 'genre' | 'kind';
  onCreate: (payload: { name: string; icon?: string; code?: string }) => Promise<void>;
  onClose: () => void;
};

/** D-GKA-FE-QUICKCREATE-MODAL — small modal to add a book-tier genre or kind, replacing
 *  the old `window.prompt()`. Name is required; icon and code are optional and omitted
 *  when blank. The parent's `guard()` toasts errors, so on a throw we keep the modal
 *  open and just clear the busy flag. Dismissal is blocked while a create is in flight. */
export function QuickCreateModal({ kind, onCreate, onClose }: Props) {
  const { t } = useTranslation('glossaryTiering');
  const [name, setName] = useState('');
  const [icon, setIcon] = useState('');
  const [code, setCode] = useState('');
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
      const payload: { name: string; icon?: string; code?: string } = { name: trimmed };
      if (icon.trim()) payload.icon = icon.trim();
      if (code.trim()) payload.code = code.trim();
      await onCreate(payload);
      onClose();
    } catch {
      setSubmitting(false);
    }
  };

  const title = kind === 'genre' ? t('quickcreate.title_genre') : t('quickcreate.title_kind');

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
            <label className="block space-y-1">
              <span className="text-xs font-medium text-muted-foreground">{t('quickcreate.code')}</span>
              <input value={code} onChange={(e) => setCode(e.target.value)} className="w-full rounded-md border bg-background px-2.5 py-1.5 text-sm" />
              <span className="text-[11px] text-muted-foreground">{t('quickcreate.code_hint')}</span>
            </label>
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
              {submitting ? t('quickcreate.creating') : t('quickcreate.create')}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
