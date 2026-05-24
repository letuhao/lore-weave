import { useUiStore } from '@/store/ui-store';

// Sidebar placeholder. Session D wires Inventory / Chat / Party / Quest
// tabs per spec §3.

export function Sidebar(): JSX.Element {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggle = useUiStore((s) => s.toggleSidebar);
  return (
    <aside
      className={`bg-slate-800/90 text-slate-100 border-l border-slate-700 transition-all ${
        collapsed ? 'w-12' : 'w-64'
      }`}
    >
      <button
        type="button"
        onClick={toggle}
        className="w-full p-2 text-left hover:bg-slate-700"
      >
        {collapsed ? '»' : '« Sidebar (placeholder)'}
      </button>
    </aside>
  );
}
