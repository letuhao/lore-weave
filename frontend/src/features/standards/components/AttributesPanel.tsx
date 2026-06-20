import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { FieldTypeBadge } from '@/features/glossary/components/tiering/FieldTypeBadge';
import { TierChip } from '@/features/glossary/components/tiering/TierChip';
import type { Attribute } from '@/features/glossary/tieringTypes';
import { useUserStandards } from '../hooks/useUserStandards';
import { useStandardAttributes } from '../hooks/useStandardAttributes';
import { AttributeFormModal, type AttributeFormValues } from './AttributeFormModal';

/** Attributes tab — manage user attributes for a (user-kind × user-genre) pair. */
export function AttributesPanel() {
  const { t } = useTranslation('standards');
  const { genres, kinds } = useUserStandards();
  const userKinds = useMemo(() => kinds.filter((k) => k.tier === 'user'), [kinds]);
  const userGenres = useMemo(() => genres.filter((g) => g.tier === 'user'), [genres]);

  const [kindId, setKindId] = useState('');
  const [genreId, setGenreId] = useState('');
  const [creating, setCreating] = useState(false);

  const selKind = userKinds.find((k) => k.id === kindId) ?? null;
  const selGenre = userGenres.find((g) => g.genre_id === genreId) ?? null;

  const { userAttrs, systemAttrs, hasSystemParent, isLoading, createAttr } = useStandardAttributes({
    userKindId: selKind?.id ?? null,
    userGenreId: selGenre?.genre_id ?? null,
    systemKindId: selKind?.clonedFromKindId ?? null,
    systemGenreId: selGenre?.cloned_from_genre_id ?? null,
  });

  const onCreate = async (vals: AttributeFormValues) => {
    await createAttr.mutateAsync(
      { kind_id: selKind!.id, genre_id: selGenre!.genre_id, ...vals },
      {
        onSuccess: () => toast.success(t('toast.attrCreated', { name: vals.name })),
        onError: () => toast.error(t('toast.attrError', { name: vals.name })),
      },
    );
  };

  if (userKinds.length === 0 || userGenres.length === 0) {
    return (
      <p className="py-6 text-sm text-muted-foreground" data-testid="standards-attributes">
        {userKinds.length === 0 ? t('attributes.no_user_kinds') : t('attributes.no_user_genres')}
      </p>
    );
  }

  const pairChosen = !!selKind && !!selGenre;

  return (
    <div data-testid="standards-attributes" className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="space-y-1">
          <span className="block text-xs font-medium text-muted-foreground">{t('tab.kinds')}</span>
          <select value={kindId} onChange={(e) => setKindId(e.target.value)} className="rounded-md border bg-background px-2.5 py-1.5 text-sm" data-testid="attr-pick-kind">
            <option value="">{t('attributes.pick_kind')}</option>
            {userKinds.map((k) => <option key={k.id} value={k.id}>{k.icon} {k.name}</option>)}
          </select>
        </label>
        <label className="space-y-1">
          <span className="block text-xs font-medium text-muted-foreground">{t('tab.genres')}</span>
          <select value={genreId} onChange={(e) => setGenreId(e.target.value)} className="rounded-md border bg-background px-2.5 py-1.5 text-sm" data-testid="attr-pick-genre">
            <option value="">{t('attributes.pick_genre')}</option>
            {userGenres.map((g) => <option key={g.genre_id} value={g.genre_id}>{g.icon} {g.name}</option>)}
          </select>
        </label>
        {pairChosen && (
          <button onClick={() => setCreating(true)} className="inline-flex items-center gap-1 rounded border px-2.5 py-1.5 text-[12px] font-medium hover:bg-secondary" data-testid="attr-new">
            <Plus className="h-3.5 w-3.5" />
            {t('attributes.new')}
          </button>
        )}
      </div>

      {!pairChosen ? (
        <p className="text-sm text-muted-foreground">{t('attributes.pick_both')}</p>
      ) : (
        <>
          {hasSystemParent && systemAttrs.length > 0 && (
            <section>
              <h3 className="mb-1.5 text-xs font-semibold text-muted-foreground">{t('attributes.system_ref')}</h3>
              <ul className="space-y-1">{systemAttrs.map((a) => <AttrRow key={a.attr_id} a={a} />)}</ul>
            </section>
          )}
          <section>
            <h3 className="mb-1.5 text-xs font-semibold text-muted-foreground">{t('attributes.your_attrs')}</h3>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">{t('loading')}</p>
            ) : userAttrs.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('attributes.empty')}</p>
            ) : (
              <ul className="space-y-1" data-testid="user-attrs">{userAttrs.map((a) => <AttrRow key={a.attr_id} a={a} />)}</ul>
            )}
          </section>
        </>
      )}

      {creating && (
        <AttributeFormModal mode="create" onSubmit={onCreate} onClose={() => setCreating(false)} />
      )}
    </div>
  );
}

function AttrRow({ a }: { a: Attribute }) {
  return (
    <li className="flex items-center gap-2 rounded-md border px-3 py-1.5" data-testid={`attr-row-${a.code}`}>
      <span className="text-[13px] font-medium">{a.name}</span>
      <code className="text-[11px] text-muted-foreground">{a.code}</code>
      <FieldTypeBadge fieldType={a.field_type} />
      {a.is_required && <span className="text-[10px] font-semibold text-destructive">*</span>}
      <TierChip tier={a.tier} className="ml-auto" />
    </li>
  );
}
