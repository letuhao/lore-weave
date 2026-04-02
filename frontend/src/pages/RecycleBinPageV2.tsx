import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, FileText, MessageSquare, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Select } from '@/components/ui/select';
import {
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useTrashItems } from '@/features/trash/useTrashItems';
import { TrashCard } from '@/features/trash/TrashCard';
import { FloatingTrashBar } from '@/features/trash/FloatingTrashBar';
import type { TrashItem, TrashType } from '@/features/trash/types';

type SortKey = 'newest' | 'oldest' | 'name';

function sortItems(items: TrashItem[], sort: SortKey): TrashItem[] {
  const sorted = [...items];
  switch (sort) {
    case 'newest':
      return sorted.sort((a, b) => new Date(b.deletedAt).getTime() - new Date(a.deletedAt).getTime());
    case 'oldest':
      return sorted.sort((a, b) => new Date(a.deletedAt).getTime() - new Date(b.deletedAt).getTime());
    case 'name':
      return sorted.sort((a, b) => a.title.localeCompare(b.title));
    default:
      return sorted;
  }
}

// ── Tab definitions ─────────────────────────────────────────────────────────

const TAB_DEFS: { value: TrashType; label: string; icon: React.ReactNode }[] = [
  { value: 'book',    label: 'Books',         icon: <BookOpen className="h-3.5 w-3.5" /> },
  { value: 'chapter', label: 'Chapters',      icon: <FileText className="h-3.5 w-3.5" /> },
  {
    value: 'glossary',
    label: 'Glossary',
    icon: (
      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
        <path d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 01-1.806-1.741L3.842 10.1a2 2 0 011.075-2.029l1.29-.645a6 6 0 013.86-.517l.318.158a6 6 0 003.86.517l2.387-.477a2 2 0 012.368 2.367l-.402 2.814a2 2 0 01-.77 1.34z" />
      </svg>
    ),
  },
  { value: 'chat',    label: 'Chat Sessions', icon: <MessageSquare className="h-3.5 w-3.5" /> },
];

// ── Page component ──────────────────────────────────────────────────────────

