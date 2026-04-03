import { useEffect, useRef, useState } from 'react';
import { BookOpen, Globe, Languages, Lightbulb, Pencil, Search, Sparkles } from 'lucide-react';

export interface PromptTemplate {
  id: string;
  label: string;
  icon: React.ReactNode;
  prompt: string;
  category: 'writing' | 'analysis' | 'translation' | 'utility';
}

const BUILT_IN_TEMPLATES: PromptTemplate[] = [
  { id: 'analyze-character', label: 'Analyze character arc', icon: <Sparkles className="h-3.5 w-3.5" />, prompt: 'Analyze the character arc of {{character}} across the selected chapters. What are their core motivations, and how do they evolve?', category: 'analysis' },
  { id: 'rewrite-scene', label: 'Rewrite a scene', icon: <Pencil className="h-3.5 w-3.5" />, prompt: 'Rewrite the following scene with a focus on showing rather than telling. Keep the same plot points but improve the prose:\n\n', category: 'writing' },
  { id: 'translate-passage', label: 'Translate passage', icon: <Languages className="h-3.5 w-3.5" />, prompt: 'Translate the following passage to {{target_language}}, preserving literary style, tone, and cultural nuance:\n\n', category: 'translation' },
  { id: 'worldbuilding-check', label: 'Worldbuilding consistency', icon: <Globe className="h-3.5 w-3.5" />, prompt: 'Review this passage for worldbuilding consistency. Check magic system rules, geography, political structure, and cultural details against established lore. Flag any contradictions.', category: 'analysis' },
  { id: 'dialogue-improve', label: 'Improve dialogue', icon: <Pencil className="h-3.5 w-3.5" />, prompt: 'Improve the dialogue in this passage. Make each character sound distinct, natural, and true to their personality. Remove exposition dumps disguised as dialogue.', category: 'writing' },
  { id: 'plot-hole', label: 'Find plot holes', icon: <Lightbulb className="h-3.5 w-3.5" />, prompt: 'Analyze the attached chapters for plot holes, logical inconsistencies, and unresolved threads. For each issue found, suggest a fix.', category: 'analysis' },
  { id: 'summarize-chapter', label: 'Summarize chapter', icon: <BookOpen className="h-3.5 w-3.5" />, prompt: 'Provide a concise summary of this chapter in 3-5 bullet points, highlighting key plot developments, character changes, and foreshadowing.', category: 'utility' },
  { id: 'expand-outline', label: 'Expand outline to prose', icon: <Pencil className="h-3.5 w-3.5" />, prompt: 'Expand the following outline into full prose. Write in third person past tense, maintaining a literary fiction style:\n\n', category: 'writing' },
];

interface PromptTemplatePickerProps {
  open: boolean;
  filter: string;
  onSelect: (template: PromptTemplate) => void;
  onClose: () => void;
}

export function PromptTemplatePicker({ open, filter, onSelect, onClose }: PromptTemplatePickerProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = BUILT_IN_TEMPLATES.filter((t) =>
    !filter || t.label.toLowerCase().includes(filter.toLowerCase()),
  );

  // Reset selection when filter changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [filter]);

  // Keyboard navigation
  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter' && filtered[selectedIndex]) {
        e.preventDefault();
        onSelect(filtered[selectedIndex]);
      } else if (e.key === 'Escape') {
        onClose();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, filtered, selectedIndex, onSelect, onClose]);

  if (!open || filtered.length === 0) return null;

  return (
    <div
      ref={listRef}
      className="absolute bottom-full left-0 mb-1 z-20 w-full max-h-[240px] overflow-y-auto rounded-lg border border-border bg-card shadow-lg"
    >
      <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Templates
      </div>
      {filtered.map((t, i) => (
        <button
          key={t.id}
          type="button"
          onClick={() => onSelect(t)}
          className={`flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors ${
            i === selectedIndex ? 'bg-accent/10 text-foreground' : 'text-muted-foreground hover:bg-secondary'
          }`}
        >
          <span className="shrink-0 text-accent">{t.icon}</span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium">{t.label}</p>
            <p className="truncate text-[10px] text-muted-foreground">{t.prompt.slice(0, 60)}...</p>
          </div>
          <span className="shrink-0 rounded bg-secondary px-1.5 py-0.5 text-[9px] text-muted-foreground">{t.category}</span>
        </button>
      ))}
    </div>
  );
}
