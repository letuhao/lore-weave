// Plan Hub v2 (24 H3 / PH16) — the 280px detail DRAWER that opens over the canvas for the selected
// node. Render-only over usePlanNode's data + the passed selection; close via onClose (edits are
// H5 / PH20 — this slice reads, it does not write). By kind:
//   • chapter/scene → Overview · Cast & Setting · Craft facets from the full outline node, plus
//     honestly-empty Canon-here / References / Critic facets (their data — problems overlay,
//     references search, critic runs — is wired in H4; the facet is present, never a silent gap).
//   • arc/saga → a MINIMAL summary (title/status/goal/span/roster keys). The 23-C3 arc-inspector
//     component does not exist yet (verified), so this is the documented reuse gap, not a fork.
//
// DOCK-2: the legacy scene-inspector's field rendering (TextField/NumberField/EntityRefField) is
// EDITABLE + studio-bus-driven; this render-only, selection-driven drawer composes a read-only facet
// renderer instead of mounting that editable panel. The editable path lands with H5's interactions.
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';
import type { OutlineNode } from '@/features/composition/types';

import { usePlanNode, type PlanNodeKind, type PlanNodeView } from '../hooks/usePlanNode';
import type { ArcListNode } from '../types';

export interface PlanDrawerProps {
  /** The canvas selection (usePlanHub's selectedId). null ⇒ the drawer renders nothing. */
  selectedId: string | null;
  /** The selected node's kind (from the panel's nodeContent) — routes the facet set + the fetch. */
  kind: string | null;
  bookId: string;
  onClose: () => void;
}

const KIND_LABEL: Record<PlanNodeKind, string> = {
  chapter: 'Chapter',
  scene: 'Scene',
  arc: 'Arc',
  saga: 'Saga',
  unknown: 'Node',
};

// ── small render primitives (read-only) ────────────────────────────────────────
function orDash(v: ReactNode): ReactNode {
  if (v == null || v === '') return <span className="text-muted-foreground/50">—</span>;
  return v;
}

function Section({ title, testid, children }: { title: string; testid: string; children: ReactNode }) {
  return (
    <section data-testid={testid} className="border-b p-3">
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-foreground/70">{title}</h3>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function Field({ label, value, testid }: { label: string; value: ReactNode; testid?: string }) {
  return (
    <div>
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div data-testid={testid} className="whitespace-pre-wrap break-words text-xs text-foreground/90">
        {orDash(value)}
      </div>
    </div>
  );
}

function StatusChip({ status }: { status?: string | null }) {
  if (!status) return null;
  return (
    <span
      data-testid="plan-drawer-status"
      className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground"
    >
      {status}
    </span>
  );
}

function EmptyFacet({ children }: { children: ReactNode }) {
  return <p className="text-[11px] italic text-muted-foreground/70">{children}</p>;
}

function Centered({ testid, tone, children }: { testid: string; tone?: 'error'; children: ReactNode }) {
  return (
    <div
      data-testid={testid}
      className={cn(
        'flex h-full items-center justify-center p-6 text-center text-sm',
        tone === 'error' ? 'text-destructive' : 'text-muted-foreground',
      )}
    >
      {children}
    </div>
  );
}

// ── chapter/scene facets ───────────────────────────────────────────────────────
function ChapterSceneFacets({ node, nameFor }: { node: OutlineNode; nameFor: PlanNodeView['nameFor'] }) {
  const present = (node.present_entity_ids ?? []).map(nameFor).filter(Boolean).join(', ');
  const num = (v: number | null | undefined): ReactNode => (v == null ? null : String(v));
  return (
    <>
      <Section title="Overview" testid="plan-drawer-section-overview">
        <Field label="Status" value={node.status} testid="plan-drawer-f-status" />
        <Field label="Goal" value={node.goal} testid="plan-drawer-f-goal" />
        <Field label="Synopsis" value={node.synopsis} testid="plan-drawer-f-synopsis" />
        <Field label="Beat role" value={node.beat_role} testid="plan-drawer-f-beat" />
        <Field label="Tension" value={num(node.tension)} testid="plan-drawer-f-tension" />
      </Section>

      <Section title="Cast & Setting" testid="plan-drawer-section-cast">
        <Field label="POV" value={nameFor(node.pov_entity_id)} testid="plan-drawer-f-pov" />
        <Field label="Present" value={present || null} testid="plan-drawer-f-present" />
        <Field label="Location" value={nameFor(node.location_entity_id)} testid="plan-drawer-f-location" />
      </Section>

      <Section title="Craft" testid="plan-drawer-section-craft">
        <Field label="Conflict" value={node.conflict} testid="plan-drawer-f-conflict" />
        <Field label="Outcome" value={node.outcome} testid="plan-drawer-f-outcome" />
        <Field label="Stakes" value={node.stakes} testid="plan-drawer-f-stakes" />
        <Field label="Story time" value={node.story_time} testid="plan-drawer-f-storytime" />
        <Field label="Value shift" value={num(node.value_shift)} testid="plan-drawer-f-valueshift" />
        <Field label="Target words" value={num(node.target_words)} testid="plan-drawer-f-targetwords" />
      </Section>

      {/* Canon-here / References / Critic — the facet is present now; its data (problems overlay,
          references search, critic runs) lands in H4. Honest visible-fallback, never a blank gap. */}
      <Section title="Canon here" testid="plan-drawer-section-canon">
        <EmptyFacet>Canon findings load with the problems overlay (H4).</EmptyFacet>
      </Section>
      <Section title="References" testid="plan-drawer-section-references">
        <EmptyFacet>Lore references load in H4.</EmptyFacet>
      </Section>
      <Section title="Critic" testid="plan-drawer-section-critic">
        <EmptyFacet>Critic results load in H4.</EmptyFacet>
      </Section>
    </>
  );
}

// ── arc/saga facets (minimal summary — 23-C3 arc-inspector not built yet) ────────
function rosterKeysOf(roster: unknown): string[] {
  if (Array.isArray(roster)) return roster.map((r) => (typeof r === 'string' ? r : String((r as { key?: string })?.key ?? ''))).filter(Boolean);
  if (roster && typeof roster === 'object') return Object.keys(roster as Record<string, unknown>);
  return [];
}

function ArcFacets({ arc }: { arc: ArcListNode }) {
  // The wire carries tracks/roster/roster_bindings (types.ts note) though the FE ArcListNode subset
  // doesn't declare them — read them defensively without redefining the H2-owned type.
  const extra = arc as ArcListNode & { tracks?: unknown; roster?: unknown };
  const rosterKeys = rosterKeysOf(extra.roster);
  const trackKeys = rosterKeysOf(extra.tracks);
  const span = arc.span ? `${arc.span.from_order}–${arc.span.to_order}` : null;
  return (
    <>
      <Section title="Overview" testid="plan-drawer-section-overview">
        <Field label="Status" value={arc.status} testid="plan-drawer-f-status" />
        <Field label="Goal" value={arc.goal} testid="plan-drawer-f-goal" />
        <Field label="Summary" value={arc.summary} testid="plan-drawer-f-summary" />
      </Section>

      <Section title="Structure" testid="plan-drawer-section-structure">
        <Field label="Kind" value={arc.kind} />
        <Field label="Chapter span (story order)" value={span} testid="plan-drawer-f-span" />
        {arc.span && !arc.is_contiguous && (
          <p data-testid="plan-drawer-noncontiguous" className="text-[11px] text-amber-600 dark:text-amber-400">
            Non-contiguous span — rendered as separate runs on the canvas.
          </p>
        )}
        <Field label="Chapters" value={String(arc.chapter_count)} testid="plan-drawer-f-chaptercount" />
        {trackKeys.length > 0 && <Field label="Tracks" value={trackKeys.join(', ')} testid="plan-drawer-f-tracks" />}
      </Section>

      <Section title="Roster" testid="plan-drawer-section-roster">
        {rosterKeys.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {rosterKeys.map((key) => (
              <span key={key} className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">{key}</span>
            ))}
          </div>
        ) : (
          <EmptyFacet>No roster keys on this arc.</EmptyFacet>
        )}
      </Section>

      {(arc.arc_template_id || arc.template_version != null) && (
        <Section title="Provenance" testid="plan-drawer-section-provenance">
          <Field label="Arc template" value={arc.arc_template_id} testid="plan-drawer-f-template" />
          <Field label="Template version" value={arc.template_version != null ? String(arc.template_version) : null} />
        </Section>
      )}

      <p data-testid="plan-drawer-arc-gap" className="p-3 text-[11px] italic text-muted-foreground/70">
        The full arc inspector (Structure · Roster · Chapters · Conformance · Provenance — 23 C3) is not
        built yet; this is a minimal summary.
      </p>
    </>
  );
}

