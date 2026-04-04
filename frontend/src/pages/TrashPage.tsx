import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, FileText, MessageSquare, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { useTrashItems } from '@/features/trash/useTrashItems';
import { TrashCard } from '@/features/trash/TrashCard';
import { FloatingTrashBar } from '@/features/trash/FloatingTrashBar';
import type { TrashItem, TrashType } from '@/features/trash/types';

type SortKey = 'newest' | 'oldest' | 'name';

function sortItems(items: TrashItem[], sort: SortKey): TrashItem[] {
  const sorted = [...items];
  switch (sort) {
    case 'newest': return sorted.sort((a, b) => new Date(b.deletedAt).getTime() - new Date(a.deletedAt).getTime());
    case 'oldest': return sorted.sort((a, b) => new Date(a.deletedAt).getTime() - new Date(b.deletedAt).getTime());
    case 'name': return sorted.sort((a, b) => a.title.localeCompare(b.title));
    default: return sorted;
  }
}

const TAB_DEFS: { value: TrashType; label: string; icon: React.ReactNode }[] = [
  { value: 'book',    label: 'Books',         icon: <BookOpen className="h-3.5 w-3.5" /> },
  { value: 'chapter', label: 'Chapters',      icon: <FileText className="h-3.5 w-3.5" /> },
  {
    value: 'glossary', label: 'Glossary',
    icon: <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 01-1.806-1.741L3.842 10.1a2 2 0 011.075-2.029l1.29-.645a6 6 0 013.86-.517l.318.158a6 6 0 003.86.517l2.387-.477a2 2 0 012.368 2.367l-.402 2.814a2 2 0 01-.77 1.34z" /></svg>,
  },
  { value: 'chat',    label: 'Chat Sessions', icon: <MessageSquare className="h-3.5 w-3.5" /> },
];

