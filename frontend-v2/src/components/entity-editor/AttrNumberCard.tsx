import type { AttrFieldProps } from './AttrTextCard';

export function AttrNumberCard({ value, onChange }: AttrFieldProps) {
  return (
    <input
      type="number"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-[140px] rounded-md border bg-background px-3 py-2 text-[13px] focus:border-ring focus:outline-none focus:ring-[3px] focus:ring-ring/15 transition-all"
    />
  );
}
