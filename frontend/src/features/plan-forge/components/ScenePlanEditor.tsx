// PlanForge — the NESTED checkpoint editor, for `scene_plan` only.
//
// Every other reviewable atom is a flat list, so `PassArtifactEditor` handles them with one row
// shape. `scene_plan` is the exception: its list is `chapters[] → scenes[]`, and the flat editor
// could only have represented it by flattening the structure on save — silently destroying the
// chapter grouping. So `scene_plan` was left GUI-read-only, which meant the one atom that most
// directly decides what gets WRITTEN (the scene breakdown each chapter is drafted from) was the one
// atom a GUI-only author could not touch. This closes that.
//
// Shape is the producer's (`plan_pass_adapters._decompose_to_artifact`), confirmed against live
// artifacts:
//   chapters[] = { chapter: {chapter_id,title,sort_order,beat_role,intent}, scenes: [...],
//                  warning, exit_state }
//   scenes[]   = { title, synopsis, tension, present_entity_ids,
//                  present_entity_names_unresolved, suggested_k }
//
// Two invariants this component must not break:
//  1. **Nothing unexposed is lost.** Chapter-level `warning`/`exit_state` and scene-level
//     `present_entity_ids` etc. are carried through by spread. A scene whose resolved entity ids
//     were dropped would silently lose its grounding.
//  2. **The chapter grouping is preserved.** Scenes are edited in place, per chapter; a chapter row
//     is never merged, reordered, or deleted here — deleting a CHAPTER is the beats checkpoint's
//     job, not the scene planner's.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

type Row = Record<string, unknown>;
const str = (v: unknown): string => (typeof v === 'string' ? v : v == null ? '' : String(v));

interface Props {
  content: unknown;
  busy: boolean;
  onSave: (edits: Record<string, unknown>) => void;
  onCancel: () => void;
}

interface ChapterEntry {
  raw: Row;              // the whole chapter object, so unexposed fields survive
  chapter: Row;          // chapter.chapter (title/beat_role/…)
  scenes: Row[];
}

function readChapters(content: unknown): ChapterEntry[] {
  const raw = (content as Record<string, unknown> | null)?.chapters;
  if (!Array.isArray(raw)) return [];
  return raw.map((c) => {
    const row = { ...(c as Row) };
    return {
      raw: row,
      chapter: { ...((row.chapter ?? {}) as Row) },
      scenes: Array.isArray(row.scenes) ? (row.scenes as Row[]).map((s) => ({ ...s })) : [],
    };
  });
}

/** A scene with no meaningful authored content — dropped on save so a blank add never ships. */
function isBlank(s: Row): boolean {
  return str(s.title).trim() === '' && str(s.synopsis).trim() === '';
}