// ── body router ─────────────────────────────────────────────────────────────────
function DrawerBody({ view }: { view: PlanNodeView }) {
  if (view.loading) return <Centered testid="plan-drawer-loading">Loading…</Centered>;
  if (view.error) return <Centered testid="plan-drawer-error" tone="error">{view.error}</Centered>;
  if (view.kind === 'chapter' || view.kind === 'scene') {
    if (!view.outlineNode) return <Centered testid="plan-drawer-empty">This node has no plan yet.</Centered>;
    return <ChapterSceneFacets node={view.outlineNode} nameFor={view.nameFor} />;
  }
  if (view.kind === 'arc' || view.kind === 'saga') {
    if (!view.arcNode) return <Centered testid="plan-drawer-empty">Arc not found in the shell.</Centered>;
    return <ArcFacets arc={view.arcNode} />;
  }
  return <Centered testid="plan-drawer-empty">Select a node to see its plan.</Centered>;
}

export function PlanDrawer({ selectedId, kind, bookId, onClose }: PlanDrawerProps) {
  // Hook first (unconditional — Rules of Hooks); then self-hide when there is no selection so the
  // orchestrator can keep <PlanDrawer/> mounted (never conditionally unmount a stateful child).
  const view = usePlanNode(bookId, selectedId, kind);
  if (!selectedId) return null;

  const headerTitle = view.outlineNode?.title ?? view.arcNode?.title ?? '';
  const headerStatus = view.outlineNode?.status ?? view.arcNode?.status ?? null;

  return (
    <aside
      data-testid="plan-drawer"
      className="absolute right-0 top-0 z-10 flex h-full w-[280px] flex-col border-l bg-background shadow-lg"
    >
      <header className="flex items-start gap-2 border-b p-3">
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {KIND_LABEL[view.kind]}
          </div>
          <div data-testid="plan-drawer-title" className="truncate text-sm font-semibold" title={headerTitle}>
            {headerTitle || (view.loading ? 'Loading…' : '—')}
          </div>
          <div className="mt-1">
            <StatusChip status={headerStatus} />
          </div>
        </div>
        <button
          type="button"
          data-testid="plan-drawer-close"
          onClick={onClose}
          aria-label="Close"
          className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          ×
        </button>
      </header>
      <div data-testid="plan-drawer-body" className="min-h-0 flex-1 overflow-auto">
        <DrawerBody view={view} />
      </div>
    </aside>
  );
}
