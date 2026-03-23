import type { EntityKind } from '../types';

type Props = {
  kind: Pick<EntityKind, 'icon' | 'name' | 'color'>;
  size?: 'sm' | 'md';
};

/**
 * Compact badge showing a kind's icon + name with its brand colour.
 */
export function KindBadge({ kind, size = 'sm' }: Props) {
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm';
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium ${textSize}`}
      style={{ borderColor: kind.color, color: kind.color }}
    >
      <span>{kind.icon}</span>
      <span>{kind.name}</span>
    </span>
  );
}
