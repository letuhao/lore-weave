// 22-C3 — the `scene-inspector` dock panel: every field of ONE selected scene on a single
// surface (spec 22 §GUI), sectioned Identity · Intent · Craft · State · Grounding. It fixes the
// F2 pathology where a scene's goal/pov/tension/craft were agent-writable-but-human-invisible or
// read-only to everyone: here a human reads AND edits them, OCC-guarded. Logic lives in the hook.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { GroundingPanel } from '@/features/composition/components/GroundingPanel';
import { useGlossaryRoster } from '@/features/composition/hooks/useGlossaryRoster';
import type { OutlineNode } from '@/features/composition/types';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { useSceneInspector } from './useSceneInspector';
import { useConformanceStatus } from './useConformanceStatus';
import { EntityRefField } from './EntityRefField';
import { SceneLinksSection } from './SceneLinksSection';
import { SceneMotifsSection } from '@/features/composition/motif/components/SceneMotifsSection';

const STATUSES: OutlineNode['status'][] = ['empty', 'outline', 'drafting', 'done'];
const SOURCE_LABEL: Record<string, string> = { authored: 'Authored', decompiled: 'Mined', planforge: 'PlanForge' };

// A text field that commits its change on blur (only when it actually changed) via OCC patch.
// The draft re-seeds from the prop on external change, but never over an in-progress edit.
function TextField({ label, value, rows, onCommit, testid }: {
  label: string; value: string; rows?: number; onCommit: (v: string) => void; testid: string;
}) {
  const [draft, setDraft] = useState(value);
  const [editing, setEditing] = useState(false);
  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);
  const commit = () => { setEditing(false); if (draft !== value) onCommit(draft); };
  return (
    <label className="block">
      <span className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      {rows ? (
        <textarea data-testid={testid} value={draft} rows={rows}
          onFocus={() => setEditing(true)} onChange={(e) => setDraft(e.target.value)} onBlur={commit}
          className="w-full resize-none rounded border bg-background px-2 py-1 text-xs" />
      ) : (
        <input data-testid={testid} value={draft}
          onFocus={() => setEditing(true)} onChange={(e) => setDraft(e.target.value)} onBlur={commit}
          className="w-full rounded border bg-background px-2 py-1 text-xs" />
      )}
    </label>
  );
}

