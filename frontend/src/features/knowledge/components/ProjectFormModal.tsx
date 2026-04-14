import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { FormDialog } from '@/components/shared';
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

const PROJECT_TYPES: { value: ProjectType; label: string }[] = [
  { value: 'book', label: 'Book' },
  { value: 'translation', label: 'Translation' },
  { value: 'code', label: 'Code' },
  { value: 'general', label: 'General' },
];

type Mode = 'create' | 'edit';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: Mode;
  project?: Project | null;
  onCreate: (payload: ProjectCreatePayload) => Promise<Project>;
  onUpdate: (projectId: string, payload: ProjectUpdatePayload) => Promise<Project>;
}

export function ProjectFormModal({
  open,
  onOpenChange,
  mode,
  project,
  onCreate,
  onUpdate,
}: Props) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [projectType, setProjectType] = useState<ProjectType>('general');
  const [instructions, setInstructions] = useState('');
  const [bookId, setBookId] = useState('');
  const [saving, setSaving] = useState(false);
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
    } else {
      setName('');
      setDescription('');
      setProjectType('general');
      setInstructions('');
      setBookId('');
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
      } else if (project) {
        await onUpdate(project.project_id, {
          name: trimmedName,
          description: trimmedDescription,
          instructions: trimmedInstructions,
          book_id: bookIdPayload,
        });
      }
      if (openRef.current) {
        toast.success(mode === 'create' ? 'Project created' : 'Project updated');
        onOpenChange(false);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Save failed';
      toast.error(msg);
    } finally {
      if (openRef.current) setSaving(false);
    }
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title={mode === 'create' ? 'New project' : 'Edit project'}
      description={
        mode === 'create'
          ? 'A project scopes what the AI remembers for a specific piece of work.'
          : undefined
      }
      footer={
        <>
          <button
            onClick={() => onOpenChange(false)}
            className="rounded-md border px-3 py-1.5 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSave}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {saving ? 'Saving…' : mode === 'create' ? 'Create' : 'Save'}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">Name</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={NAME_MAX}
            className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring"
            placeholder="e.g. Winds of the Eastern Sea"
          />
          {!nameValid && name.length > 0 && (
            <span className="text-[11px] text-destructive">
              Name must be 1–{NAME_MAX} characters.
            </span>
          )}
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">Type</span>
          <select
            value={projectType}
            onChange={(e) => setProjectType(e.target.value as ProjectType)}
            disabled={mode === 'edit'}
            className="rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring disabled:opacity-60"
          >
            {PROJECT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          {mode === 'edit' && (
            <span className="text-[11px] text-muted-foreground">
              Project type is immutable after creation.
            </span>
          )}
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            Book ID <span className="text-muted-foreground/70">(optional)</span>
          </span>
          <input
            type="text"
            value={bookId}
            onChange={(e) => setBookId(e.target.value)}
            className="rounded-md border bg-input px-3 py-2 font-mono text-xs outline-none focus:border-ring"
            placeholder="uuid"
          />
          {!bookIdValid && (
            <span className="text-[11px] text-destructive">
              Must be a valid UUID.
            </span>
          )}
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            Description <span className="text-muted-foreground/70">(optional)</span>
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
            Instructions <span className="text-muted-foreground/70">(optional)</span>
          </span>
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            maxLength={INSTRUCTIONS_MAX}
            rows={5}
            className="resize-y rounded-md border bg-input px-3 py-2 text-sm outline-none focus:border-ring"
            placeholder="Style notes, voice, constraints — injected into every chat for this project."
          />
          <span className="text-right text-[11px] text-muted-foreground">
            {instructions.length} / {INSTRUCTIONS_MAX}
          </span>
        </label>
      </div>
    </FormDialog>
  );
}