export function ScenePlanEditor({ content, busy, onSave, onCancel }: Props) {
  const { t } = useTranslation('studio');
  const [chapters, setChapters] = useState<ChapterEntry[]>(() => readChapters(content));

  const mutateScenes = (ci: number, fn: (scenes: Row[]) => Row[]) =>
    setChapters((cs) => cs.map((c, i) => (i === ci ? { ...c, scenes: fn(c.scenes) } : c)));

  const setCell = (ci: number, si: number, key: string, val: string) =>
    mutateScenes(ci, (ss) => ss.map((s, i) => (i === si ? { ...s, [key]: val } : s)));
  const removeScene = (ci: number, si: number) =>
    mutateScenes(ci, (ss) => ss.filter((_, i) => i !== si));
  const addScene = (ci: number) =>
    mutateScenes(ci, (ss) => [...ss, { title: '', synopsis: '', tension: '' }]);

  const save = () => {
    onSave({
      chapters: chapters.map((c) => ({
        ...c.raw,                       // keeps warning / exit_state / anything we don't render
        chapter: c.chapter,
        scenes: c.scenes.filter((s) => !isBlank(s)),
      })),
    });
  };

  if (!chapters.length) {
    return (
      <p data-testid="scene-plan-editor-empty" className="text-[10px] text-muted-foreground">
        {t('planPasses.noScenes', { defaultValue: 'No chapters to edit in this scene plan.' })}
      </p>
    );
  }

  return (
    <div data-testid="scene-plan-editor" className="rounded border border-primary/30 bg-background/60 p-1.5">
      <div className="max-h-72 space-y-2 overflow-y-auto">
        {chapters.map((c, ci) => (
          <div key={`${str(c.chapter.chapter_id)}-${ci}`} data-testid={`scene-chapter-${ci}`}>
            <p className="mb-0.5 text-[10px] font-medium text-foreground">
              {str(c.chapter.title) || `Chapter ${ci + 1}`}
              {c.chapter.beat_role != null && str(c.chapter.beat_role) !== '' && (
                <span className="ml-1 rounded bg-secondary px-1 text-[9px] uppercase text-muted-foreground">
                  {str(c.chapter.beat_role)}
                </span>
              )}
            </p>
            <div className="space-y-1 pl-2">
              {c.scenes.map((s, si) => (
                <div key={si} data-testid={`scene-row-${ci}-${si}`} className="flex items-center gap-1">
                  <input
                    data-testid={`scene-${ci}-${si}-title`}
                    value={str(s.title)} placeholder="Title"
                    onChange={(e) => setCell(ci, si, 'title', e.target.value)}
                    className="min-w-0 flex-1 rounded border border-border bg-background px-1 py-0.5 text-[10px]"
                  />
                  <input
                    data-testid={`scene-${ci}-${si}-synopsis`}
                    value={str(s.synopsis)} placeholder="Synopsis"
                    onChange={(e) => setCell(ci, si, 'synopsis', e.target.value)}
                    className="min-w-0 flex-[2] rounded border border-border bg-background px-1 py-0.5 text-[10px]"
                  />
                  <input
                    data-testid={`scene-${ci}-${si}-tension`}
                    value={str(s.tension)} placeholder="0-100" inputMode="numeric"
                    onChange={(e) => setCell(ci, si, 'tension', e.target.value)}
                    className="w-14 rounded border border-border bg-background px-1 py-0.5 text-[10px]"
                  />
                  <button
                    type="button" data-testid={`scene-remove-${ci}-${si}`}
                    onClick={() => removeScene(ci, si)}
                    title={t('planPasses.editRemove', { defaultValue: 'Remove' })}
                    className="rounded border border-destructive/40 px-1 text-[10px] text-destructive hover:bg-destructive/10"
                  >✕</button>
                </div>
              ))}
              {/* A chapter with no scenes cannot be drafted at all — say so rather than showing an
                  empty gap the author might read as "fine". */}
              {!c.scenes.length && (
                <p data-testid={`scene-none-${ci}`} className="text-[10px] text-destructive">
                  {t('planPasses.chapterNoScenes', { defaultValue: 'No scenes — this chapter cannot be drafted.' })}
                </p>
              )}
              <button
                type="button" data-testid={`scene-add-${ci}`} onClick={() => addScene(ci)}
                className="rounded border border-border px-1.5 py-0.5 text-[10px] hover:bg-secondary"
              >+ {t('planPasses.editAdd', { defaultValue: 'Add' })}</button>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex gap-2">
        <button
          type="button" data-testid="edit-save" disabled={busy} onClick={save}
          className="ml-auto rounded bg-primary px-2 py-0.5 text-[10px] font-medium text-primary-foreground hover:brightness-110 disabled:opacity-40"
        >{t('planPasses.saveEdits', { defaultValue: 'Save edits' })}</button>
        <button
          type="button" data-testid="edit-cancel" onClick={onCancel}
          className="rounded border border-border px-2 py-0.5 text-[10px] hover:bg-secondary"
        >{t('planPasses.cancel', { defaultValue: 'Cancel' })}</button>
      </div>
    </div>
  );
}
