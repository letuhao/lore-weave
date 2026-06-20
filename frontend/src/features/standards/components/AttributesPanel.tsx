import { useTranslation } from 'react-i18next';

/** Attributes tab — built in M2 (user attrs per kind×genre + system read-only). */
export function AttributesPanel() {
  const { t } = useTranslation('standards');
  return (
    <p className="py-6 text-sm text-muted-foreground" data-testid="standards-attributes">
      {t('attributes.placeholder')}
    </p>
  );
}
