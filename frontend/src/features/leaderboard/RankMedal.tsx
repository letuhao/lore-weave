import { cn } from '@/lib/utils';

const medalStyles: Record<number, string> = {
  1: 'bg-gradient-to-br from-[#e8a832] to-[#d4952a] text-[#1a1008] shadow-[0_0_12px_rgba(232,168,50,0.3)]',
  2: 'bg-gradient-to-br from-[#c0c0c0] to-[#a0a0a0] text-[#1a1a1a]',
  3: 'bg-gradient-to-br from-[#cd7f32] to-[#b06828] text-[#1a1008]',
};

export function RankMedal({ rank, size = 'md' }: { rank: number; size?: 'sm' | 'md' }) {
  const dim = size === 'sm' ? 'w-[22px] h-[22px] text-[10px]' : 'w-7 h-7 text-xs';

  if (rank <= 3) {
    return (
      <span className={cn('flex shrink-0 items-center justify-center rounded-full font-bold', dim, medalStyles[rank])}>
        {rank}
      </span>
    );
  }

  return (
    <span className={cn('flex shrink-0 items-center justify-center font-mono font-semibold text-muted-foreground', dim)}>
      {rank}
    </span>
  );
}
