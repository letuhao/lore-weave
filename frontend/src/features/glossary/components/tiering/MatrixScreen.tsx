import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useBookOntology } from '../../hooks/useBookOntology';
import { KindSelect } from './KindSelect';
import { ActiveGenrePills } from './ActiveGenrePills';
import { AttributeMatrix, type CellRef } from './AttributeMatrix';
import { MatrixCellInspector } from './MatrixCellInspector';

/** 02-attribute-matrix screen: one kind's attributes across the book's active genres. */
export function MatrixScreen({ bookId }: { bookId: string }) {
  const { t } = useTranslation('glossaryTiering');
  const ont = useBookOntology(bookId);
  const [kindId, setKindId] = useState<string | null>(null);
  const [cell, setCell] = useState<CellRef | null>(null);

  const { genres, kinds, attributes } = ont.ontology;

  // Default to the first kind once the ontology loads.
  useEffect(() => {
    if (!kindId && kinds.length > 0) setKindId(kinds[0].book_kind_id);
  }, [kinds, kindId]);

  const activeGenres = useMemo(() => genres.filter((g) => g.active), [genres]);
  const kindAttrs = useMemo(
    () => attributes.filter((a) => a.kind_id === kindId),
    [attributes, kindId],
  );

  const cellAttr = cell ? kindAttrs.find((a) => a.code === cell.code && a.genre_id === cell.genreId) ?? null : null;
  const cellGenre = cell ? genres.find((g) => g.genre_id === cell.genreId) ?? null : null;

  const setActive = async (ids: string[]) => {
    try {
      await ont.setActiveGenres(ids);
      toast.success(t('toast.saved'));
    } catch (e) {
      const msg = (e as { status?: number }).status === 403 ? t('toast.forbidden') : (e as Error).message;
      toast.error(msg || t('toast.save_failed'));
    }
  };

  if (ont.isLoading) return <p className="p-4 text-sm text-muted-foreground">{t('manage.loading')}</p>;
  if (!ont.isAdopted) return <p className="p-4 text-sm text-muted-foreground">{t('manage.not_adopted')}</p>;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold">{t('matrix.title')}</h2>
        <p className="text-xs text-muted-foreground">{t('matrix.subtitle')}</p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <KindSelect kinds={kinds} value={kindId} onChange={(id) => { setKindId(id); setCell(null); }} />
        <ActiveGenrePills genres={genres} onSetActive={setActive} />
      </div>

      {kindId ? (
        <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
          <AttributeMatrix
            activeGenres={activeGenres}
            attributes={kindAttrs}
            selectedCell={cell}
            onSelectCell={setCell}
          />
          <MatrixCellInspector attribute={cellAttr} genre={cellGenre} />
        </div>
      ) : (
        <p className="rounded-lg border bg-card p-6 text-center text-xs text-muted-foreground">{t('matrix.select_kind')}</p>
      )}
    </div>
  );
}
