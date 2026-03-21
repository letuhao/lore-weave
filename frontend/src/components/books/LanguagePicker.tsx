import { useMemo } from 'react';

type LanguageOption = {
  code: string;
  label: string;
};

const PRESET_LANGUAGES: LanguageOption[] = [
  { code: 'en', label: 'English (en)' },
  { code: 'vi', label: 'Vietnamese (vi)' },
  { code: 'ja', label: 'Japanese (ja)' },
  { code: 'zh-Hans', label: 'Chinese Simplified (zh-Hans)' },
  { code: 'zh-Hant', label: 'Chinese Traditional (zh-Hant)' },
  { code: 'ko', label: 'Korean (ko)' },
];

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
  placeholder = 'Original language (e.g. en)',
}: Props) {
  const selected = useMemo(
    () => PRESET_LANGUAGES.find((o) => o.code.toLowerCase() === value.toLowerCase()),
    [value],
  );

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">
        {label}
        {required ? ' *' : ''}
      </label>
      <select
        className="w-full rounded border px-2 py-2 text-sm"
        value={selected?.code || ''}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Select language</option>
        {PRESET_LANGUAGES.map((item) => (
          <option key={item.code} value={item.code}>
            {item.label}
          </option>
        ))}
      </select>
      <input
        className="w-full rounded border px-2 py-2 text-sm"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
      />
    </div>
  );
}
