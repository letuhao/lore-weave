import { useState } from 'react';
import type { FieldType } from '../types';

type Props = {
  fieldType: FieldType;
  options?: string[];
  value: string;
  onChange: (val: string) => void;
  onFocus?: () => void;
  onBlur?: () => void;
  disabled?: boolean;
};

const INPUT_CLS =
  'w-full rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50';

export function AttributeValueInput({ fieldType, options, value, onChange, onFocus, onBlur, disabled }: Props) {
  // For tags: maintain chip array from comma-separated value
  const [tagInput, setTagInput] = useState('');

  if (fieldType === 'textarea') {
    return (
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={onFocus}
        onBlur={onBlur}
        disabled={disabled}
        rows={3}
        className={INPUT_CLS + ' resize-y'}
      />
    );
  }

  if (fieldType === 'select' && options && options.length > 0) {
    return (
      <select
        value={value}
        onChange={(e) => { onChange(e.target.value); onBlur?.(); }}
        onFocus={onFocus}
        disabled={disabled}
        className={INPUT_CLS}
      >
        <option value="">— select —</option>
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    );
  }

  if (fieldType === 'boolean') {
    return (
      <select
        value={value}
        onChange={(e) => { onChange(e.target.value); onBlur?.(); }}
        onFocus={onFocus}
        disabled={disabled}
        className={INPUT_CLS}
      >
        <option value="">—</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    );
  }

  if (fieldType === 'tags') {
    const chips = value ? value.split(',').map((t) => t.trim()).filter(Boolean) : [];

    function removeChip(chip: string) {
      const next = chips.filter((c) => c !== chip).join(', ');
      onChange(next);
      onBlur?.();
    }

    function addChip(raw: string) {
      const tag = raw.trim();
      if (!tag || chips.includes(tag)) return;
      const next = [...chips, tag].join(', ');
      onChange(next);
      setTagInput('');
      onBlur?.();
    }

    return (
      <div
        className="flex flex-wrap items-center gap-1 rounded border bg-background px-2 py-1 text-sm"
        onFocusCapture={onFocus}
      >
        {chips.map((chip) => (
          <span
            key={chip}
            className="inline-flex items-center gap-0.5 rounded-full bg-muted px-2 py-0.5 text-xs"
          >
            {chip}
            <button
              type="button"
              onClick={() => removeChip(chip)}
              disabled={disabled}
              className="hover:text-destructive disabled:opacity-50"
              aria-label={`Remove ${chip}`}
            >
              ✕
            </button>
          </span>
        ))}
        <input
          type="text"
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ',') {
              e.preventDefault();
              addChip(tagInput);
            }
          }}
          onBlur={() => { if (tagInput) addChip(tagInput); }}
          disabled={disabled}
          placeholder="Add tag…"
          className="min-w-[80px] flex-1 bg-transparent text-sm focus:outline-none"
        />
      </div>
    );
  }

  // text | number | date | url — all render as <input>
  const inputType =
    fieldType === 'number' ? 'number' :
    fieldType === 'url' ? 'url' :
    'text';

  return (
    <input
      type={inputType}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onFocus={onFocus}
      onBlur={onBlur}
      disabled={disabled}
      className={INPUT_CLS}
    />
  );
}
