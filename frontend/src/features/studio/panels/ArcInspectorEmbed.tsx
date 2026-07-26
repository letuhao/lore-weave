// 32 §3.5 (AI-4/DOCK-2) — the arc-inspector's EMBEDDED variant, mounted by PlanDrawer for an
// arc/saga selection. Same shared body as the dock panel; the drawer supplies the id (no picker,
// no chrome). A thin component so useArcInspector is called unconditionally (Rules of Hooks) — the
// drawer mounts it only in its arc branch, never conditionally inside a hook body.
import { useArcInspector } from './useArcInspector';
import { ArcInspectorBody } from './ArcInspectorBody';
import type { ArcOpenPromise } from '@/features/plan-hub/types';

export function ArcInspectorEmbed({ arcId, bookId, onOpenPromise }: {
  arcId: string;
  bookId: string;
  onOpenPromise?: (p: ArcOpenPromise) => void;
}) {
  const state = useArcInspector(bookId, arcId);
  return <ArcInspectorBody state={state} onOpenPromise={onOpenPromise} />;
}
