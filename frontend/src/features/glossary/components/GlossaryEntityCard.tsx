import { useEffect, useRef, useState } from 'react';
import { KindBadge } from './KindBadge';
import type { GlossaryEntitySummary } from '../types';

type Props = {
  entity: GlossaryEntitySummary;
  isSelected: boolean;
  onClick: () => void;
  onDelete: () => void;
  onSetInactive: () => void;
};

const STATUS_BADGE: Record<string, string> = {
  draft: 'bg-muted text-muted-foreground',
  active: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  inactive: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
};

export function GlossaryEntityCard({
  entity,
  isSelected,
  onClick,
  onDelete,
  onSetInactive,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu + reset confirm when user clicks outside the menu area
  useEffect(() => {
    if (!menuOpen) return;
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
        setConfirmDelete(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [menuOpen]);

  function closeMenu() {
    setMenuOpen(false);
    setConfirmDelete(false);
  }

  function handleMenuClick(e: React.MouseEvent) {
    e.stopPropagation();
    setMenuOpen((o) => !o);
  }

  function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    closeMenu();
    onDelete();
  }

  function handleSetInactive(e: React.MouseEvent) {
    e.stopPropagation();
    closeMenu();
    onSetInactive();
  }

  const displayName = entity.display_name || '(unnamed)';

  return (
    <div
      onClick={onClick}
      className={`relative flex cursor-pointer overflow-hidden rounded border bg-background transition hover:shadow-sm ${
        isSelected ? 'border-primary ring-1 ring-primary' : 'hover:border-border'
      }`}
    >
      {/* Left color bar */}
      <div className="w-1 shrink-0" style={{ backgroundColor: entity.kind.color }} />

      <div className="flex min-w-0 flex-1 flex-col gap-1.5 p-3">
        {/* Top row: kind badge + status */}
        <div className="flex items-center gap-2">
          <KindBadge kind={entity.kind} size="sm" />
          <span
            className={`ml-auto rounded-full px-2 py-0.5 text-xs font-medium ${
              STATUS_BADGE[entity.status] ?? STATUS_BADGE.draft
            }`}
          >
            {entity.status}
          </span>
        </div>

        {/* Display name */}
        <p className="truncate text-sm font-medium">{displayName}</p>

        {/* Counters */}
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {entity.chapter_link_count > 0 && (
            <span title="Chapter links">📎 {entity.chapter_link_count}</span>
          )}
          {entity.translation_count > 0 && (
            <span title="Translations">🌐 {entity.translation_count}</span>
          )}
          {entity.evidence_count > 0 && (
            <span title="Evidences">📝 {entity.evidence_count}</span>
          )}
          {entity.tags.length > 0 && (
            <span className="truncate" title={entity.tags.join(', ')}>
              #{entity.tags[0]}
              {entity.tags.length > 1 && ` +${entity.tags.length - 1}`}
            </span>
          )}
        </div>
      </div>

      {/* ⋯ menu button */}
      <div ref={menuRef} className="relative flex shrink-0 items-start p-2">
        <button
          onClick={handleMenuClick}
          className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label="Entity actions"
        >
          ⋯
        </button>

        {menuOpen && (
          <div
            className="absolute right-0 top-7 z-10 min-w-[120px] rounded border bg-background shadow-md"
            onClick={(e) => e.stopPropagation()}
          >
            {entity.status !== 'inactive' && (
              <button
                onClick={handleSetInactive}
                className="block w-full px-3 py-1.5 text-left text-xs hover:bg-muted"
              >
                Set Inactive
              </button>
            )}
            <button
              onClick={handleDelete}
              className="block w-full px-3 py-1.5 text-left text-xs text-destructive hover:bg-muted"
            >
              {confirmDelete ? 'Confirm move to trash' : 'Move to trash'}
            </button>
            {confirmDelete && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  closeMenu();
                }}
                className="block w-full px-3 py-1.5 text-left text-xs hover:bg-muted"
              >
                Cancel
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
