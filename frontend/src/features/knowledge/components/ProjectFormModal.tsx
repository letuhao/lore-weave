import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { FormDialog } from '@/components/shared';
import { BookPicker } from '@/components/shared/BookPicker';
import { useChatCapabilities } from '@/features/chat-ai-settings/hooks/useChatCapabilities';
import { isVersionConflict } from '../api';
import type {
  Project,
  ProjectCreatePayload,
  ProjectType,
  ProjectUpdatePayload,
} from '../types';
import { EmbeddingModelPicker } from './EmbeddingModelPicker';
import { RerankModelPicker } from './RerankModelPicker';

// Caps mirror the backend Pydantic StringConstraints in
// services/knowledge-service/app/db/models.py. Keeping them in sync
// gives users immediate feedback instead of a 422 round-trip.
const NAME_MAX = 200;
const DESCRIPTION_MAX = 2000;
const INSTRUCTIONS_MAX = 20000;
const GENRE_MAX = 100;

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
  /** D-KG-NO-CREATE-CTA: a caller that already knows WHICH book this project is
   *  for (e.g. a book-scoped studio panel's "no project yet" empty state) locks
   *  the BookPicker to that book instead of leaving it open to any book — the
   *  whole reason the caller is showing this form is "create the KG for THIS
   *  book". Create mode only; ignored in edit mode (book_id is edited via the
   *  normal picker there). */
  initialBookId?: string;
}

