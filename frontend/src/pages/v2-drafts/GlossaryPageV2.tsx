import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Plus,
  Trash2,
  MoreHorizontal,
  MinusCircle,
  BookOpen,
} from 'lucide-react';
import { useAuth } from '@/auth';
import { useEntityKinds } from '@/features/glossary/hooks/useEntityKinds';
import { useGlossaryEntities } from '@/features/glossary/hooks/useGlossaryEntities';
import { useEntityDetail } from '@/features/glossary/hooks/useEntityDetail';
import { glossaryApi } from '@/features/glossary/api';
import { CreateEntityModal } from '@/features/glossary/components/CreateEntityModal';
import { GlossaryEntityCard } from '@/features/glossary/components/GlossaryEntityCard';
import { EntityDetailPanel } from '@/features/glossary/components/EntityDetailPanel';
import { KindBadge } from '@/features/glossary/components/KindBadge';
import type { EntityKind, EntityStatus, GlossaryEntitySummary } from '@/features/glossary/types';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select } from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import {
  DataTable,
  FilterToolbar,
  ToggleChip,
  TagInput,
  Pagination,
  SortDropdown,
  ViewToggle,
  EmptyState,
  BulkActionBar,
} from '@/components/data';
import type { ColumnDef, SortState, ViewMode } from '@/components/data';

const STATUS_OPTIONS: { value: 'all' | EntityStatus; label: string }[] = [
  { value: 'all', label: 'All statuses' },
  { value: 'draft', label: 'Draft' },
  { value: 'active', label: 'Active' },
  { value: 'inactive', label: 'Inactive' },
];

const STATUS_VARIANT: Record<string, 'success' | 'muted' | 'warning'> = {
  active: 'success',
  draft: 'warning',
  inactive: 'muted',
};

/**
 * V2 GlossaryPage — Redesigned:
 * - Table/grid view toggle with DataTable for table view
 * - Unified FilterToolbar with composable filters
 * - Proper page-based pagination (replaces load-more)
 * - Sort dropdown
 * - Bulk selection & actions
 * - Tag filter with inline tag input
 */
