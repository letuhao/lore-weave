// View: pick an interview persona (template) + a chat model, then start. Render
// only — all logic/state lives in useInterviewSetup (passed in as props so this
// stays a pure view and is trivially testable).

import { GraduationCap, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { InterviewSetup } from '../hooks/useInterviewSetup';

interface PersonaPickerProps {
  setup: InterviewSetup;
  onStart: () => void;
}

export function PersonaPicker({ setup, onStart }: PersonaPickerProps) {
  const { templates, models, loading, selectedTemplateId, selectedModelId, selectTemplate, selectModel, canStart, starting } = setup;

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading personas…
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 overflow-y-auto p-6">
      <header className="flex items-center gap-3">
        <GraduationCap className="h-7 w-7 text-primary" />
        <div>
          <h1 className="font-serif text-lg font-semibold">Interview practice</h1>
          <p className="text-xs text-muted-foreground">Pick an interviewer and a model, then start. You can speak or type.</p>
        </div>
      </header>

      <section className="flex flex-col gap-2">
        <span className="text-xs font-medium text-muted-foreground">Interviewer</span>
        <div className="grid gap-2 sm:grid-cols-1">
          {templates.length === 0 && (
            <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">No personas available.</p>
          )}
          {templates.map((t) => (
            <button
              key={t.template_id}
              type="button"
              onClick={() => selectTemplate(t.template_id)}
              className={cn(
                'flex flex-col items-start gap-1 rounded-lg border bg-card p-4 text-left transition-colors hover:border-primary/60 hover:bg-accent/40',
                selectedTemplateId === t.template_id && 'border-primary ring-1 ring-primary',
              )}
            >
              <span className="flex items-center gap-2 text-sm font-medium">
                {t.name}
                {t.tier === 'system' && (
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">default</span>
                )}
              </span>
              {t.description && <span className="text-xs text-muted-foreground">{t.description}</span>}
              <span className="mt-1 text-[11px] text-muted-foreground">
                {t.scenario.phases.length} phases · {t.scenario.checklist.length} checkpoints
                {t.scenario.time_budget_min ? ` · ~${t.scenario.time_budget_min} min` : ''}
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <label htmlFor="interview-model" className="text-xs font-medium text-muted-foreground">Model</label>
        {models.length === 0 ? (
          <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
            No chat-capable model. Add one under Settings → Models.
          </p>
        ) : (
          <select
            id="interview-model"
            value={selectedModelId ?? ''}
            onChange={(e) => selectModel(e.target.value)}
            className="rounded-lg border bg-background p-2 text-sm"
          >
            {models.map((m) => (
              <option key={m.user_model_id} value={m.user_model_id}>
                {m.alias ?? m.provider_model_name} ({m.provider_kind})
              </option>
            ))}
          </select>
        )}
      </section>

      <button
        type="button"
        disabled={!canStart}
        onClick={onStart}
        className="flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity disabled:opacity-50"
      >
        {starting && <Loader2 className="h-4 w-4 animate-spin" />}
        Start practice
      </button>
    </div>
  );
}
