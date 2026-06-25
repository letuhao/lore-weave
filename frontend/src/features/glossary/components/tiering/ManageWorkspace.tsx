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
import { QuickCreateModal, type QuickCreatePayload } from './QuickCreateModal';
import { ConfirmDialog } from '@/components/shared';
import { KindResearchPanel } from './KindResearchPanel';

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
  const [quickCreate, setQuickCreate] = useState<'genre' | 'kind' | null>(null);
  const [editTarget, setEditTarget] = useState<{
    type: 'genre' | 'kind';
    id: string;
    initial: { name: string; icon?: string; color?: string };
  } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<{ type: 'genre' | 'kind'; id: string; name: string } | null>(null);

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

  const onQuickCreate = (payload: QuickCreatePayload) =>
    quickCreate === 'genre'
      ? guard(() => ont.createGenre(payload), t('toast.saved'), 'toast.save_failed')
      : guard(() => ont.createKind(payload), t('toast.saved'), 'toast.save_failed');

  // Open the settings modal for a row, seeded from the live ontology (so the
  // colour swatch + icon reflect the current value, not a stale row prop).
  const openEditGenre = (id: string) => {
    const g = genres.find((x) => x.genre_id === id);
    if (g) setEditTarget({ type: 'genre', id, initial: { name: g.name, icon: g.icon, color: g.color } });
  };
  const openEditKind = (id: string) => {
    const k = kinds.find((x) => x.book_kind_id === id);
    if (k) setEditTarget({ type: 'kind', id, initial: { name: k.name, icon: k.icon, color: k.color } });
  };
  // Patch name/icon/color of the edited row. Code is the stable key (not sent).
  const onEditSubmit = (payload: QuickCreatePayload) => {
    if (!editTarget) return Promise.resolve();
    const changes = { name: payload.name, icon: payload.icon ?? '', color: payload.color };
    return editTarget.type === 'genre'
      ? guard(() => ont.patchGenre(editTarget.id, changes), t('toast.saved'), 'toast.save_failed')
      : guard(() => ont.patchKind(editTarget.id, changes), t('toast.saved'), 'toast.save_failed');
  };
  const onNewAttr = () => {
    if (!genreId || !kindId) return;
    void guard(
      () => ont.createAttribute({ kind_id: kindId, genre_id: genreId, name: 'new_attribute' }),
      t('toast.saved'),
      'toast.save_failed',
    );
  };

  // Genre/kind delete cascades server-side (deprecates attributes + kind links), so it
  // goes through a destructive confirm. On success, clear any selection that pointed at
  // the now-deleted row so the drilldown doesn't show a stale parent.
  const onConfirmDelete = () => {
    if (!confirmDelete) return;
    const { type, id } = confirmDelete;
    void guard(
      async () => {
        if (type === 'genre') {
          await ont.deleteGenre(id);
          if (genreId === id) {
            setGenreId(null);
            setKindId(null);
            setAttrId(null);
          }
        } else {
          await ont.deleteKind(id);
          if (kindId === id) {
            setKindId(null);
            setAttrId(null);
          }
        }
      },
      t('toast.deleted'),
      'toast.delete_failed',
    );
    setConfirmDelete(null);
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
          onNew={() => setQuickCreate('genre')}
          newLabel={t('col.new_genre')}
          emptyText={t('col.select_genre')}
          onEdit={(r) => openEditGenre(r.id)}
          editLabel={t('col.edit_genre')}
          onDelete={(r) => setConfirmDelete({ type: 'genre', id: r.id, name: r.label })}
          deleteLabel={t('col.delete_genre')}
        />
        <OntologyColumn
          title={genreId ? t('col.kinds_in', { genre: genres.find((g) => g.genre_id === genreId)?.name ?? '' }) : t('col.kinds')}
          rows={kindRows}
          selectedId={kindId}
          onSelect={(id) => {
            setKindId(id);
            setAttrId(null);
          }}
          onNew={() => setQuickCreate('kind')}
          newLabel={t('col.new_kind')}
          emptyText={genreId ? t('col.empty_kinds') : t('col.select_genre')}
          disabled={!genreId}
          onEdit={(r) => openEditKind(r.id)}
          editLabel={t('col.edit_kind')}
          onDelete={(r) => setConfirmDelete({ type: 'kind', id: r.id, name: r.label })}
          deleteLabel={t('col.delete_kind')}
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
        onRevert={(id) => guard(() => ont.revertAttribute(id), t('toast.reverted'), 'toast.revert_failed')}
      />

      {/* D-BATCH-RESEARCH-JOB — batch web-research over all entities of the selected kind. */}
      {kindId && (
        <KindResearchPanel
          bookId={bookId}
          kindId={kindId}
          kindName={kinds.find((k) => k.book_kind_id === kindId)?.name ?? ''}
        />
      )}

      {showAdopt && (
        <AdoptPicklistModal
          genres={standards.genres}
          kinds={standards.kinds}
          loading={standards.isLoading}
          onAdopt={adopt}
          onClose={() => setShowAdopt(false)}
        />
      )}

      {quickCreate && (
        <QuickCreateModal
          kind={quickCreate}
          onCreate={onQuickCreate}
          onClose={() => setQuickCreate(null)}
        />
      )}

      {editTarget && (
        <QuickCreateModal
          kind={editTarget.type}
          mode="edit"
          initial={editTarget.initial}
          onCreate={onEditSubmit}
          onClose={() => setEditTarget(null)}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          open
          onOpenChange={(o) => {
            if (!o) setConfirmDelete(null);
          }}
          variant="destructive"
          title={t(confirmDelete.type === 'genre' ? 'del.genre_title' : 'del.kind_title', {
            name: confirmDelete.name,
          })}
          description={t(confirmDelete.type === 'genre' ? 'del.genre_body' : 'del.kind_body')}
          confirmLabel={t('del.confirm')}
          cancelLabel={t('del.cancel')}
          onConfirm={onConfirmDelete}
        />
      )}
    </div>
  );
}
