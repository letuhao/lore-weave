import type { LanguageVersionGroup, VersionSummary } from '@/features/translation/versionsApi';
import { STATUS_COLOR, STATUS_ICON } from './TranslationStatusCell';

type Props = {
  /** All language groups from the API */
  languages: LanguageVersionGroup[];
  /** Currently selected language (null = show original) */
  selectedLang: string | null;
  onLangChange: (lang: string | null) => void;
  /** Selected version id within the current language */
  selectedVersionId: string | null;
  onVersionSelect: (id: string) => void;
  onRetranslate: () => void;
  originalLanguage?: string | null;
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function VersionSidebar({
  languages,
  selectedLang,
  onLangChange,
  selectedVersionId,
  onVersionSelect,
  onRetranslate,
  originalLanguage,
}: Props) {
  const currentGroup = languages.find((g) => g.target_language === selectedLang) ?? null;

  // Build dropdown options
  const langOptions: { value: string | null; label: string }[] = [
    { value: null, label: `Original${originalLanguage ? ` (${originalLanguage})` : ''}` },
    ...languages.map((g) => ({
      value: g.target_language,
      label: `${g.target_language} — ${g.versions.length} version${g.versions.length !== 1 ? 's' : ''}`,
    })),
  ];

  return (
    <div className="flex h-full flex-col gap-4">
      {/* Language dropdown */}
      <div className="space-y-1">
        <label className="text-xs font-medium text-muted-foreground">Language</label>
        <select
          className="w-full rounded border px-2 py-1.5 text-sm"
          value={selectedLang ?? ''}
          onChange={(e) => onLangChange(e.target.value === '' ? null : e.target.value)}
        >
          {langOptions.map((o) => (
            <option key={o.value ?? '__original'} value={o.value ?? ''}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {/* Version list — only shown when a translation language is selected */}
      {currentGroup && (
        <div className="flex flex-1 flex-col gap-1 overflow-y-auto">
          <p className="text-xs font-medium text-muted-foreground">Versions</p>
          {currentGroup.versions.map((v) => (
            <VersionRow
              key={v.id}
              version={v}
              selected={v.id === selectedVersionId}
              onClick={() => onVersionSelect(v.id)}
            />
          ))}
        </div>
      )}

      {/* Re-translate button */}
      <button
        onClick={onRetranslate}
        className="mt-auto rounded border px-3 py-1.5 text-sm hover:bg-muted"
      >
        + Translate…
      </button>
    </div>
  );
}

function VersionRow({
  version,
  selected,
  onClick,
}: {
  version: VersionSummary;
  selected: boolean;
  onClick: () => void;
}) {
  const statusKey = version.is_active ? 'active' : version.status === 'completed' ? 'translated' : version.status === 'running' ? 'running' : 'failed';
  const color = STATUS_COLOR[statusKey as keyof typeof STATUS_COLOR] ?? 'text-muted-foreground';
  const icon = STATUS_ICON[statusKey as keyof typeof STATUS_ICON] ?? '?';

  return (
    <button
      onClick={onClick}
      className={`w-full rounded border px-3 py-2 text-left text-sm transition-colors ${
        selected ? 'border-primary bg-primary/5' : 'hover:bg-muted'
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="font-medium">v{version.version_num}</span>
        <span className={`${color} text-xs`}>
          {icon} {version.is_active ? 'Active' : version.status}
        </span>
      </div>
      <p className="mt-0.5 text-xs text-muted-foreground">{formatDate(version.created_at)}</p>
      {version.input_tokens != null && version.output_tokens != null && (
        <p className="mt-0.5 text-xs text-muted-foreground">
          {version.input_tokens} → {version.output_tokens} tokens
        </p>
      )}
    </button>
  );
}
