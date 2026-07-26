// G-C6 — icon + color pickers for the Genre / Kind draft modals. No new npm dep:
// native <input type="color"> + a hex text field, and a curated emoji grid + free text.
import { inputCls } from './FormBits';

const DEFAULT_COLOR = '#7c3aed';

// A small curated set of emoji useful for genre/kind glyphs.
const EMOJI = [
  '📖', '⚔️', '🐉', '🏰', '🔮', '🌌', '🚀', '🤖', '👤', '🧝',
  '🛡️', '🗺️', '💀', '🔥', '❄️', '⚡', '🌿', '👑', '🎭', '⭐',
];

export function ColorField({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  // <input type="color"> needs a valid #rrggbb; fall back to the default when empty.
  const swatch = /^#[0-9a-fA-F]{6}$/.test(value) ? value : DEFAULT_COLOR;
  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        aria-label="Color picker"
        value={swatch}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-12 cursor-pointer rounded-md border border-input bg-background p-1"
      />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={DEFAULT_COLOR}
        aria-label="Color hex"
        className={`${inputCls} font-mono`}
      />
    </div>
  );
}

export function IconField({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {EMOJI.map((emoji) => {
          const active = value === emoji;
          return (
            <button
              key={emoji}
              type="button"
              aria-label={`Use ${emoji}`}
              aria-pressed={active}
              onClick={() => onChange(emoji)}
              className={`flex h-8 w-8 items-center justify-center rounded-md border text-base hover:bg-secondary/60 ${
                active ? 'border-primary ring-1 ring-primary' : 'border-border'
              }`}
            >
              {emoji}
            </button>
          );
        })}
      </div>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Or type any glyph / short text"
        aria-label="Icon"
        className={inputCls}
      />
    </div>
  );
}
