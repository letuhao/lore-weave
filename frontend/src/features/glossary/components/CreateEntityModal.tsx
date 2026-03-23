import type { EntityKind } from '../types';

type Props = {
  kinds: EntityKind[];
  onSelect: (kind: EntityKind) => void;
  onClose: () => void;
  isCreating?: boolean;
};

// Group kind codes by genre for visual separation.
const GENRE_ORDER: { label: string; tags: string[] }[] = [
  { label: 'Universal', tags: ['universal'] },
  { label: 'Fantasy', tags: ['fantasy'] },
  { label: 'Romance / Drama', tags: ['romance', 'drama', 'historical'] },
];

function groupKinds(kinds: EntityKind[]) {
  return GENRE_ORDER.map(({ label, tags }) => ({
    label,
    kinds: kinds.filter((k) =>
      k.genre_tags.some((t) => tags.includes(t)) &&
      !kinds
        .filter((k2) =>
          GENRE_ORDER.slice(0, GENRE_ORDER.findIndex((g) => g.tags.includes(tags[0])))
            .flatMap((g) => g.tags)
            .some((t) => k2.genre_tags.includes(t))
        )
        .includes(k),
    ),
  })).filter((g) => g.kinds.length > 0);
}

/**
 * Modal presenting the 12 default entity kinds as a clickable grid.
 * In SP-1 the onSelect callback is wired but creation is a no-op until SP-2.
 */
export function CreateEntityModal({ kinds, onSelect, onClose, isCreating = false }: Props) {
  // Simple grouping: universal first, then fantasy, then romance/drama
  const universal = kinds.filter((k) => k.genre_tags.includes('universal'));
  const fantasy = kinds.filter(
    (k) => k.genre_tags.includes('fantasy') && !k.genre_tags.includes('universal'),
  );
  const romance = kinds.filter(
    (k) =>
      (k.genre_tags.includes('romance') || k.genre_tags.includes('drama') || k.genre_tags.includes('historical')) &&
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
            className="text-muted-foreground hover:text-foreground"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="space-y-4">
          {groups.map((group) => (
            <div key={group.label}>
              <p className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
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
                    <span className="text-xs font-medium leading-tight" style={{ color: kind.color }}>
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