export function RecycleBinPageV2() {
  const {
    items: allItems,
    counts,
    isLoading,
    restoreItem,
    purgeItem,
  } = useTrashItems();

  const [activeTab, setActiveTab] = useState<TrashType>('book');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortKey>('newest');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmPurge, setConfirmPurge] = useState<TrashItem[] | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  // ── Filtered + sorted items for active tab ────────────────────────────────

  const tabItems = useMemo(() => {
    let filtered = allItems.filter((it) => it.type === activeTab);
    if (search.trim()) {
      const q = search.toLowerCase();
      filtered = filtered.filter(
        (it) =>
          it.title.toLowerCase().includes(q) ||
          it.badge.toLowerCase().includes(q) ||
          (it.context?.toLowerCase().includes(q) ?? false),
      );
    }
    return sortItems(filtered, sort);
  }, [allItems, activeTab, search, sort]);

  function handleTabChange(tab: string) {
    setActiveTab(tab as TrashType);
    setSelected(new Set());
    setSearch('');
  }

  // ── Selection ─────────────────────────────────────────────────────────────

  function toggleItem(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === tabItems.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(tabItems.map((it) => it.id)));
    }
  }

  // ── Single-item actions ───────────────────────────────────────────────────

  async function handleRestore(item: TrashItem) {
    setActionLoading(true);
    try {
      await restoreItem(item);
      setSelected((prev) => { const n = new Set(prev); n.delete(item.id); return n; });
      toast.success(`Restored "${item.title}"`);
    } catch (e) {
      toast.error(`Restore failed: ${(e as Error).message}`);
    } finally {
      setActionLoading(false);
    }
  }

  function handlePurgeClick(item: TrashItem) {
    setConfirmPurge([item]);
  }

  // ── Bulk actions ──────────────────────────────────────────────────────────

  async function handleBulkRestore() {
    const selectedItems = tabItems.filter((it) => selected.has(it.id));
    setActionLoading(true);
    let restored = 0;
    for (const item of selectedItems) {
      try {
        await restoreItem(item);
        restored++;
      } catch { /* continue */ }
    }
    setSelected(new Set());
    setActionLoading(false);
    toast.success(`Restored ${restored} item${restored !== 1 ? 's' : ''}`);
  }

  function handleBulkPurgeClick() {
    const selectedItems = tabItems.filter((it) => selected.has(it.id));
    setConfirmPurge(selectedItems);
  }

  // ── Confirm purge ─────────────────────────────────────────────────────────

  async function executePurge() {
    if (!confirmPurge) return;
    setActionLoading(true);
    let purged = 0;
    for (const item of confirmPurge) {
      try {
        await purgeItem(item);
        purged++;
      } catch { /* continue */ }
    }
    setSelected((prev) => {
      const next = new Set(prev);
      for (const item of confirmPurge) next.delete(item.id);
      return next;
    });
    setConfirmPurge(null);
    setActionLoading(false);
    toast.success(`Permanently deleted ${purged} item${purged !== 1 ? 's' : ''}`);
  }

  // ── Render ────────────────────────────────────────────────────────────────

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
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <div className="flex items-center justify-between">
          <TabsList>
            {TAB_DEFS.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value} className="gap-1.5">
                {tab.icon}
                {tab.label}
                {counts[tab.value] > 0 && (
                  <span className="rounded-full bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                    {counts[tab.value]}
                  </span>
                )}
              </TabsTrigger>
            ))}
          </TabsList>

          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search trash\u2026"
              className="h-8 w-[200px] rounded-md border border-input bg-input pl-8 pr-3 text-[13px] text-foreground placeholder:text-muted-foreground/60 focus:border-ring focus:outline-none focus:shadow-[0_0_0_3px_rgba(212,149,42,0.15)]"
            />
          </div>
        </div>

        {/* Shared tab content (same card pattern for all types) */}
        {TAB_DEFS.map((tab) => (
          <TabsContent key={tab.value} value={tab.value} className="space-y-3">
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
              <Select
                value={sort}
                onChange={(e) => setSort(e.target.value as SortKey)}
                className="h-7 w-auto text-xs"
              >
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
                <option value="name">Name A-Z</option>
              </Select>
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
                    onPurge={() => handlePurgeClick(item)}
                    disabled={actionLoading}
                  />
                ))}
              </div>
            )}

            {/* Empty state */}
            {!isLoading && tabItems.length === 0 && (
              <div className="flex flex-col items-center justify-center gap-3 py-16">
                <Trash2 className="h-12 w-12 text-muted-foreground/20" />
                <p className="text-sm font-medium text-foreground">Trash is empty</p>
                <p className="text-xs text-muted-foreground">
                  {search
                    ? 'No items match your search.'
                    : 'Deleted items will appear here for 30 days before permanent removal.'}
                </p>
              </div>
            )}
          </TabsContent>
        ))}
      </Tabs>

      {/* Floating action bar */}
      <FloatingTrashBar
        count={selected.size}
        onRestore={() => void handleBulkRestore()}
        onPurge={handleBulkPurgeClick}
        onClear={() => setSelected(new Set())}
        disabled={actionLoading}
      />

      {/* Confirm purge dialog */}
      {confirmPurge && (
        <DialogContent onClose={() => setConfirmPurge(null)} className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete permanently?</DialogTitle>
          </DialogHeader>
          <p className="py-2 text-sm text-muted-foreground">
            {confirmPurge.length === 1 ? (
              <>
                <strong className="text-foreground">{confirmPurge[0].title}</strong> will be
                permanently deleted. This cannot be undone.
              </>
            ) : (
              <>
                <strong className="text-foreground">{confirmPurge.length} items</strong> will be
                permanently deleted. This cannot be undone.
              </>
            )}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmPurge(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => void executePurge()}
              disabled={actionLoading}
            >
              {actionLoading ? 'Deleting\u2026' : 'Delete Permanently'}
            </Button>
          </DialogFooter>
        </DialogContent>
      )}
    </div>
  );
}
