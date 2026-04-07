const KNOWN_FLAGS = ['chat', 'vision', 'tool_calling', 'extended_thinking', 'json_mode', 'reasoning', 'tts', 'stt', 'image_gen', 'video_gen', 'embedding', 'moderation'] as const;

type Props = {
  flags: Record<string, boolean>;
  onChange: (flags: Record<string, boolean>) => void;
};

function formatLabel(flag: string): string {
  return flag.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function CapabilityFlags({ flags, onChange }: Props) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium">Capabilities</label>
      <div className="flex flex-wrap gap-3">
        {KNOWN_FLAGS.map((f) => (
          <label key={f} className="flex items-center gap-1.5 text-xs cursor-pointer">
            <input
              type="checkbox"
              checked={flags[f] ?? false}
              onChange={(e) => onChange({ ...flags, [f]: e.target.checked })}
              className="accent-primary"
            />
            {formatLabel(f)}
          </label>
        ))}
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Auto-detected from model config. Toggle to override.
      </p>
    </div>
  );
}

export { KNOWN_FLAGS };
