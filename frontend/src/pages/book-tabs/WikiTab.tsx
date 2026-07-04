// 15_wiki_panels.md B5 — thin page shell over the shared WikiWorkspace (DOCK-2 "no fork"), same
// shape as GlossaryTab.tsx post-migration. Re-exports WikiSidebar so existing imports of
// `../WikiTab` (see __tests__/WikiTab.test.tsx) keep resolving without changes.
export { WikiSidebar } from '@/features/wiki/components/WikiWorkspace';
import { WikiWorkspace } from '@/features/wiki/components/WikiWorkspace';

export function WikiTab({ bookId }: { bookId: string }) {
  return <WikiWorkspace bookId={bookId} />;
}
