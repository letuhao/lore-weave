import { useState } from 'react';
import { Save } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

const STORAGE_KEY = 'lw_reading_prefs';

type ReadingPrefs = {
  fontSize: number;
  lineSpacing: number;
  theme: 'system' | 'dark' | 'sepia';
  fontFamily: 'sans' | 'serif' | 'mono';
};

const DEFAULTS: ReadingPrefs = { fontSize: 16, lineSpacing: 1.8, theme: 'system', fontFamily: 'serif' };

function loadPrefs(): ReadingPrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

const THEMES = [
  { id: 'system', label: 'System', preview: 'bg-background border' },
  { id: 'dark', label: 'Dark', preview: 'bg-[#181412] border border-[#332d28]' },
  { id: 'sepia', label: 'Sepia', preview: 'bg-[#f4ecd8] border border-[#d4c9a8]' },
] as const;

const FONTS = [
  { id: 'sans', label: 'Sans-serif', cls: 'font-sans' },
  { id: 'serif', label: 'Serif', cls: 'font-serif' },
  { id: 'mono', label: 'Monospace', cls: 'font-mono' },
] as const;

export function ReadingTab() {
  const [saved, setSaved] = useState<ReadingPrefs>(loadPrefs);
  const [prefs, setPrefs] = useState<ReadingPrefs>(loadPrefs);

  const isDirty = JSON.stringify(prefs) !== JSON.stringify(saved);

  function save() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    setSaved({ ...prefs });
    toast.success('Reading preferences saved');
  }

  return (
    <div>
      <div className="border-b py-5">
        <h2 className="text-sm font-semibold">Reading Preferences</h2>
        <p className="mb-4 text-xs text-muted-foreground">Customize the reading experience. Settings are stored locally.</p>

        {/* Font size */}
        <div className="mb-5">
          <label className="mb-2 block text-xs font-medium">Font Size: {prefs.fontSize}px</label>
          <input
            type="range"
            min={12}
            max={24}
            step={1}
            value={prefs.fontSize}
            onChange={(e) => setPrefs({ ...prefs, fontSize: Number(e.target.value) })}
            aria-label="Font size in pixels"
            className="w-full max-w-xs accent-primary"
          />
          <div className="mt-1 flex justify-between text-[10px] text-muted-foreground" style={{ maxWidth: 320 }}>
            <span>12px</span><span>18px</span><span>24px</span>
          </div>
        </div>

        {/* Line spacing */}
        <div className="mb-5">
          <label className="mb-2 block text-xs font-medium">Line Spacing: {prefs.lineSpacing.toFixed(1)}</label>
          <input
            type="range"
            min={1.2}
            max={2.4}
            step={0.1}
            value={prefs.lineSpacing}
            onChange={(e) => setPrefs({ ...prefs, lineSpacing: Number(e.target.value) })}
            aria-label="Line spacing multiplier"
            className="w-full max-w-xs accent-primary"
          />
        </div>

        {/* Font family */}
        <div className="mb-5">
          <label className="mb-2 block text-xs font-medium">Font Family</label>
          <div className="flex gap-2">
            {FONTS.map((f) => (
              <button
                key={f.id}
                onClick={() => setPrefs({ ...prefs, fontFamily: f.id as ReadingPrefs['fontFamily'] })}
                className={cn(
                  'rounded-md border px-4 py-2 text-[13px] transition-colors',
                  f.cls,
                  prefs.fontFamily === f.id
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'hover:bg-secondary',
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Theme */}
        <div className="mb-5">
          <label className="mb-2 block text-xs font-medium">Reader Theme</label>
          <div className="flex gap-2">
            {THEMES.map((t) => (
              <button
                key={t.id}
                onClick={() => setPrefs({ ...prefs, theme: t.id as ReadingPrefs['theme'] })}
                className={cn(
                  'flex items-center gap-2 rounded-md border px-4 py-2 text-[13px] transition-colors',
                  prefs.theme === t.id ? 'border-primary ring-1 ring-primary/30' : '',
                )}
              >
                <span className={cn('h-4 w-4 rounded', t.preview)} />
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Preview */}
        <div className="mb-4">
          <label className="mb-2 block text-xs font-medium">Preview</label>
          <div className="rounded-md border bg-card p-4">
            <p
              className={cn(
                prefs.fontFamily === 'serif' ? 'font-serif' : prefs.fontFamily === 'mono' ? 'font-mono' : 'font-sans',
              )}
              style={{ fontSize: prefs.fontSize, lineHeight: prefs.lineSpacing }}
            >
              The throne room was silent save for the quiet crackling of magical torches. The Demon Lord sat cross-legged, examining a scroll detailing the latest territorial dispute with the neighboring kingdom of Aerolia.
            </p>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            onClick={save}
            disabled={!isDirty}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
          >
            <Save className="h-3 w-3" />
            Save Preferences
          </button>
        </div>
      </div>
    </div>
  );
}
