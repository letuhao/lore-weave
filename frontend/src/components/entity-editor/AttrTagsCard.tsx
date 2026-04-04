import { useState } from 'react';
import { X } from 'lucide-react';
import type { AttrFieldProps } from './AttrTextCard';

export function AttrTagsCard({ value, onChange }: AttrFieldProps) {
  const tags = value ? value.split(',').map((t) => t.trim()).filter(Boolean) : [];
  const [input, setInput] = useState('');

  const addTag = () => {
    const trimmed = input.trim();
    if (trimmed && !tags.includes(trimmed)) {
      onChange([...tags, trimmed].join(', '));
    }
    setInput('');
  };

  const removeTag = (tag: string) => {
    onChange(tags.filter((t) => t !== tag).join(', '));
  };

  return (
    <div className="flex flex-wrap gap-1.5 rounded-md border bg-background p-2">
      {tags.map((tag) => (
        <span key={tag} className="inline-flex items-center gap-1 rounded bg-secondary px-2 py-0.5 text-xs">
          {tag}
          <button onClick={() => removeTag(tag)} className="text-muted-foreground/50 hover:text-foreground transition-colors">
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } }}
        onBlur={addTag}
        placeholder="+ Add tag"
        className="min-w-[80px] flex-1 bg-transparent px-1 py-0.5 text-xs outline-none placeholder:text-muted-foreground/40"
      />
    </div>
  );
}
