import type { AttrFieldProps } from './AttrTextCard';

export function AttrUrlCard({ value, onChange }: AttrFieldProps) {
  return (
    <input
      type="url"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder="https://..."
      className="w-full rounded-md border bg-background px-3 py-2 font-mono text-xs focus:border-ring focus:outline-none focus:ring-[3px] focus:ring-ring/15 transition-all"
    />
  );
}
