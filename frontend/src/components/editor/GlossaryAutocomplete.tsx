import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { EntityNameEntry } from '@/features/glossary/types';

// S-10 O7 (PO D-d) — the CLOSED set of kinds the `[[`-create picker offers. Enum-gated per the
// Frontend-Tool-Contract: the UI only ever sends one of these to knowledgeApi.createEntity, so a
// free-typed / mistyped kind can never reach the backend from this surface.
export const AUTHORABLE_KINDS = ['character', 'location', 'organization', 'concept', 'item'] as const;
export type AuthorableKind = (typeof AUTHORABLE_KINDS)[number];

type Props = {
  entities: EntityNameEntry[];
  editorEl: HTMLElement | null;
  /** Called with (triggerStart, triggerEnd, entityName) to replace [[query with entity name via editor commands */
  onInsertEntity: (from: number, to: number, name: string) => void;
  /** Optional notification after a pick — the INSERT itself is onInsertEntity's job. */
  onSelect?: (entity: EntityNameEntry) => void;
  /** S-10 O7 (PO D-d) — the `[[`-create flow. When provided, typing `[[NewName` offers
   *  "＋ Create "NewName" as…" with the AuthorableKind picker; choosing a kind calls this with the
   *  typed name + the chosen (closed-set) kind. The consumer creates the entity + inserts it. OPTIONAL:
   *  when omitted the affordance is HIDDEN (never a dead "+ Create new" link — the 2026-07-17 audit
   *  removed that; this is the build the audit named). */
  onCreateNew?: (name: string, kind: AuthorableKind) => void;
};

