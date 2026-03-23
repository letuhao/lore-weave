import type { EntityKind } from '../types';

type Props = {
  kinds: EntityKind[];
  onSelect: (kind: EntityKind) => void;
  onClose: () => void;
  isCreating?: boolean;
  createError?: string;
};

/**
 * Modal presenting the 12 default entity kinds as a clickable grid.
 * In SP-2 onSelect triggers entity creation in the parent (GlossaryPage).
 */
export function CreateEntityModal({
  kinds,
  onSelect,
  onClose,
  isCreating = false,
  createError = '',
}: Props) {
  const universal = kinds.filter((k) => k.genre_tags.includes('universal'));
  const fantasy = kinds.filter(
    (k) => k.genre_tags.includes('fantasy') && !k.genre_tags.includes('universal'),
  );
  const romance = kinds.filter(
    (k) =>
      (k.genre_tags.includes('romance') ||
        k.genre_tags.includes('drama') ||
        k.genre_tags.includes('historical')) &&
      !k.genre_tags.includes('universal') &&
      !k.genre_tags.includes('fantasy'),
  );

  const groups = [
    { label: 'Universal', kinds: universal },
    { label: 'Fantasy', kinds: fantasy },
    { label: 'Romance / Drama', kinds: romance },
  ].filter((g) => g.kinds.length > 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">Choose entity type</h2>
          <button
            onClick={onClose}
            disabled={isCreating}
            className="text-muted-foreground hover:text-foreground disabled:opacity-50"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {createError && (
          <p className="mb-3 rounded border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {createError}
          </p>
        )}

        {isCreating && (
          <div className="mb-3 text-center text-sm text-muted-foreground">
            Creating entity…
          </div>
        )}

        <div className="space-y-4">
          {groups.map((group) => (
            <div key={group.label}>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {group.label}
              </p>
              <div className="grid grid-cols-3 gap-2">
                {group.kinds.map((kind) => (
                  <button
                    key={kind.kind_id}
                    disabled={isCreating}
                    onClick={() => onSelect(kind)}
                    className="flex flex-col items-center gap-1 rounded border p-3 text-center transition hover:bg-muted disabled:opacity-50"
                    style={{ borderColor: kind.color + '40' }}
                  >
                    <span className="text-2xl">{kind.icon}</span>
                    <span
                      className="text-xs font-medium leading-tight"
                      style={{ color: kind.color }}
                    >
                      {kind.name}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
