import type { AttrFieldProps } from './AttrTextCard';

export function AttrDateCard({ value, onChange }: AttrFieldProps) {
  return (
    <input
      type="date"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-[200px] rounded-md border bg-background px-3 py-2 text-[13px] focus:border-ring focus:outline-none focus:ring-[3px] focus:ring-ring/15 transition-all"
    />
  );
}
