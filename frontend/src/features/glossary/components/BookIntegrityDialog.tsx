import { useState } from 'react';
import { CheckCircle2, CircleAlert, Loader2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { glossaryApi, type BookIntegrityResponse } from '../api';

export function BookIntegrityDialog({ bookId, onClose }: { bookId: string; onClose: () => void }) {
  const { t } = useTranslation('books');
  const { accessToken } = useAuth();
  const [report, setReport] = useState<BookIntegrityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [repairMessage, setRepairMessage] = useState<string | null>(null);

  const run = async () => {
    if (!accessToken) return;
    setChecking(true);
    setError(null);
    setRepairMessage(null);
    try {
      setReport(await glossaryApi.checkBookIntegrity(bookId, accessToken));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setChecking(false);
    }
  };

  const repair = async () => {
    if (!accessToken) return;
    setRepairing(true);
    setError(null);
    setRepairMessage(null);
    try {
      const result = await glossaryApi.repairBookIntegrity(bookId, accessToken);
      setRepairMessage(t('glossary.integrity.repaired', { count: result.fixed_count }));
      await run();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRepairing(false);
    }
  };

  const statusLabel = (status: string) => t('glossary.integrity.status.' + status, { defaultValue: status });
  const checkLabel = (code: string, fallback: string) => t('glossary.integrity.checks.' + code, { defaultValue: fallback });
  const statusClass = report?.status === 'ok'
    ? 'text-emerald-600'
    : report?.status === 'warning'
      ? 'text-amber-600'
      : 'text-destructive';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="book-integrity-title">
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-lg border bg-card p-5 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 id="book-integrity-title" className="text-base font-semibold">{t('glossary.integrity.title')}</h2>
          <button type="button" onClick={onClose} aria-label={t('glossary.integrity.close')} className="rounded p-1 hover:bg-secondary">
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{t('glossary.integrity.description')}</p>

        {!report && !checking && (
          <button type="button" onClick={() => void run()} className="mt-5 rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground">
            {t('glossary.integrity.run')}
          </button>
        )}
        {checking && (
          <div className="mt-5 flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> {t('glossary.integrity.checking')}
          </div>
        )}
        {repairMessage && <p className="mt-4 rounded border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-700">{repairMessage}</p>}
        {error && <p className="mt-4 rounded border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</p>}
        {report && (
          <>
            <div className="mt-5 flex items-center gap-2 border-b pb-3">
              {report.status === 'ok' ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : <CircleAlert className="h-5 w-5 text-amber-600" />}
              <span className={'text-sm font-semibold ' + statusClass}>{statusLabel(report.status)}</span>
              <span className="ml-auto text-[10px] text-muted-foreground">{new Date(report.checked_at).toLocaleString()}</span>
            </div>
            <ul className="mt-3 space-y-2">
              {report.checks.map((check) => (
                <li key={check.code} className="flex items-start gap-2 rounded border p-2 text-xs">
                  {check.status === 'ok'
                    ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
                    : <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />}
                  <div className="min-w-0">
                    <div className="font-medium">{checkLabel(check.code, check.message)}</div>
                    <div className="mt-0.5 text-muted-foreground">
                      {t('glossary.integrity.issues', { count: check.count })}
                      {check.status === 'unavailable' && ' · ' + t('glossary.integrity.unavailable')}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
            {report.status !== 'ok' && (
              <button type="button" onClick={() => void repair()} disabled={repairing || checking} className="mt-4 mr-2 rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground disabled:opacity-60">
                {repairing ? t('glossary.integrity.repairing') : t('glossary.integrity.repair')}
              </button>
            )}
            <button type="button" onClick={() => void run()} disabled={repairing} className="mt-4 rounded border px-3 py-1.5 text-sm hover:bg-secondary disabled:opacity-60">
              {t('glossary.integrity.runAgain')}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
