// Plan Hub v2 (24 H3 / PH16 / PH20) — the 280px detail DRAWER that opens over the canvas for the
// selected node. It READS via usePlanNode and WRITES via the `writes` prop (PH16's fixed click
// contract: "the drawer edits the DESIRED state; Open in Editor goes to the ACTUAL"). Omitting
// `writes` renders it read-only rather than showing controls that would 403. By kind:
//   • chapter/scene → Overview · Cast & Setting · Craft from the full outline node, plus LIVE
//     Canon-here + Open-threads facets read straight off the cold-open `overlay` prop (those refs
//     are already in memory — no extra fetch, PH9's closed read set). Each ref deep-links to its
//     owning lens via `onOpenRef` (PH18).
//     References + Critic remain empty, and now say WHY: references need `composition_find_
//     references` (28 AN-3, unbuilt) and critic runs are book-scoped (the Quality → Critic panel).
//     They used to read "loads in H4" — long after H4 shipped, which made shipped data look like an
//     unbuilt feature. A stub must name its real blocker or it becomes a lie.
//   • arc/saga → a MINIMAL summary (title/status/goal/span/roster keys). The 23-C3 arc-inspector
//     component does not exist yet (verified), so this is the documented reuse gap, not a fork.
//
// DOCK-2: the legacy scene-inspector's field rendering (TextField/NumberField/EntityRefField) is
// studio-bus-driven; this selection-driven drawer composes its own facet renderer + the PH20 edit
// block (PlanDrawerEdit) rather than mounting that panel — no fork, and no bus dependency.
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';
import type { OutlineNode } from '@/features/composition/types';

import { usePlanNode, type PlanNodeKind, type PlanNodeView } from '../hooks/usePlanNode';
import { refsFor } from './nodePresentation';
import { PlanDrawerEdit } from './PlanDrawerEdit';
// 32 §3.5 (AI-4/DOCK-2) — the drawer mounts the arc-inspector's SHARED body (embedded variant),
// the SAME component the dock panel renders. No fork; no `ArcFacets` stub.
import { ArcInspectorEmbed } from '@/features/studio/panels/ArcInspectorEmbed';
import type { NodeEdit } from '../api';
import type { PlanOverlay, PlanOverlayRef } from '../types';

export interface PlanDrawerProps {
  /** The canvas selection (usePlanHub's selectedId). null ⇒ the drawer renders nothing. */
  selectedId: string | null;
  /** The selected node's kind (from the panel's nodeContent) — routes the facet set + the fetch. */
  kind: string | null;
  bookId: string;
  onClose: () => void;
  /** The cold-open problems overlay. Its canon + thread refs are ALREADY in memory — the drawer's
   *  facets read them directly rather than re-fetching (PH9's closed read set). */
  overlay?: PlanOverlay | null;
  /** PH18 deep-link: open the ref in its owning lens (canon → `quality-canon`, thread →
   *  `quality-promises`). Omitted ⇒ refs render as plain text, never a dead link. */
  onOpenRef?: (ref: PlanOverlayRef, nodeId: string) => void;
  // NOTE: there is deliberately no `refsCapped` prop. It lives at `overlay.problems.refs_capped`,
  // and the drawer already has the overlay — a second prop carrying the same fact is one concept
  // under two names (DA-10), and the two would eventually disagree.

