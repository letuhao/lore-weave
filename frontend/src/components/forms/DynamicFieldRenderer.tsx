import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { TagInput } from '@/components/data/FilterToolbar';
import type { FieldType } from '@/features/glossary/types';

interface DynamicFieldProps {
  fieldType: FieldType;
  value: string;
  onChange: (value: string) => void;
  options?: string[];
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
}

/**
 * Renders the appropriate form control based on a dynamic FieldType definition.
 * Maps each glossary attribute field_type to a concrete UI component.
 */
export function DynamicFieldRenderer({
  fieldType,
  value,
  onChange,
  options = [],
  required,
  disabled,
  placeholder,
}: DynamicFieldProps) {
  switch (fieldType) {
    case 'text':
      return (
        <Input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          disabled={disabled}
          placeholder={placeholder}
          className="h-8 text-sm"
        />
      );

    case 'textarea':
      return (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          disabled={disabled}
          placeholder={placeholder}
          rows={3}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        />
      );

    case 'select':
      return (
        <Select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          disabled={disabled}
          className="h-8 text-sm"
        >
          <option value="">Select…</option>
          {options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </Select>
      );

    case 'number':
      return (
        <Input
          type="number"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          disabled={disabled}
          placeholder={placeholder}
          className="h-8 text-sm"
        />
      );

    case 'date':
      return (
        <Input
          type="date"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          disabled={disabled}
          className="h-8 text-sm"
        />
      );

    case 'url':
      return (
        <Input
          type="url"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          disabled={disabled}
          placeholder={placeholder || 'https://…'}
          className="h-8 text-sm"
        />
      );

    case 'boolean':
      return (
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={value === 'true'}
            onChange={(e) => onChange(String(e.target.checked))}
            disabled={disabled}
            className="h-4 w-4 rounded border-input accent-primary"
          />
          <span className="text-muted-foreground">{placeholder || 'Yes'}</span>
        </label>
      );

    case 'tags':
      return (
        <TagInput
          tags={value ? value.split(',').filter(Boolean) : []}
          onChange={(tags) => onChange(tags.join(','))}
          placeholder={placeholder || 'Add tag…'}
        />
      );

    default:
      return (
        <Input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder={placeholder}
          className="h-8 text-sm"
        />
      );
  }
}
