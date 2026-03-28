import { useState } from 'react';
import { DynamicFieldRenderer } from './DynamicFieldRenderer';
import { Button } from '@/components/ui/button';
import type { AttributeDefinition } from '@/features/glossary/types';

interface DynamicFormProps {
  attributes: AttributeDefinition[];
  values: Record<string, string>;
  onChange: (attrCode: string, value: string) => void;
  onSave?: () => void;
  isSaving?: boolean;
  disabled?: boolean;
  /** Show in 2-column layout when there are many fields. */
  compact?: boolean;
}

/**
 * Renders a complete form from an array of AttributeDefinitions.
 * Adapts layout based on field count: 1 column for few fields, 2 columns for many.
 */
export function DynamicForm({
  attributes,
  values,
  onChange,
  onSave,
  isSaving,
  disabled,
  compact,
}: DynamicFormProps) {
  const sorted = [...attributes].sort((a, b) => a.sort_order - b.sort_order);
  const useGrid = compact || sorted.length > 4;

  return (
    <div className="space-y-4">
      <div className={useGrid ? 'grid gap-4 sm:grid-cols-2' : 'space-y-4'}>
        {sorted.map((attr) => {
          // Textarea and tags always take full width
          const fullWidth = attr.field_type === 'textarea' || attr.field_type === 'tags';

          return (
            <div
              key={attr.attr_def_id}
              className={fullWidth && useGrid ? 'sm:col-span-2' : undefined}
            >
              <label className="mb-1 block text-xs font-medium text-foreground">
                {attr.name}
                {attr.is_required && <span className="ml-0.5 text-destructive">*</span>}
              </label>
              <DynamicFieldRenderer
                fieldType={attr.field_type}
                value={values[attr.code] ?? ''}
                onChange={(v) => onChange(attr.code, v)}
                options={attr.options}
                required={attr.is_required}
                disabled={disabled}
                placeholder={attr.name}
              />
            </div>
          );
        })}
      </div>

      {onSave && (
        <div className="flex justify-end">
          <Button size="sm" onClick={onSave} disabled={isSaving || disabled}>
            {isSaving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      )}
    </div>
  );
}