export function ProjectFormModal({
  open,
  onOpenChange,
  mode,
  project,
  onCreate,
  onUpdate,
  initialBookId,
}: Props) {
  const { t } = useTranslation('knowledge');
  // D-WS4C-EFFECTIVE-VALUE — the deploy-tier ceiling on canon capture. The user
  // knob below is only HALF the story: `effective = deploy_allows && knob`. A
  // deployment can kill-switch capture platform-wide, so we surface that here
  // instead of letting the toggle silently do nothing. Unknown (null / fetch
  // failed) ⇒ assume allowed — the ceiling defaults on, so a transient outage
  // must not fabricate a "disabled by deployment" warning.
  const { capabilities } = useChatCapabilities();
  const canonCaptureDeployAllows = capabilities?.canon_capture?.deploy_allows !== false;
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [projectType, setProjectType] = useState<ProjectType>('general');
  const [instructions, setInstructions] = useState('');
  const [bookId, setBookId] = useState('');
  const [genre, setGenre] = useState('');
  // K12.4: embedding_model is edit-only — switching it mid-extraction
  // is a rebuild-worthy change, so we expose it on the edit form but
  // not on create (new projects have no extracted data yet).
  const [embeddingModel, setEmbeddingModel] = useState<string | null>(null);
  const [initialEmbeddingModel, setInitialEmbeddingModel] = useState<string | null>(null);
  // D-RERANK-NOT-BYOK (S0b): per-project BYOK rerank model — edit-only, like
  // embedding_model. null ⇒ raw-search skips rerank.
  const [rerankModel, setRerankModel] = useState<string | null>(null);
  const [initialRerankModel, setInitialRerankModel] = useState<string | null>(null);
  // K21-C (D3/D4): per-project memory-tool toggles. Edit-only (like
  // embedding_model) — they govern the chat tool loop, which is
  // meaningless on a project with no chat history yet. Both mirror
  // the boolean-toggle pattern used elsewhere in the project UI.
  const [toolCallingEnabled, setToolCallingEnabled] = useState(true);
  const [memoryRememberConfirm, setMemoryRememberConfirm] = useState(false);
  // WS-4C Half A — opt-in: each capture is an LLM call billed to the user's own model.
  const [canonCaptureEnabled, setCanonCaptureEnabled] = useState(false);
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
      setGenre(project.genre ?? '');
      setEmbeddingModel(project.embedding_model);
      setInitialEmbeddingModel(project.embedding_model);
      setRerankModel(project.rerank_model);
      setInitialRerankModel(project.rerank_model);
      setToolCallingEnabled(project.tool_calling_enabled);
      setMemoryRememberConfirm(project.memory_remember_confirm);
      setCanonCaptureEnabled(project.canon_capture_enabled);
      setBaselineVersion(project.version);
    } else {
      setName('');
      setDescription('');
      setProjectType(initialBookId ? 'book' : 'general');
      setInstructions('');
      setBookId(initialBookId ?? '');
      setGenre('');
      setEmbeddingModel(null);
      setInitialEmbeddingModel(null);
      setRerankModel(null);
      setInitialRerankModel(null);
      setToolCallingEnabled(true);
      setMemoryRememberConfirm(false);
      setCanonCaptureEnabled(false);
      setBaselineVersion(null);
    }
  }, [open, mode, project, initialBookId]);

  const trimmedName = name.trim();
  const trimmedDescription = description.trim();
  const trimmedInstructions = instructions.trim();
  const trimmedGenre = genre.trim();
  const nameValid = trimmedName.length >= 1 && trimmedName.length <= NAME_MAX;
  const descriptionValid = description.length <= DESCRIPTION_MAX;
  const instructionsValid = instructions.length <= INSTRUCTIONS_MAX;
  const genreValid = trimmedGenre.length <= GENRE_MAX;
  const bookIdValid = bookId === '' || /^[0-9a-f-]{36}$/i.test(bookId);
  const canSave = nameValid && descriptionValid && instructionsValid && genreValid && bookIdValid && !saving;

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
          genre: trimmedGenre || null,
        });
      } else if (project && baselineVersion != null) {
        const patch: ProjectUpdatePayload = {
          name: trimmedName,
          description: trimmedDescription,
          instructions: trimmedInstructions,
          book_id: bookIdPayload,
          genre: trimmedGenre || null,
          // K21-C (D3/D4): always send the memory-tool toggles on
          // edit — they're plain form fields like name/description.
          tool_calling_enabled: toolCallingEnabled,
          memory_remember_confirm: memoryRememberConfirm,
          // WS-4C Half A — same plain-form-field treatment as the two above.
          canon_capture_enabled: canonCaptureEnabled,
        };
        // K12.4: include embedding_model only when the user changed it.
        // Omitting the field leaves the column unchanged on the backend
        // (ProjectUpdate.model_dump(exclude_unset=True) pattern).
        if (embeddingModel !== initialEmbeddingModel) {
          patch.embedding_model = embeddingModel;
        }
        // D-RERANK-NOT-BYOK (S0b): include rerank_model only when changed.
        if (rerankModel !== initialRerankModel) {
          patch.rerank_model = rerankModel;
        }
        await onUpdate(project.project_id, patch, baselineVersion);
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
          <span className="text-xs font-medium text-muted-foreground">{t('projects.form.genre', { defaultValue: 'Genre' })}</span>
          <input
            type="text"
            value={genre}
            onChange={(e) => setGenre(e.target.value)}
            maxLength={GENRE_MAX}
            className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring"
            placeholder={t('projects.form.genrePlaceholder', { defaultValue: 'e.g. Tiên hiệp, Cultivation, Fantasy…' })}
          />
          {!genreValid && (
            <span className="text-[11px] text-destructive">
              {t('projects.form.genreError', { max: GENRE_MAX, defaultValue: `Genre must be at most ${GENRE_MAX} characters.` })}
            </span>
          )}
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            {t('projects.form.bookId')}
          </span>
          {mode === 'create' && initialBookId ? (
            // D-KG-NO-CREATE-CTA: opened from that book's own "no project yet"
            // empty state — locked, not just pre-filled, so the create action
            // can't accidentally attach the new project to a different book.
            <p
              data-testid="project-form-book-locked"
              className="rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
            >
              {t('projects.form.bookIdLocked', { defaultValue: 'This book (locked)' })}
            </p>
          ) : (
            // C4 (BL-3/G6): pick a book by title — no raw UUID. Empty stays valid
            // (book optional); the stored value is the book_id.
            <BookPicker
              value={bookId === '' ? null : bookId}
              onChange={(id) => setBookId(id ?? '')}
              placeholder={t('projects.form.bookIdPlaceholder', { defaultValue: 'Search your books by title…' })}
            />
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

        {/* K12.4: embedding model is edit-only. Create flow keeps the
            form minimal; users pick a model after the project exists.
            T2-close-1b-FE: project.project_id lets the picker fetch
            the K17.9 benchmark-status badge for the selected model. */}
        {mode === 'edit' && (
          <EmbeddingModelPicker
            value={embeddingModel}
            onChange={setEmbeddingModel}
            disabled={saving}
            projectId={project?.project_id}
          />
        )}

        {/* D-RERANK-NOT-BYOK (S0b): per-project BYOK rerank model — edit-only,
            mirroring the embedding picker. Optional: empty ⇒ raw-search skips rerank. */}
        {mode === 'edit' && (
          <RerankModelPicker
            value={rerankModel}
            onChange={setRerankModel}
            disabled={saving}
          />
        )}

        {/* K21-C (D3/D4): memory-tool toggles — edit-only, mirroring
            the embedding-model picker's edit-only placement. */}
        {mode === 'edit' && (
          <div className="flex flex-col gap-2 border-t pt-3">
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={toolCallingEnabled}
                onChange={(e) => setToolCallingEnabled(e.target.checked)}
                disabled={saving}
                className="mt-0.5 h-3.5 w-3.5 rounded border"
                data-testid="project-tool-calling-toggle"
              />
              <span className="flex flex-col gap-0.5">
                <span className="font-medium text-foreground">
                  {t('projects.form.toolCalling', { defaultValue: 'Memory tools in chat' })}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {t('projects.form.toolCallingHint', {
                    defaultValue:
                      'Let the AI search, recall, and note memory while chatting in this project.',
                  })}
                </span>
              </span>
            </label>

            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={memoryRememberConfirm}
                onChange={(e) => setMemoryRememberConfirm(e.target.checked)}
                disabled={saving || !toolCallingEnabled}
                className="mt-0.5 h-3.5 w-3.5 rounded border"
                data-testid="project-memory-confirm-toggle"
              />
              <span className="flex flex-col gap-0.5">
                <span className="font-medium text-foreground">
                  {t('projects.form.memoryConfirm', {
                    defaultValue: 'Confirm before saving memories',
                  })}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {t('projects.form.memoryConfirmHint', {
                    defaultValue:
                      'Facts the AI wants to remember wait for your approval instead of saving automatically.',
                  })}
                </span>
              </span>
            </label>

            {/* WS-4C Half A — canon auto-capture. OPT-IN: every capture is an LLM call
                billed to the user's own model, so the hint says so plainly rather than
                letting the cost be a surprise. Needs a linked book (there is no glossary
                inbox without one), which mirrors the backend's `no_book` gate. */}
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={canonCaptureEnabled}
                onChange={(e) => setCanonCaptureEnabled(e.target.checked)}
                disabled={saving || !bookId}
                className="mt-0.5 h-3.5 w-3.5 rounded border"
                data-testid="project-canon-capture-toggle"
              />
              <span className="flex flex-col gap-0.5">
                <span className="font-medium text-foreground">
                  {t('projects.form.canonCapture', {
                    defaultValue: 'Auto-capture new names from chat',
                  })}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {bookId
                    ? t('projects.form.canonCaptureHint', {
                        defaultValue:
                          'Every few turns, names your conversation introduces are added to this book’s glossary review inbox as suggestions — never as canon. Uses one extra AI call per capture, billed to your own model.',
                      })
                    : t('projects.form.canonCaptureNoBook', {
                        defaultValue:
                          'Link a book to this project to capture names into its glossary.',
                      })}
                </span>
                {/* D-WS4C-EFFECTIVE-VALUE — the honest effective value + source. When
                    the deployment kill-switches capture off, the knob above CAN'T take
                    effect (effective = deploy_allows && knob). We say so plainly and
                    keep the user's choice saved for when it's re-enabled, rather than
                    letting the toggle read "on" while nothing captures. */}
                {bookId && !canonCaptureDeployAllows && (
                  <span
                    className="text-[11px] font-medium text-amber-600 dark:text-amber-500"
                    data-testid="project-canon-capture-ceiling-off"
                  >
                    {t('projects.form.canonCaptureCeilingOff', {
                      defaultValue:
                        'Turned off for this deployment — your choice is saved, but capture won’t run until an administrator re-enables it.',
                    })}
                  </span>
                )}
              </span>
            </label>
          </div>
        )}
      </div>
    </FormDialog>
  );
}
