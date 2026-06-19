import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Layers } from 'lucide-react';
import { toast } from 'sonner';
import { useBookOntology } from '../../hooks/useBookOntology';
import { useStandards } from '../../hooks/useStandards';
import { tierFromSourceRef } from '../../lib/tiering';
import type { AdoptRequest } from '../../tieringTypes';
import { OntologyColumn, type ColumnRow } from './OntologyColumn';
import { AttributeEditorPanel } from './AttributeEditorPanel';
import { AdoptPicklistModal } from './AdoptPicklistModal';

/** 01-manage: the book ontology Manage workspace. Genre → kind → attribute drilldown
 *  over the book-local ontology, with adopt copy-down + book-tier attribute editing.
 *  Every book row is the book's own editable copy; the tier chip shows provenance. */
export function ManageWorkspace({ bookId }: { bookId: string }) {
  const { t } = useTranslation('glossaryTiering');
  const ont = useBookOntology(bookId);
  const standards = useStandards();
  const [genreId, setGenreId] = useState<string | null>(null);
  const [kindId, setKindId] = useState<string | null>(null);
  const [attrId, setAttrId] = useState<string | null>(null);
  const [showAdopt, setShowAdopt] = useState(false);

  const { genres, kinds, kind_genres, attributes } = ont.ontology;

  // kinds linked to the selected genre (via book_kind_genres).
  const kindRows: ColumnRow[] = useMemo(() => {
    if (!genreId) return [];
    const linked = new Set(kind_genres.filter((l) => l.genre_id === genreId).map((l) => l.kind_id));
    return kinds
      .filter((k) => linked.has(k.book_kind_id))
      .map((k) => ({ id: k.book_kind_id, icon: k.icon, label: k.name, tier: tierFromSourceRef(k.source_ref) }));
  }, [genreId, kinds, kind_genres]);

  const attrRows: ColumnRow[] = useMemo(() => {
    if (!genreId || !kindId) return [];
    return attributes
      .filter((a) => a.kind_id === kindId && a.genre_id === genreId)
      .map((a) => ({ id: a.attr_id, label: a.name, tier: tierFromSourceRef(a.source_ref), meta: a.field_type }));
  }, [genreId, kindId, attributes]);

  const genreRows: ColumnRow[] = genres.map((g) => ({
    id: g.genre_id,
    icon: g.icon,
    label: g.name,
    tier: tierFromSourceRef(g.source_ref),
    meta: t('col.count_kinds', { count: kind_genres.filter((l) => l.genre_id === g.genre_id).length }),
  }));

  const selectedAttr = attributes.find((a) => a.attr_id === attrId) ?? null;

  const guard = async (fn: () => Promise<unknown>, okMsg: string, failKey: string) => {
    try {
      await fn();
      toast.success(okMsg);
    } catch (e) {
      const msg = (e as { status?: number }).status === 403 ? t('toast.forbidden') : (e as Error).message;
      toast.error(msg || t(failKey));
    }
  };

  const adopt = (req: AdoptRequest) =>
    guard(() => ont.adopt(req), t('toast.adopted'), 'toast.adopt_failed');

  const onNewGenre = () => {
    const name = window.prompt(t('col.new_genre'));
    if (name?.trim()) void guard(() => ont.createGenre({ name: name.trim() }), t('toast.saved'), 'toast.save_failed');
  };
  const onNewKind = () => {
    const name = window.prompt(t('col.new_kind'));
    if (name?.trim()) void guard(() => ont.createKind({ name: name.trim() }), t('toast.saved'), 'toast.save_failed');
  };
  const onNewAttr = () => {
    if (!genreId || !kindId) return;
    void guard(
      () => ont.createAttribute({ kind_id: kindId, genre_id: genreId, name: 'new_attribute' }),
      t('toast.saved'),
      'toast.save_failed',
    );
  };

  if (ont.isLoading) return <p className="p-4 text-sm text-muted-foreground">{t('manage.loading')}</p>;
  if (ont.error) return <p className="p-4 text-sm text-destructive">{t('manage.load_failed')}</p>;

  if (!ont.isAdopted) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed bg-card p-10 text-center">
        <Layers className="h-8 w-8 text-muted-foreground" />
        <h3 className="text-sm font-semibold">{t('manage.not_adopted')}</h3>
        <p className="max-w-md text-xs text-muted-foreground">{t('manage.not_adopted_hint')}</p>
        <button
          onClick={() => setShowAdopt(true)}
          className="mt-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          {t('manage.adopt_cta')}
        </button>
        {showAdopt && (
          <AdoptPicklistModal
            genres={standards.genres}
            kinds={standards.kinds}
            loading={standards.isLoading}
            onAdopt={adopt}
            onClose={() => setShowAdopt(false)}
          />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">{t('manage.title')}</h2>
          <p className="text-xs text-muted-foreground">{t('manage.subtitle')}</p>
        </div>
        <button
          onClick={() => setShowAdopt(true)}
          className="flex items-center gap-1 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary"
        >
          <Plus className="h-3.5 w-3.5" /> {t('manage.adopt_more')}
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <OntologyColumn
          title={t('col.genres')}
          rows={genreRows}
          selectedId={genreId}
          onSelect={(id) => {
            setGenreId(id);
            setKindId(null);
            setAttrId(null);
          }}
          onNew={onNewGenre}
          newLabel={t('col.new_genre')}
          emptyText={t('col.select_genre')}
        />
        <OntologyColumn
          title={genreId ? t('col.kinds_in', { genre: genres.find((g) => g.genre_id === genreId)?.name ?? '' }) : t('col.kinds')}
          rows={kindRows}
          selectedId={kindId}
          onSelect={(id) => {
            setKindId(id);
            setAttrId(null);
          }}
          onNew={onNewKind}
          newLabel={t('col.new_kind')}
          emptyText={genreId ? t('col.empty_kinds') : t('col.select_genre')}
          disabled={!genreId}
        />
        <OntologyColumn
          title={t('col.attributes')}
          rows={attrRows}
          selectedId={attrId}
          onSelect={setAttrId}
          onNew={onNewAttr}
          newLabel={t('col.new_attr')}
          emptyText={kindId ? t('col.empty_attrs') : t('col.select_kind')}
          disabled={!kindId}
        />
      </div>

      <AttributeEditorPanel
        attribute={selectedAttr}
        onSave={(id, changes) => guard(() => ont.patchAttribute(id, changes), t('toast.saved'), 'toast.save_failed')}
        onDelete={(id) =>
          guard(
            async () => {
              await ont.deleteAttribute(id);
              setAttrId(null);
            },
            t('toast.deleted'),
            'toast.delete_failed',
          )
        }
      />

      {showAdopt && (
        <AdoptPicklistModal
          genres={standards.genres}
          kinds={standards.kinds}
          loading={standards.isLoading}
          onAdopt={adopt}
          onClose={() => setShowAdopt(false)}
        />
      )}
    </div>
  );
}