export function GlossaryAutocomplete({ entities, editorEl, onInsertEntity, onSelect, onCreateNew }: Props) {
  const { t } = useTranslation('glossaryEditor');
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [triggerRange, setTriggerRange] = useState<{ from: number; to: number } | null>(null);
  // S-10 O7 — the `[[`-create sub-mode: the "＋ Create" affordance expands into the AuthorableKind
  // picker in place. Reset whenever the popup closes / the query changes.
  const [creating, setCreating] = useState(false);

  const filtered = useMemo(() => {
    if (!query) return entities.slice(0, 10);
    const q = query.toLowerCase();
    return entities
      .filter((e) => e.display_name.toLowerCase().includes(q))
      .slice(0, 10);
  }, [entities, query]);

  // Listen for [[ in the editor via selection/input
  useEffect(() => {
    if (!editorEl) return;

    const handleInput = () => {
      const sel = window.getSelection();
      if (!sel || sel.rangeCount === 0) return;

      const range = sel.getRangeAt(0);
      const textNode = range.startContainer;
      if (textNode.nodeType !== Node.TEXT_NODE) return;

      const text = textNode.textContent || '';
      const offset = range.startOffset;

      // Find [[ before cursor
      const before = text.slice(0, offset);
      const triggerIdx = before.lastIndexOf('[[');
      if (triggerIdx === -1) {
        if (open) setOpen(false);
        return;
      }

      // Extract search query after [[
      const searchText = before.slice(triggerIdx + 2);
      if (searchText.includes(']')) {
        if (open) setOpen(false);
        return;
      }

      setQuery(searchText);
      setSelectedIdx(0);

      // Calculate ProseMirror positions for the trigger range
      // Walk up from text node to find the offset in the document
      const walker = document.createTreeWalker(editorEl, NodeFilter.SHOW_TEXT);
      let pmOffset = 0;
      let found = false;
      while (walker.nextNode()) {
        if (walker.currentNode === textNode) {
          found = true;
          break;
        }
        pmOffset += (walker.currentNode.textContent || '').length;
      }
      if (found) {
        setTriggerRange({ from: pmOffset + triggerIdx, to: pmOffset + offset });
      }

      // Position popup near cursor
      const rect = range.getBoundingClientRect();
      setPos({ x: rect.left, y: rect.bottom + 4 });
      setOpen(true);
    };

    editorEl.addEventListener('input', handleInput);
    editorEl.addEventListener('keyup', handleInput);
    return () => {
      editorEl.removeEventListener('input', handleInput);
      editorEl.removeEventListener('keyup', handleInput);
    };
  }, [editorEl]);

  // Keyboard navigation
  useEffect(() => {
    if (!open || !editorEl) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIdx((i) => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (selectedIdx < filtered.length) {
          handleSelect(filtered[selectedIdx]);
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        setOpen(false);
      }
    };

    editorEl.addEventListener('keydown', handleKeyDown, true);
    return () => editorEl.removeEventListener('keydown', handleKeyDown, true);
  }, [open, editorEl, filtered, selectedIdx]);

  const handleSelect = useCallback(
    (entity: EntityNameEntry) => {
      if (triggerRange) {
        // Replace [[query with entity name via editor commands (safe, no DOM mutation)
        onInsertEntity(triggerRange.from, triggerRange.to, entity.display_name);
      }
      onSelect?.(entity);
      cleanup();
    },
    [triggerRange, onInsertEntity, onSelect],
  );

  const cleanup = () => {
    setOpen(false);
    setQuery('');
    setSelectedIdx(0);
    setTriggerRange(null);
    setCreating(false);
  };

  // Leaving the create sub-mode whenever the typed query changes keeps the picker from lingering
  // over a stale name (the user kept typing after opening it).
  useEffect(() => { setCreating(false); }, [query]);

  const canCreate = !!onCreateNew && query.trim().length > 0;

  if (!open) return null;

  return (
    <div
      className="fixed z-[100] w-[300px] rounded-lg border bg-card shadow-xl"
      style={{ left: pos.x, top: pos.y }}
    >
      <div className="border-b px-3 py-2 text-[10px] text-muted-foreground">
        {t('suggestions')} "<span className="text-[var(--primary)]">{query}</span>"
      </div>
      <div className="max-h-[200px] overflow-y-auto py-1">
        {filtered.map((entity, i) => (
          <div
            key={entity.entity_id}
            onClick={() => handleSelect(entity)}
            className={`flex items-center gap-2 px-3 py-1.5 cursor-pointer transition-colors ${
              i === selectedIdx ? 'bg-[var(--primary-muted)]' : 'hover:bg-[var(--card-hover)]'
            }`}
          >
            <span
              className="h-2 w-2 rounded-full flex-shrink-0"
              style={{ background: entity.kind_color || '#9e9488' }}
            />
            <span className="text-[13px] flex-1 truncate">{entity.display_name}</span>
            <span className="text-[10px] text-muted-foreground">{entity.kind_name}</span>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="px-3 py-2 text-xs text-muted-foreground">{t('noMatch')}</div>
        )}
      </div>
      {/* S-10 O7 — the `[[`-create picker. Expands in place under the list: "Create "query" as…" +
          one chip per AuthorableKind (closed set). Choosing a kind hands (name, kind) to the consumer
          (create + insert) and closes. Only offered when a create handler is wired AND the query is a
          real name. */}
      {creating && canCreate && (
        <div data-testid="glossary-create-picker" className="border-t px-3 py-2">
          <div className="mb-1.5 text-[10px] text-muted-foreground">
            {t('createAs', { defaultValue: 'Create "{{name}}" as…', name: query })}
          </div>
          <div className="flex flex-wrap gap-1">
            {AUTHORABLE_KINDS.map((k) => (
              <button
                key={k}
                type="button"
                data-testid={`glossary-create-kind-${k}`}
                onClick={() => { onCreateNew?.(query, k); cleanup(); }}
                className="rounded border px-2 py-0.5 text-[11px] hover:bg-[var(--primary-muted)]"
              >
                {t(`kind.${k}`, { defaultValue: k })}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="border-t px-3 py-1.5 flex justify-between text-[10px] text-muted-foreground">
        <span>↑↓ {t('navigate')} · Enter {t('select')} · Esc {t('dismiss')}</span>
        {canCreate && !creating && (
          <button
            type="button"
            data-testid="glossary-create-toggle"
            className="text-[var(--primary)] cursor-pointer hover:underline"
            onClick={() => setCreating(true)}
          >
            ＋ {t('createNew')}
          </button>
        )}
      </div>
    </div>
  );
}
