import { useId } from 'react';
import { LANGUAGE_CODES } from '@/data/languageCodes';

type Props = {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  required?: boolean;
  placeholder?: string;
};

export function LanguagePicker({
  value,
  onChange,
  label = 'Language',
  required,
  placeholder = 'e.g. en, vi, zh-Hans',
}: Props) {
  const uid = useId();
  const datalistId = `language-picker-list-${uid}`;

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">
        {label}
        {required ? ' *' : ''}
      </label>
      <input
        className="w-full rounded border px-2 py-2 text-sm"
        list={datalistId}
        placeholder={placeholder}
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value)}
      />
      <datalist id={datalistId}>
        {LANGUAGE_CODES.map((entry) => (
          <option key={entry.code} value={entry.code}>
            {entry.name} ({entry.code})
          </option>
        ))}
      </datalist>
    </div>
  );
}
