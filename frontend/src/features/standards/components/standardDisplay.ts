import type { TFunction } from 'i18next';

export function standardName(
  t: TFunction,
  kind: 'genre' | 'kind' | 'attribute',
  code: string,
  fallback: string,
  system: boolean,
): string {
  if (!system) return fallback;
  return t('system.' + kind + 's.' + code + '.name', { defaultValue: fallback });
}

export function standardDescription(
  t: TFunction,
  kind: 'genre' | 'kind' | 'attribute',
  code: string,
  fallback: string | null | undefined,
  system: boolean,
): string | null {
  if (!system) return fallback ?? null;
  const value = t('system.' + kind + 's.' + code + '.description', { defaultValue: fallback ?? '' });
  return value || null;
}
