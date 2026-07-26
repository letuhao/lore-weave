import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ProjectFormModal } from '../ProjectFormModal';
import { useProjects } from '../../hooks/useProjects';

// D-KG-NO-CREATE-CTA (2026-07-05): every book-scoped kg-* panel's "no project
// yet" empty state used to be a dead end — correct copy ("...create a project
// to manage its graph schema") with no button behind it. One shared empty
// state (DOCK-2 — no per-panel fork) so kg-overview/kg-schema/kg-graph/
// kg-gap-report all get the same fix at once. Reuses ProjectFormModal AS-IS
// (initialBookId locks the picker to this book) instead of a second,
// parallel "quick create" form that could drift from the classic one.
interface Props {
  bookId: string;
  /** Preserves each panel's own pre-existing data-testid for its empty state
   *  (kg-overview-no-project / kg-ontology-no-project / kg-gap-no-project) so
   *  this extraction doesn't churn any existing panel test. */
  testId: string;
}

export function KgNoProjectState({ bookId, testId }: Props) {
  const { t } = useTranslation('kgOntology');
  const { createProject, isMutating } = useProjects({ includeArchived: false, bookId });
  const [open, setOpen] = useState(false);

  const handleCreate = async (payload: Parameters<typeof createProject>[0]) => {
    const project = await createProject(payload);
    toast.success(
      t('page.createProject', { defaultValue: 'Create Knowledge Project' }),
    );
    return project;
  };

  return (
    <div className="rounded-lg border p-8 text-center" data-testid={testId}>
      <p className="text-sm font-medium">{t('page.noProject')}</p>
      <p className="mt-1 text-xs text-muted-foreground">{t('page.noProjectHelp')}</p>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={isMutating}
        data-testid="kg-no-project-create-btn"
        className="mt-4 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
      >
        {t('page.createProject', { defaultValue: 'Create Knowledge Project' })}
      </button>

      <ProjectFormModal
        open={open}
        onOpenChange={setOpen}
        mode="create"
        initialBookId={bookId}
        onCreate={handleCreate}
        // Edit is unreachable from create mode — a stub satisfies the shared
        // component's prop contract without pulling in an update path this
        // empty state never exercises.
        onUpdate={() => Promise.reject(new Error('not supported'))}
      />
    </div>
  );
}