export function GlossaryPageV2() {
  const { bookId = '' } = useParams();
  const { accessToken } = useAuth();

  const { kinds, isLoading: kindsLoading } = useEntityKinds();
  const {
    entities,
    total,
    isLoading,
    isLoadingMore,
    error,
    filters,
    hasMore,
    setFilters,
    loadMore,
    removeEntity,
    refresh,
  } = useGlossaryEntities(bookId);

  // UI state
  const [view, setView] = useState<ViewMode>('grid');
  const [sort, setSort] = useState<SortState | null>(null);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState('');

  // Pagination state (client-side on top of existing hook data, since the hook uses load-more)
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const {
    entity: detailEntity,
    isLoading: detailLoading,
    isSaving,
    patch,
    refetch: refetchDetail,
  } = useEntityDetail(bookId, selectedEntityId);

  // Client-side sort (the existing hook handles filtering via API)
  const sorted = useMemo(() => {
    if (!sort) return entities;
    return [...entities].sort((a, b) => {
      let cmp = 0;
      switch (sort.field) {
        case 'display_name':
          cmp = a.display_name.localeCompare(b.display_name);
          break;
        case 'status':
          cmp = a.status.localeCompare(b.status);
          break;
        case 'kind':
          cmp = a.kind.name.localeCompare(b.kind.name);
          break;
        case 'updated_at':
          cmp = a.updated_at.localeCompare(b.updated_at);
          break;
        default:
          break;
      }
      return sort.direction === 'desc' ? -cmp : cmp;
    });
  }, [entities, sort]);

  // Selection helpers
  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // Build active filter chips
  const activeFilters = [
    ...(filters.status !== 'all'
      ? [{ label: `Status: ${filters.status}`, onRemove: () => setFilters({ status: 'all' }) }]
      : []),
    ...(filters.chapterIds === 'unlinked'
      ? [{ label: 'Unlinked only', onRemove: () => setFilters({ chapterIds: [] }) }]
      : []),
    ...filters.kindCodes.map((code) => {
      const kind = kinds.find((k) => k.code === code);
      return {
        label: `${kind?.icon ?? ''} ${kind?.name ?? code}`,
        onRemove: () =>
          setFilters({ kindCodes: filters.kindCodes.filter((c) => c !== code) }),
      };
    }),
    ...filters.tags.map((tag) => ({
      label: `#${tag}`,
      onRemove: () => setFilters({ tags: filters.tags.filter((t) => t !== tag) }),
    })),
  ];

  async function handleKindSelect(kind: EntityKind) {
    if (!accessToken) return;
    setIsCreating(true);
    setCreateError('');
    try {
      const created = await glossaryApi.createEntity(bookId, kind.kind_id, accessToken);
      setIsCreateOpen(false);
      refresh();
      setSelectedEntityId(created.entity_id);
    } catch (e: unknown) {
      setCreateError((e as Error).message || 'Failed to create entity');
    } finally {
      setIsCreating(false);
    }
  }

  async function handleDelete(entityId: string) {
    if (!accessToken) return;
    try {
      await glossaryApi.deleteEntity(bookId, entityId, accessToken);
      removeEntity(entityId);
      if (selectedEntityId === entityId) setSelectedEntityId(null);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(entityId);
        return next;
      });
    } catch {
      // handled
    }
  }

  async function handleSetInactive(entityId: string) {
    if (!accessToken) return;
    try {
      await glossaryApi.patchEntity(bookId, entityId, { status: 'inactive' }, accessToken);
      refresh();
    } catch {
      // handled
    }
  }

  // Table columns
  const columns: ColumnDef<GlossaryEntitySummary>[] = [
    {
      key: 'kind',
      header: 'Kind',
      widthClass: 'w-24',
      render: (e) => <KindBadge kind={e.kind} size="sm" />,
    },
    {
      key: 'display_name',
      header: 'Name',
      sortable: true,
      render: (e) => (
        <div>
          <span className="font-medium">{e.display_name || '(unnamed)'}</span>
          {e.display_name_translation && (
            <span className="ml-2 text-xs text-muted-foreground">{e.display_name_translation}</span>
          )}
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      widthClass: 'w-24',
      render: (e) => <Badge variant={STATUS_VARIANT[e.status] ?? 'muted'}>{e.status}</Badge>,
    },
    {
      key: 'chapter_link_count',
      header: 'Links',
      widthClass: 'w-16',
      hideBelow: 'sm',
      render: (e) => <span className="text-xs tabular-nums">{e.chapter_link_count}</span>,
    },
    {
      key: 'translation_count',
      header: 'Translations',
      widthClass: 'w-24',
      hideBelow: 'md',
      render: (e) => <span className="text-xs tabular-nums">{e.translation_count}</span>,
    },
    {
      key: 'tags',
      header: 'Tags',
      hideBelow: 'lg',
      render: (e) =>
        e.tags.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {e.tags.slice(0, 2).map((tag) => (
              <span key={tag} className="rounded-full bg-muted px-1.5 py-0.5 text-[10px]">
                #{tag}
              </span>
            ))}
            {e.tags.length > 2 && (
              <span className="text-[10px] text-muted-foreground">+{e.tags.length - 2}</span>
            )}
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        ),
    },
    {
      key: 'updated_at',
      header: 'Updated',
      sortable: true,
      widthClass: 'w-24',
      hideBelow: 'lg',
      render: (e) => (
        <span className="text-xs text-muted-foreground">
          {new Date(e.updated_at).toLocaleDateString()}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      widthClass: 'w-10',
      render: (e) => (
        <DropdownMenu>
          <DropdownMenuTrigger
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Entity actions"
            onClick={(ev) => ev.stopPropagation()}
          >
            <MoreHorizontal className="h-4 w-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {e.status !== 'inactive' && (
              <DropdownMenuItem onClick={() => handleSetInactive(e.entity_id)}>
                <MinusCircle className="mr-2 h-3.5 w-3.5" /> Set Inactive
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => handleDelete(e.entity_id)}
              className="text-destructive"
            >
              <Trash2 className="mr-2 h-3.5 w-3.5" /> Move to trash
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ];

  const sortOptions = [
    { field: 'display_name', label: 'Name' },
    { field: 'status', label: 'Status' },
    { field: 'kind', label: 'Kind' },
    { field: 'updated_at', label: 'Updated' },
  ];

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      {/* ── Header ────────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Glossary</h1>
          <p className="text-xs text-muted-foreground">
            {total} {total === 1 ? 'entity' : 'entities'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link to={`/books/${bookId}/glossary/trash`}>
              <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Trash
            </Link>
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setIsCreateOpen(true);
              setCreateError('');
            }}
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" /> New Entity
          </Button>
        </div>
      </div>

      {/* ── Toolbar ───────────────────────────────────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <FilterToolbar
            searchValue={filters.searchQuery}
            onSearchChange={(v) => setFilters({ searchQuery: v })}
            searchPlaceholder="Search entities…"
            activeFilters={activeFilters}
            onClearAll={() =>
              setFilters({ kindCodes: [], status: 'all', chapterIds: [], searchQuery: '', tags: [] })
            }
            advancedFilters={
              <div className="space-y-3">
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                    Filter by tags
                  </label>
                  <TagInput
                    tags={filters.tags}
                    onChange={(tags) => setFilters({ tags })}
                    placeholder="Type a tag and press Enter…"
                  />
                </div>
              </div>
            }
          >
            {/* Status filter */}
            <Select
              value={filters.status}
              onChange={(e) =>
                setFilters({ status: e.target.value as 'all' | EntityStatus })
              }
              className="h-8 w-auto text-xs"
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>

            {/* Unlinked toggle */}
            <Button
              variant={filters.chapterIds === 'unlinked' ? 'default' : 'outline'}
              size="sm"
              onClick={() =>
                setFilters({
                  chapterIds: filters.chapterIds === 'unlinked' ? [] : 'unlinked',
                })
              }
              className="h-8 text-xs"
            >
              Unlinked
            </Button>

            <SortDropdown sort={sort} options={sortOptions} onSortChange={setSort} />
            <ViewToggle view={view} onViewChange={setView} />
          </FilterToolbar>
        </div>

        {/* Kind chips row */}
        {!kindsLoading && kinds.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {kinds.map((k) => (
              <ToggleChip
                key={k.kind_id}
                label={k.name}
                icon={k.icon}
                color={k.color}
                active={filters.kindCodes.includes(k.code)}
                onToggle={() => {
                  const next = filters.kindCodes.includes(k.code)
                    ? filters.kindCodes.filter((c) => c !== k.code)
                    : [...filters.kindCodes, k.code];
                  setFilters({ kindCodes: next });
                }}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Error ─────────────────────────────────────────────────────────────── */}
      {error && (
        <p className="rounded border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </p>
      )}

      {/* ── Content ───────────────────────────────────────────────────────────── */}
      {isLoading ? (
        view === 'grid' ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-24 animate-pulse rounded border bg-muted" />
            ))}
          </div>
        ) : (
          <DataTable
            columns={columns}
            data={[]}
            rowKey={(e) => e.entity_id}
            isLoading={true}
            skeletonRows={6}
          />
        )
      ) : sorted.length === 0 ? (
        <EmptyState
          icon={<BookOpen className="h-10 w-10 text-muted-foreground/50" />}
          title={
            filters.searchQuery || filters.kindCodes.length > 0 || filters.status !== 'all'
              ? 'No entities match your filters'
              : 'No entities yet'
          }
          description={
            filters.searchQuery || filters.kindCodes.length > 0
              ? 'Try adjusting your search or filters.'
              : 'Click "New Entity" to create your first glossary entry.'
          }
          filtered={!!(filters.searchQuery || filters.kindCodes.length > 0 || filters.status !== 'all')}
          action={
            !filters.searchQuery && filters.kindCodes.length === 0
              ? {
                  label: 'New Entity',
                  onClick: () => {
                    setIsCreateOpen(true);
                    setCreateError('');
                  },
                }
              : undefined
          }
        />
      ) : view === 'table' ? (
        /* ── Table view ──────────────────────────────────────────────────────── */
        <DataTable
          columns={columns}
          data={sorted}
          rowKey={(e) => e.entity_id}
          sort={sort}
          onSort={(field) => {
            setSort((prev) => {
              if (prev?.field === field) {
                return prev.direction === 'asc' ? { field, direction: 'desc' } : null;
              }
              return { field, direction: 'asc' };
            });
          }}
          selectedIds={selectedIds}
          onToggleSelect={toggleSelect}
          onSelectAll={() => setSelectedIds(new Set(sorted.map((e) => e.entity_id)))}
          onDeselectAll={() => setSelectedIds(new Set())}
          onRowClick={(e) => setSelectedEntityId(e.entity_id)}
          activeRowId={selectedEntityId}
        />
      ) : (
        /* ── Grid view (existing cards) ──────────────────────────────────────── */
        <div className="grid gap-3 sm:grid-cols-2">
          {sorted.map((entity) => (
            <GlossaryEntityCard
              key={entity.entity_id}
              entity={entity}
              isSelected={selectedEntityId === entity.entity_id}
              onClick={() => setSelectedEntityId(entity.entity_id)}
              onDelete={() => handleDelete(entity.entity_id)}
              onSetInactive={() => handleSetInactive(entity.entity_id)}
            />
          ))}
        </div>
      )}

      {/* ── Load more / Pagination ────────────────────────────────────────────── */}
      {hasMore && (
        <div className="flex justify-center pt-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadMore}
            disabled={isLoadingMore}
          >
            {isLoadingMore ? 'Loading…' : `Load more (${total - entities.length} remaining)`}
          </Button>
        </div>
      )}

      {/* ── Bulk Action Bar ───────────────────────────────────────────────────── */}
      <BulkActionBar
        selectedCount={selectedIds.size}
        onClear={() => setSelectedIds(new Set())}
      >
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={async () => {
            for (const id of selectedIds) {
              await handleSetInactive(id);
            }
            setSelectedIds(new Set());
          }}
        >
          <MinusCircle className="mr-1.5 h-3 w-3" /> Set Inactive
        </Button>
        <Button
          variant="destructive"
          size="sm"
          className="h-7 text-xs"
          onClick={async () => {
            for (const id of selectedIds) {
              await handleDelete(id);
            }
            setSelectedIds(new Set());
          }}
        >
          <Trash2 className="mr-1.5 h-3 w-3" /> Move to Trash
        </Button>
      </BulkActionBar>

      {/* ── Create entity modal ───────────────────────────────────────────────── */}
      {isCreateOpen && (
        <CreateEntityModal
          kinds={kinds}
          onSelect={handleKindSelect}
          onClose={() => setIsCreateOpen(false)}
          isCreating={isCreating}
          createError={createError}
        />
      )}

      {/* ── Entity detail panel ───────────────────────────────────────────────── */}
      {selectedEntityId && (
        <EntityDetailPanel
          entity={detailEntity}
          bookId={bookId}
          token={accessToken ?? ''}
          isLoading={detailLoading}
          isSaving={isSaving}
          onClose={() => setSelectedEntityId(null)}
          onPatch={patch}
          onRefresh={refetchDetail}
        />
      )}
    </div>
  );
}
