import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { FormDialog } from '@/components/shared';
import { isVersionConflict } from '../api';
import type {
  Project,
  ProjectCreatePayload,
  ProjectType,
  ProjectUpdatePayload,
} from '../types';

// Caps mirror the backend Pydantic StringConstraints in
// services/knowledge-service/app/db/models.py. Keeping them in sync
// gives users immediate feedback instead of a 422 round-trip.
const NAME_MAX = 200;
const DESCRIPTION_MAX = 2000;
const INSTRUCTIONS_MAX = 20000;

const PROJECT_TYPE_VALUES: ProjectType[] = ['book', 'translation', 'code', 'general'];

type Mode = 'create' | 'edit';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: Mode;
  project?: Project | null;
  onCreate: (payload: ProjectCreatePayload) => Promise<Project>;
  // D-K8-03: update passes the expected version captured at open time.
  onUpdate: (
    projectId: string,
    payload: ProjectUpdatePayload,
    expectedVersion: number,
  ) => Promise<Project>;
}

export function ProjectFormModal({
  open,
  onOpenChange,
  mode,
  project,
  onCreate,
  onUpdate,
}: Props) {
  const { t } = useTranslation('memory');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [projectType, setProjectType] = useState<ProjectType>('general');
  const [instructions, setInstructions] = useState('');
  const [bookId, setBookId] = useState('');
  const [saving, setSaving] = useState(false);
  // D-K8-03: track the version at dialog open time so we can send it
  // back in If-Match on save. Updated on 412 so the user can retry
  // against the fresh row without closing the dialog.
  const [baselineVersion, setBaselineVersion] = useState<number | null>(null);
  // K8.2-R2: track whether the dialog is still open when an in-flight
  // save resolves. If the user hit Cancel/X mid-save we skip the
  // success toast and the stray setState — the action was effectively
  // abandoned from their POV. Errors still toast so they know a
  // background save failed.
  const openRef = useRef(open);
  useEffect(() => {
    openRef.current = open;
  }, [open]);

  // Reset form whenever the dialog opens — either to the project's
  // current values (edit) or to defaults (create). Keeping this in
  // useEffect instead of re-keying the dialog means the unmount
  // animation plays cleanly when it closes.
  useEffect(() => {
    if (!open) return;
    if (mode === 'edit' && project) {
      setName(project.name);
      setDescription(project.description);
      setProjectType(project.project_type);
      setInstructions(project.instructions);
      setBookId(project.book_id ?? '');
      setBaselineVersion(project.version);
    } else {
      setName('');
      setDescription('');
      setProjectType('general');
      setInstructions('');
      setBookId('');
      setBaselineVersion(null);
    }
  }, [open, mode, project]);

  const trimmedName = name.trim();
  const trimmedDescription = description.trim();
  const trimmedInstructions = instructions.trim();
  const nameValid = trimmedName.length >= 1 && trimmedName.length <= NAME_MAX;
  const descriptionValid = description.length <= DESCRIPTION_MAX;
  const instructionsValid = instructions.length <= INSTRUCTIONS_MAX;
  const bookIdValid = bookId === '' || /^[0-9a-f-]{36}$/i.test(bookId);
  const canSave = nameValid && descriptionValid && instructionsValid && bookIdValid && !saving;

  const handleSubmit = async () => {
    if (!canSave) return;
    setSaving(true);
    // K8.2-R4: unified book_id null handling — empty string ⇒ null,
    // validated UUID ⇒ verbatim. Same rule in both create and edit.
    const bookIdPayload = bookId === '' ? null : bookId;
    try {
      if (mode === 'create') {
        await onCreate({
          name: trimmedName,
          description: trimmedDescription,
          project_type: projectType,
          instructions: trimmedInstructions,
          book_id: bookIdPayload,
        });
      } else if (project && baselineVersion != null) {
        await onUpdate(
          project.project_id,
          {
            name: trimmedName,
            description: trimmedDescription,
            instructions: trimmedInstructions,
            book_id: bookIdPayload,
          },
          baselineVersion,
        );
      }
      if (openRef.current) {
        toast.success(
          mode === 'create'
            ? t('projects.toast.created', { defaultValue: 'Project created' })
            : t('projects.toast.updated', { defaultValue: 'Project updated' }),
        );
        onOpenChange(false);
      }
    } catch (err) {
      // D-K8-03: 412 Precondition Failed — another device modified
      // the project since this dialog opened. Refresh the baseline
      // to the fresh server state and keep the dialog open so the
      // user can review the diff and retry. We deliberately do NOT
      // overwrite the form fields — the user's edits are preserved
      // so they can re-apply them on top of the fresh row.
      if (isVersionConflict<Project>(err)) {
        setBaselineVersion(err.current.version);
        toast.error(
          t('projects.toast.conflict', {
            defaultValue:
              'Another device modified this project. Review the latest and save again.',
          }),
        );
      } else {
        const msg = err instanceof Error ? err.message : 'Save failed';
        toast.error(msg);
      }
    } finally {
      if (openRef.current) setSaving(false);
    }
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={mode === 'create' ? t('projects.form.createTitle') : t('projects.form.editTitle')}
      description={
        mode === 'create' ? t('projects.form.createDescription') : undefined
      }
      footer={
        <>
          <button
            onClick={() => onOpenChange(false)}
            className="rounded-md border px-3 py-1.5 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            {t('projects.form.cancel')}
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSave}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {saving
              ? t('global.saving')
              : mode === 'create'
                ? t('projects.form.create')
                : t('projects.form.save')}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">{t('projects.form.name')}</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={NAME_MAX}
            className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring"
            placeholder={t('projects.form.namePlaceholder')}
          />
          {!nameValid && name.length > 0 && (
            <span className="text-[11px] text-destructive">
              {t('projects.form.nameError', { max: NAME_MAX, defaultValue: `Name must be 1–${NAME_MAX} characters.` })}
            </span>
          )}
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">{t('projects.form.type')}</span>
          <select
            value={projectType}
            onChange={(e) => setProjectType(e.target.value as ProjectType)}
            disabled={mode === 'edit'}
            className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring disabled:opacity-60"
          >
            {PROJECT_TYPE_VALUES.map((value) => (
              <option key={value} value={value}>
                {t(`projects.form.typeOptions.${value}`)}
              </option>
            ))}
          </select>
          {mode === 'edit' && (
            <span className="text-[11px] text-muted-foreground">
              {t('projects.form.typeImmutable')}
            </span>
          )}
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            {t('projects.form.bookId')}
          </span>
          <input
            type="text"
            value={bookId}
            onChange={(e) => setBookId(e.target.value)}
            className="rounded-md border bg-input px-3 py-2 font-mono text-xs outline-none focus:border-ring"
            placeholder={t('projects.form.bookIdPlaceholder')}
          />
          {!bookIdValid && (
            <span className="text-[11px] text-destructive">
              {t('projects.form.bookIdError', { defaultValue: 'Must be a valid UUID.' })}
            </span>
          )}
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            {t('projects.form.description')}
          </span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={DESCRIPTION_MAX}
            rows={3}
            className="resize-y rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring"
          />
          <span className="text-right text-[11px] text-muted-foreground">
            {description.length} / {DESCRIPTION_MAX}
          </span>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            {t('projects.form.instructions')}
          </span>
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            maxLength={INSTRUCTIONS_MAX}
            rows={5}
            className="resize-y rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring"
            placeholder={t('projects.form.instructionsPlaceholder')}
          />
          <span className="text-right text-[11px] text-muted-foreground">
            {instructions.length} / {INSTRUCTIONS_MAX}
          </span>
        </label>
      </div>
    </FormDialog>
  );
}