// A number field (nullable) — an empty string clears to null; commits on blur.
function NumberField({ label, value, min, max, onCommit, testid }: {
  label: string; value: number | null | undefined; min?: number; max?: number; onCommit: (v: number | null) => void; testid: string;
}) {
  const seed = value == null ? '' : String(value);
  const [draft, setDraft] = useState(seed);
  const [editing, setEditing] = useState(false);
  useEffect(() => { if (!editing) setDraft(value == null ? '' : String(value)); }, [value, editing]);
  const commit = () => {
    setEditing(false);
    const next = draft.trim() === '' ? null : Number(draft);
    if (next != null && Number.isNaN(next)) { setDraft(seed); return; }
    if (next !== (value ?? null)) onCommit(next);
  };
  return (
    <label className="block">
      <span className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <input data-testid={testid} type="number" value={draft} min={min} max={max}
        onFocus={() => setEditing(true)} onChange={(e) => setDraft(e.target.value)} onBlur={commit}
        className="w-full rounded border bg-background px-2 py-1 text-xs" />
    </label>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b p-3">
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-foreground/70">{title}</h3>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

export function SceneInspectorPanel(props: IDockviewPanelProps) {
  useStudioPanel('scene-inspector', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const sb = useSceneInspector(host.bookId ?? null);
  const conf = useConformanceStatus(host.bookId ?? null); // 26 IX-14 — the per-scene dirty chip
  // 22-C3b — the book's glossary roster resolves pov/present/location ids → names (DOCK-2 no fork).
  const roster = useGlossaryRoster(host.bookId ?? undefined, accessToken ?? null);
  const rosterOptions = roster.data ?? [];
  const n = sb.node;

  if (!n) {
    return (
      <div data-testid="studio-scene-inspector-panel" className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
        {sb.loading
          ? t('panels.scene-inspector.loading', { defaultValue: 'Loading…' })
          : sb.error
            ? <span data-testid="scene-inspector-error" className="text-destructive">{sb.error}</span>
            : t('panels.scene-inspector.none', { defaultValue: 'Select a scene to inspect its full plan.' })}
      </div>
    );
  }

  const setF = (p: Partial<OutlineNode>) => void sb.patch(p);

  return (
    <div data-testid="studio-scene-inspector-panel" className="flex h-full min-h-0 flex-col overflow-auto">
      {sb.error && <div data-testid="scene-inspector-error" className="border-b bg-destructive/10 px-3 py-1.5 text-xs text-destructive">{sb.error}</div>}
      {/* 26 IX-14 — this scene's chapter drifted since the last conformance run (arc dirty ∧ chapter stale). */}
      {n.chapter_id && conf.dirtyChapters.has(n.chapter_id) && (
        <div data-testid="scene-inspector-dirty" className="border-b bg-amber-500/10 px-3 py-1.5 text-xs text-amber-700 dark:text-amber-300">
          {t('panels.scene-inspector.dirty', { defaultValue: 'Canon moved since the last conformance run — this plan may be stale.' })}
        </div>
      )}

      <Section title={t('panels.scene-inspector.section.identity', { defaultValue: 'Identity' })}>
        <TextField testid="scene-inspector-title" label={t('panels.scene-inspector.f.title', { defaultValue: 'Title' })}
          value={n.title} onCommit={(v) => setF({ title: v })} />
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <span data-testid="scene-inspector-source" className="rounded bg-muted px-1.5 py-0.5">
            {SOURCE_LABEL[n.source ?? 'authored'] ?? n.source}
          </span>
          <span>#{n.story_order != null ? n.story_order + 1 : '—'}</span>
        </div>
      </Section>

      <Section title={t('panels.scene-inspector.section.intent', { defaultValue: 'Intent' })}>
        <label className="block">
          <span className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {t('panels.scene-inspector.f.status', { defaultValue: 'Status' })}
          </span>
          <select data-testid="scene-inspector-status" value={n.status}
            onChange={(e) => setF({ status: e.target.value as OutlineNode['status'] })}
            className="w-full rounded border bg-background px-2 py-1 text-xs">
            {STATUSES.map((s) => <option key={s} value={s}>{t(`panels.scene-inspector.status.${s}`, { defaultValue: s })}</option>)}
          </select>
        </label>
        <TextField testid="scene-inspector-goal" label={t('panels.scene-inspector.f.goal', { defaultValue: 'Goal' })}
          value={n.goal ?? ''} onCommit={(v) => setF({ goal: v })} />
        <TextField testid="scene-inspector-synopsis" rows={3} label={t('panels.scene-inspector.f.synopsis', { defaultValue: 'Synopsis' })}
          value={n.synopsis} onCommit={(v) => setF({ synopsis: v })} />
        <TextField testid="scene-inspector-beat" label={t('panels.scene-inspector.f.beat', { defaultValue: 'Beat role' })}
          value={n.beat_role ?? ''} onCommit={(v) => setF({ beat_role: v || null })} />
        <NumberField testid="scene-inspector-tension" label={t('panels.scene-inspector.f.tension', { defaultValue: 'Tension (0–100)' })}
          value={n.tension} min={0} max={100} onCommit={(v) => setF({ tension: v })} />
      </Section>

      {/* 22-C3b (F2) — cast & setting as glossary refs, not raw UUIDs. */}
      <Section title={t('panels.scene-inspector.section.cast', { defaultValue: 'Cast & Setting' })}>
        <EntityRefField mode="single" testid="scene-inspector-pov"
          label={t('panels.scene-inspector.f.pov', { defaultValue: 'POV character' })}
          value={n.pov_entity_id} roster={rosterOptions} rosterLoading={roster.isLoading}
          onChange={(id) => setF({ pov_entity_id: id })} />
        <EntityRefField mode="multi" testid="scene-inspector-present"
          label={t('panels.scene-inspector.f.present', { defaultValue: 'Present characters' })}
          value={n.present_entity_ids} roster={rosterOptions} rosterLoading={roster.isLoading}
          onChange={(ids) => setF({ present_entity_ids: ids })} />
        <EntityRefField mode="single" testid="scene-inspector-location"
          label={t('panels.scene-inspector.f.location', { defaultValue: 'Location' })}
          value={n.location_entity_id} roster={rosterOptions} rosterLoading={roster.isLoading}
          onChange={(id) => setF({ location_entity_id: id })} />
      </Section>

      <Section title={t('panels.scene-inspector.section.craft', { defaultValue: 'Craft' })}>
        <TextField testid="scene-inspector-conflict" rows={2} label={t('panels.scene-inspector.f.conflict', { defaultValue: 'Conflict' })}
          value={n.conflict ?? ''} onCommit={(v) => setF({ conflict: v })} />
        <TextField testid="scene-inspector-outcome" rows={2} label={t('panels.scene-inspector.f.outcome', { defaultValue: 'Outcome' })}
          value={n.outcome ?? ''} onCommit={(v) => setF({ outcome: v })} />
        <TextField testid="scene-inspector-stakes" label={t('panels.scene-inspector.f.stakes', { defaultValue: 'Stakes' })}
          value={n.stakes ?? ''} onCommit={(v) => setF({ stakes: v })} />
        <TextField testid="scene-inspector-storytime" label={t('panels.scene-inspector.f.storyTime', { defaultValue: 'Story time' })}
          value={n.story_time ?? ''} onCommit={(v) => setF({ story_time: v || null })} />
        <NumberField testid="scene-inspector-valueshift" label={t('panels.scene-inspector.f.valueShift', { defaultValue: 'Value shift (−100…100)' })}
          value={n.value_shift} min={-100} max={100} onCommit={(v) => setF({ value_shift: v })} />
        <NumberField testid="scene-inspector-targetwords" label={t('panels.scene-inspector.f.targetWords', { defaultValue: 'Target words' })}
          value={n.target_words} min={0} onCommit={(v) => setF({ target_words: v })} />
      </Section>

      {/* 3b §3.2a — Motifs: bind/swap/clear this scene's motif + the ranked Suggest button. */}
      <Section title={t('panels.scene-inspector.section.motifs', { defaultValue: 'Motifs' })}>
        <SceneMotifsSection
          projectId={sb.projectId ?? null}
          bookId={host.bookId ?? null}
          chapterId={n.chapter_id ?? null}
          sceneId={n.id}
          roster={rosterOptions}
          token={accessToken ?? null}
        />
      </Section>

      {/* 22-C3 Links — this scene's causal edges, reusing the Scene Graph's data (DOCK-2, no fork). */}
      {sb.projectId && (
        <Section title={t('panels.scene-inspector.section.links', { defaultValue: 'Links' })}>
          <SceneLinksSection projectId={sb.projectId} token={accessToken ?? null} sceneId={n.id} />
        </Section>
      )}

      {/* Grounding — reuse the existing panel's data (DOCK-2, no fork). */}
      {sb.projectId && host.bookId && n.chapter_id && (
        <Section title={t('panels.scene-inspector.section.grounding', { defaultValue: 'Grounding' })}>
          <div data-testid="scene-inspector-grounding">
            <GroundingPanel projectId={sb.projectId} bookId={host.bookId} chapterId={n.chapter_id} sceneId={n.id} token={accessToken ?? null} />
          </div>
        </Section>
      )}
    </div>
  );
}
