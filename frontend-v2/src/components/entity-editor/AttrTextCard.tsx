export interface AttrFieldProps {
  value: string;
  onChange: (value: string) => void;
  options?: string[];
}

export function AttrTextCard({ value, onChange }: AttrFieldProps) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-md border bg-background px-3 py-2 text-[13px] focus:border-ring focus:outline-none focus:ring-[3px] focus:ring-ring/15 transition-all"
    />
  );
}
