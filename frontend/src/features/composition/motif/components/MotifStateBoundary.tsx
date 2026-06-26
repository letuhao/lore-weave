// W6 §4.1 — the shared loading / error / permission wrapper. Standardizes the
// state matrix every motif surface needs (the mockups show only the happy path;
// audit H-8 R4). `empty` + `cost-confirm` are screen-specific (NOT here).
//
// Render-only view: it receives state flags + callbacks, holds no logic.
import { useTranslation } from 'react-i18next';
import type { ReactNode } from 'react';

type Props = {
  isLoading?: boolean;
  isError?: boolean;
  /** When set, renders the read-only "Clone to edit" lock instead of children. */
  permissionLocked?: boolean;
  onRetry?: () => void;
  onClone?: () => void;
  /** What the skeleton should look like — `cards` (3 card stubs) or `rows`. */
  skeleton?: 'cards' | 'rows' | 'spinner';
  testid?: string;
  children: ReactNode;
};

export function MotifStateBoundary({
  isLoading, isError, permissionLocked, onRetry, onClone, skeleton = 'spinner', testid = 'motif-state', children,
}: Props) {
  const { t } = useTranslation('composition');

  if (isLoading) {
    return (
      <div data-testid={`${testid}-loading`} aria-busy="true" className="p-2">
        {skeleton === 'cards' ? (
          <div className="flex flex-col gap-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-20 animate-pulse rounded border border-neutral-200 bg-neutral-100 dark:border-neutral-700 dark:bg-neutral-800" />
            ))}
          </div>
        ) : skeleton === 'rows' ? (
          <div className="flex flex-col gap-1">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-8 animate-pulse rounded bg-neutral-100 dark:bg-neutral-800" />
            ))}
          </div>
        ) : (
          <div className="text-xs text-neutral-500">{t('loading', { defaultValue: 'Loading…' })}</div>
        )}
      </div>
    );
  }

  if (isError) {
    return (
      <div data-testid={`${testid}-error`} role="alert" className="m-2 rounded border border-red-300 bg-red-50 p-3 text-sm dark:border-red-800 dark:bg-red-950/40">
        <p className="text-red-700 dark:text-red-300">{t('motif.error.load', { defaultValue: "Couldn't load — please retry." })}</p>
        {onRetry && (
          <button
            type="button"
            data-testid={`${testid}-retry`}
            className="mt-2 rounded border border-red-400 px-2 py-0.5 text-xs text-red-700 hover:bg-red-100 dark:text-red-300 dark:hover:bg-red-900/40"
            onClick={onRetry}
          >
            {t('motif.action.retry', { defaultValue: 'Retry' })}
          </button>
        )}
      </div>
    );
  }

  if (permissionLocked) {
    return (
      <div data-testid={`${testid}-locked`} className="m-2 rounded border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950/30">
        <p className="text-amber-800 dark:text-amber-200">
          {t('motif.permission.readOnly', { defaultValue: 'This is a shared template — clone it to make your own editable copy.' })}
        </p>
        {onClone && (
          <button
            type="button"
            data-testid={`${testid}-clone`}
            className="mt-2 rounded bg-amber-600 px-2 py-1 text-xs font-medium text-white hover:bg-amber-700"
            onClick={onClone}
          >
            {t('motif.action.cloneToEdit', { defaultValue: 'Clone to edit' })}
          </button>
        )}
        <div className="mt-2 opacity-70">{children}</div>
      </div>
    );
  }

  return <>{children}</>;
}
