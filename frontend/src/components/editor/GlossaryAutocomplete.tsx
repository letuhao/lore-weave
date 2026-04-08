import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { EntityNameEntry } from '@/features/glossary/types';

type Props = {
  entities: EntityNameEntry[];
  editorEl: HTMLElement | null;
  /** Called with (triggerStart, triggerEnd, entityName) to replace [[query with entity name via editor commands */
  onInsertEntity: (from: number, to: number, name: string) => void;
  onSelect: (entity: EntityNameEntry) => void;
  onCreateNew: (searchText: string) => void;
};

export function GlossaryAutocomplete({ entities, editorEl, onInsertEntity, onSelect, onCreateNew }: Props) {
  const { t } = useTranslation('glossaryEditor');
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [triggerRange, setTriggerRange] = useState<{ from: number; to: number } | null>(null);

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
      onSelect(entity);
      cleanup();
    },
    [triggerRange, onInsertEntity, onSelect],
  );

  const cleanup = () => {
    setOpen(false);
    setQuery('');
    setSelectedIdx(0);
    setTriggerRange(null);
  };

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
      <div className="border-t px-3 py-1.5 flex justify-between text-[10px] text-muted-foreground">
        <span>↑↓ {t('navigate')} · Enter {t('select')} · Esc {t('dismiss')}</span>
        <span
          className="text-[var(--primary)] cursor-pointer hover:underline"
          onClick={() => { onCreateNew(query); cleanup(); }}
        >
          + {t('createNew')}
        </span>
      </div>
    </div>
  );
}
