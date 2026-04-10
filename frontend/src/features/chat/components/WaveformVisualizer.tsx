import { cn } from '@/lib/utils';

interface WaveformVisualizerProps {
  active: boolean;
  className?: string;
}

/** Animated waveform bars — CSS-only, no AudioContext needed.
 *  Keyframes defined in index.css as @keyframes waveform */
export function WaveformVisualizer({ active, className }: WaveformVisualizerProps) {
  return (
    <div className={cn('flex items-end justify-center gap-[3px] h-10', className)}>
      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
        <div
          key={i}
          className={cn(
            'w-1 rounded-full bg-primary transition-all duration-200',
            active ? 'animate-waveform' : 'h-1 opacity-30',
          )}
          style={active ? {
            animationDelay: `${i * 0.12}s`,
            animationDuration: `${0.8 + (i % 3) * 0.2}s`,
          } : undefined}
        />
      ))}
    </div>
  );
}