export function TrashPage() {
  const { items: allItems, counts, isLoading, restoreItem, purgeItem } = useTrashItems();
  const [activeTab, setActiveTab] = useState<TrashType>('book');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortKey>('newest');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmPurge, setConfirmPurge] = useState<TrashItem[] | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const tabItems = useMemo(() => {
    let filtered = allItems.filter((it) => it.type === activeTab);
    if (search.trim()) {
      const q = search.toLowerCase();
      filtered = filtered.filter(
        (it) => it.title.toLowerCase().includes(q) || it.badge.toLowerCase().includes(q) || (it.context?.toLowerCase().includes(q) ?? false),
      );
    }
    return sortItems(filtered, sort);
  }, [allItems, activeTab, search, sort]);

  function handleTabChange(tab: TrashType) {
    setActiveTab(tab);
    setSelected(new Set());
    setSearch('');
  }

  function toggleItem(id: string) {
    setSelected((prev) => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  }

  function toggleAll() {
    setSelected(tabItems.length > 0 && selected.size === tabItems.length ? new Set() : new Set(tabItems.map((it) => it.id)));
  }

  async function handleRestore(item: TrashItem) {
    setActionLoading(true);
    try {
      await restoreItem(item);
      setSelected((prev) => { const n = new Set(prev); n.delete(item.id); return n; });
      toast.success(`Restored "${item.title}"`);
    } catch (e) {
      toast.error(`Restore failed: ${(e as Error).message}`);
    } finally { setActionLoading(false); }
  }

  async function handleBulkRestore() {
    const items = tabItems.filter((it) => selected.has(it.id));
    setActionLoading(true);
    let restored = 0;
    for (const item of items) { try { await restoreItem(item); restored++; } catch {} }
    setSelected(new Set());
    setActionLoading(false);
    toast.success(`Restored ${restored} item${restored !== 1 ? 's' : ''}`);
  }

  async function executePurge() {
    if (!confirmPurge) return;
    setActionLoading(true);
    let purged = 0;
    for (const item of confirmPurge) { try { await purgeItem(item); purged++; } catch {} }
    setSelected((prev) => { const n = new Set(prev); for (const item of confirmPurge) n.delete(item.id); return n; });
    setConfirmPurge(null);
    setActionLoading(false);
    toast.success(`Permanently deleted ${purged} item${purged !== 1 ? 's' : ''}`);
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <Trash2 className="h-5 w-5 text-muted-foreground" />
            <h1 className="text-lg font-semibold">Recycle Bin</h1>
          </div>
          <p className="ml-[30px] mt-1 text-xs text-muted-foreground">
            Items here will be permanently deleted after 30 days.
          </p>
        </div>
        <Link to="/books" className="text-[13px] text-muted-foreground hover:text-foreground">
          &larr; Back to Workspace
        </Link>
      </div>

      {/* Tabs + Search */}
      <div className="flex items-center justify-between border-b">
        <div className="flex">
          {TAB_DEFS.map((tab) => (
            <button
              key={tab.value}
              type="button"
              onClick={() => handleTabChange(tab.value)}
              className={cn(
                'flex items-center gap-1.5 border-b-2 px-4 py-2 text-[13px] font-medium transition-colors',
                activeTab === tab.value
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              {tab.icon}
              {tab.label}
              {counts[tab.value] > 0 && (
                <span className="rounded-full bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                  {counts[tab.value]}
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="relative mb-[-1px]">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search trash…"
            className="h-8 w-[200px] rounded-md border bg-input pl-8 pr-3 text-[13px] text-foreground placeholder:text-muted-foreground/60 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          />
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={tabItems.length > 0 && selected.size === tabItems.length}
            onChange={toggleAll}
            disabled={tabItems.length === 0}
            className="h-4 w-4 cursor-pointer rounded border-border bg-input accent-primary"
          />
          <span className="text-xs text-muted-foreground">
            {tabItems.length} item{tabItems.length !== 1 ? 's' : ''}
          </span>
        </div>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          className="h-7 rounded-md border bg-input px-2 text-xs text-muted-foreground outline-none"
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="name">Name A-Z</option>
        </select>
      </div>

      {/* Loading */}
      {isLoading && tabItems.length === 0 && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-14 animate-pulse rounded-lg border bg-muted/30" />
          ))}
        </div>
      )}

      {/* Cards */}
      {tabItems.length > 0 && (
        <div className="flex flex-col gap-2">
          {tabItems.map((item) => (
            <TrashCard
              key={item.id}
              item={item}
              selected={selected.has(item.id)}
              onToggle={() => toggleItem(item.id)}
              onRestore={() => void handleRestore(item)}
              onPurge={() => setConfirmPurge([item])}
              disabled={actionLoading}
            />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && tabItems.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-3 py-16">
          <Trash2 className="h-12 w-12 text-muted-foreground/20" />
          <p className="text-sm font-medium">Trash is empty</p>
          <p className="text-xs text-muted-foreground">
            {search ? 'No items match your search.' : 'Deleted items will appear here for 30 days before permanent removal.'}
          </p>
        </div>
      )}

      {/* Floating action bar */}
      <FloatingTrashBar
        count={selected.size}
        onRestore={() => void handleBulkRestore()}
        onPurge={() => setConfirmPurge(tabItems.filter((it) => selected.has(it.id)))}
        onClear={() => setSelected(new Set())}
        disabled={actionLoading}
      />

      {/* Confirm purge dialog */}
      <ConfirmDialog
        open={confirmPurge !== null}
        onOpenChange={(open) => { if (!open) setConfirmPurge(null); }}
        title="Delete permanently?"
        description={
          confirmPurge?.length === 1
            ? `"${confirmPurge[0].title}" will be permanently deleted. This cannot be undone.`
            : `${confirmPurge?.length ?? 0} items will be permanently deleted. This cannot be undone.`
        }
        confirmLabel={actionLoading ? 'Deleting…' : 'Delete Permanently'}
        cancelLabel="Cancel"
        variant="destructive"
        onConfirm={() => void executePurge()}
      />
    </div>
  );
}