  /** PH20 writes. Omitted ⇒ the drawer is read-only (no EDIT grant / no token) — the edit block
   *  simply isn't rendered, rather than rendering controls that would 403. */
  writes?: {
    edit: (nodeId: string, version: number, patch: NodeEdit) => void;
    archive: (nodeId: string) => void;
    restore: (nodeId: string) => void;
    saving: boolean;
    error: string | null;
  };
  /** The book's chapters, for the ⚓ re-anchor picker (BPS-13). */
  chapters?: { chapter_id: string; title: string; sort_order: number }[];
  /** PH16 — "Open in Editor" goes to the ACTUAL (the manuscript). */
  onOpenInEditor?: (chapterId: string) => void;
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

/** One overlay ref. Deep-links into its owning lens when the panel wired `onOpenRef` (PH18); plain
 *  text otherwise — a ref must never render as a link that does nothing (PH7 visible-fallback). */
function RefRow({ refItem, nodeId, onOpen }: { refItem: PlanOverlayRef; nodeId: string; onOpen?: (r: PlanOverlayRef, n: string) => void }) {
  if (!onOpen) {
    return (
      <li data-testid="plan-drawer-ref" className="text-xs text-foreground/90">
        {refItem.line}
      </li>
    );
  }
  return (
    <li>
      <button
        type="button"
        data-testid="plan-drawer-ref"
        onClick={() => onOpen(refItem, nodeId)}
        className="w-full text-left text-xs text-primary underline-offset-2 hover:underline"
      >
        {refItem.line}
      </button>
    </li>
  );
}

function RefList({
  refs,
  nodeId,
  count,
  capped,
  emptyLabel,
  onOpenRef,
  testid,
}: {
  refs: PlanOverlayRef[];
  nodeId: string;
  count: number;
  capped?: boolean;
  emptyLabel: string;
  onOpenRef?: (r: PlanOverlayRef, n: string) => void;
  testid: string;
}) {
  if (count === 0) return <EmptyFacet>{emptyLabel}</EmptyFacet>;
  return (
    <>
      <ul data-testid={testid} className="space-y-1">
        {refs.map((r) => (
          <RefRow key={`${r.kind}:${r.id}`} refItem={r} nodeId={nodeId} onOpen={onOpenRef} />
        ))}
      </ul>
      {/* OUT-5: the COUNT is exact, the LIST may be capped. Saying so is the difference between a
          documented truncation and a UI that looks broken. */}
      {count > refs.length && (
        <p data-testid={`${testid}-capped`} className="text-[11px] italic text-muted-foreground/70">
          {count} in total{capped ? ' — the list is truncated' : ''}.
        </p>
      )}
    </>
  );
}

// ── chapter/scene facets ───────────────────────────────────────────────────────
function ChapterSceneFacets({
  node,
  nameFor,
  overlay,
  onOpenRef,
  writes,
  chapters,
  onOpenInEditor,
}: {
  node: OutlineNode;
  nameFor: PlanNodeView['nameFor'];
  overlay?: PlanOverlay | null;
  onOpenRef?: (r: PlanOverlayRef, nodeId: string) => void;
  writes?: PlanDrawerProps['writes'];
  chapters?: PlanDrawerProps['chapters'];
  onOpenInEditor?: (chapterId: string) => void;
}) {
  const present = (node.present_entity_ids ?? []).map(nameFor).filter(Boolean).join(', ');
  const num = (v: number | null | undefined): ReactNode => (v == null ? null : String(v));
  const problems = overlay?.problems.by_node[node.id];
  const refsCapped = overlay?.problems.refs_capped ?? false;
  const canonRefs = refsFor(overlay ?? null, node.id, 'canon');
  const threadRefs = refsFor(overlay ?? null, node.id, 'thread');
  return (
    <>
      {/* PH20 — the drawer EDITS the desired state. Rendered only when a write path is wired. */}
      {writes && onOpenInEditor && (
        <>
          <PlanDrawerEdit
            node={node}
            chapters={chapters ?? []}
            saving={writes.saving}
            onEdit={(patch) => writes.edit(node.id, node.version, patch)}
            onArchive={() => writes.archive(node.id)}
            onRestore={() => writes.restore(node.id)}
            onOpenInEditor={onOpenInEditor}
          />
          {writes.error && (
            <p data-testid="plan-drawer-write-error" className="border-b p-3 text-xs text-destructive">
              {writes.error}
            </p>
          )}
        </>
      )}

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

      {/* Canon here + Open threads — LIVE. These refs already ride the cold-open overlay, so the
          drawer reads them from memory (no extra fetch — PH9's closed read set). They used to say
          "loads in H4" long AFTER H4 shipped, which read as a missing feature rather than a stale
          comment: the data was sitting in the same hook. Each ref deep-links to its lens (PH18). */}
      <Section title="Canon here" testid="plan-drawer-section-canon">
        <RefList
          refs={canonRefs}
          nodeId={node.id}
          count={problems?.canon ?? 0}
          capped={refsCapped}
          emptyLabel="No canon rule is anchored here."
          onOpenRef={onOpenRef}
          testid="plan-drawer-canon-refs"
        />
      </Section>
      <Section title="Open threads" testid="plan-drawer-section-threads">
        <RefList
          refs={threadRefs}
          nodeId={node.id}
          count={problems?.threads_open ?? 0}
          capped={refsCapped}
          emptyLabel="No promise opens here."
          onOpenRef={onOpenRef}
          testid="plan-drawer-thread-refs"
        />
      </Section>

      {/* References + Critic stay empty — and now say WHY, and what would fill them. The old copy
          ("loads in H4") was simply false once H4 landed; an honest gap names its real blocker. */}
      <Section title="References" testid="plan-drawer-section-references">
        <EmptyFacet>
          Back-references (where else this node’s entities appear) need
          <code className="mx-1">composition_find_references</code> — spec 28 AN-3, not built yet.
          The cast above is this node’s own roster.
        </EmptyFacet>
      </Section>
      <Section title="Critic" testid="plan-drawer-section-critic">
        <EmptyFacet>Critic runs are book-scoped — see the Quality → Critic panel.</EmptyFacet>
      </Section>
    </>
  );
}

// ── body router ─────────────────────────────────────────────────────────────────
// The arc/saga branch mounts the arc-inspector's shared body (32 §3.5) — the old `ArcFacets`
// minimal-summary stub + its `plan-drawer-arc-gap` note are GONE (the inspector is built).
function DrawerBody({
  view,
  bookId,
  overlay,
  onOpenRef,
  writes,
  chapters,
  onOpenInEditor,
}: {
  view: PlanNodeView;
  bookId: string;
  overlay?: PlanOverlay | null;
  onOpenRef?: (r: PlanOverlayRef, nodeId: string) => void;
  writes?: PlanDrawerProps['writes'];
  chapters?: PlanDrawerProps['chapters'];
  onOpenInEditor?: (chapterId: string) => void;
}) {
  if (view.loading) return <Centered testid="plan-drawer-loading">Loading…</Centered>;
  if (view.error) return <Centered testid="plan-drawer-error" tone="error">{view.error}</Centered>;
  if (view.kind === 'chapter' || view.kind === 'scene') {
    if (!view.outlineNode) return <Centered testid="plan-drawer-empty">This node has no plan yet.</Centered>;
    return (
      <ChapterSceneFacets
        node={view.outlineNode}
        nameFor={view.nameFor}
        overlay={overlay}
        onOpenRef={onOpenRef}
        writes={writes}
        chapters={chapters}
        onOpenInEditor={onOpenInEditor}
      />
    );
  }
  if (view.kind === 'arc' || view.kind === 'saga') {
    if (!view.arcNode) return <Centered testid="plan-drawer-empty">Arc not found in the shell.</Centered>;
    // The shell has no `resolved`/`open_promises`/derived block — the embed fetches GET /arcs/{id}.
    return <ArcInspectorEmbed arcId={view.arcNode.id} bookId={bookId} />;
  }
  return <Centered testid="plan-drawer-empty">Select a node to see its plan.</Centered>;
}

export function PlanDrawer({
  selectedId,
  kind,
  bookId,
  onClose,
  overlay,
  onOpenRef,
  writes,
  chapters,
  onOpenInEditor,
}: PlanDrawerProps) {
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
        <DrawerBody
          view={view}
          bookId={bookId}
          overlay={overlay}
          onOpenRef={onOpenRef}
          writes={writes}
          chapters={chapters}
          onOpenInEditor={onOpenInEditor}
        />
      </div>
    </aside>
  );
}
