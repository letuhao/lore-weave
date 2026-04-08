import { useTranslation } from 'react-i18next';

type Props = { label: string };

export function StubTab({ label }: Props) {
  const { t } = useTranslation('profile');
  return (
    <div className="py-12 text-center">
      <div className="text-3xl mb-3 opacity-40">🚧</div>
      <p className="text-sm text-[var(--muted-fg)]">{t('comingSoon', { feature: label })}</p>
    </div>
  );
}
