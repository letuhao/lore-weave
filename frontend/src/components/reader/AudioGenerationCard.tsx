import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import type { SpeakableBlock, AudioSource } from '@/lib/audio-utils';

interface AudioGenerationCardProps {
  blocks: SpeakableBlock[];
  aiSegments?: Map<number, string>;
  /** Map of block_index → source_text_hash from stored audio segments */
  segmentHashes?: Map<number, string>;
}

type GenStatus = 'idle' | 'generating' | 'done';

/** SHA-256 hash matching the book-service textHash() function */
async function textHash(text: string): Promise<string> {
  const data = new TextEncoder().encode(text);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Shows generation progress, saved audio status, and content drift warnings.
 * Rendered inside AudioOverview or TTSSettings.
 */
export function AudioGenerationCard({ blocks, aiSegments, segmentHashes }: AudioGenerationCardProps) {
  const [genStatus, setGenStatus] = useState<GenStatus>('idle');
  const [genProgress, setGenProgress] = useState(0);
  const [driftIndices, setDriftIndices] = useState<number[]>([]);

  const textBlocks = blocks.filter((b) => b.type === 'text');
  const withAI = textBlocks.filter((b) => aiSegments?.has(b.index));
  const withoutAI = textBlocks.filter((b) => !aiSegments?.has(b.index) && !b.audioUrl);

  // Drift detection: compare current block text hash with stored segment hash
  useEffect(() => {
    if (!segmentHashes || segmentHashes.size === 0) {
      setDriftIndices([]);
      return;
    }
    let cancelled = false;
    const check = async () => {
      const drifted: number[] = [];
      for (const block of withAI) {
        const storedHash = segmentHashes.get(block.index);
        if (!storedHash || !block.text) continue;
        const currentHash = await textHash(block.text);
        if (currentHash !== storedHash) {
          drifted.push(block.index);
        }
      }
      if (!cancelled) setDriftIndices(drifted);
    };
    check();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [segmentHashes?.size, withAI.length]);

  const driftCount = driftIndices.length;

  if (textBlocks.length === 0) return null;

  return (
    <div className="space-y-2">
      {/* Saved audio card */}
      {withAI.length > 0 && (
        <div className="rounded-md border border-green-500/20 bg-green-500/5 p-2.5">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            <span className="text-[11px] font-medium text-green-400">
              {withAI.length} block{withAI.length !== 1 ? 's' : ''} with AI audio
            </span>
          </div>
          {driftCount > 0 && (
            <div className="mt-1 text-[10px] text-amber-400">
              {driftCount} block{driftCount !== 1 ? 's' : ''} may have changed since generation
            </div>
          )}
        </div>
      )}

      {/* Generation progress */}
      {genStatus === 'generating' && (
        <div className="rounded-md border bg-secondary p-2.5">
          <div className="mb-1.5 flex items-center justify-between text-[10px]">
            <span className="text-muted-foreground">Generating...</span>
            <span className="font-medium text-foreground">
              {genProgress}/{withoutAI.length}
            </span>
          </div>
          <div className="flex gap-[3px]">
            {withoutAI.map((_, i) => (
              <div
                key={i}
                className={cn(
                  'h-1.5 flex-1 rounded-full transition-colors',
                  i < genProgress ? 'bg-purple-500' : 'bg-border',
                )}
              />
            ))}
          </div>
        </div>
      )}

      {/* Generate button */}
      {withoutAI.length > 0 && genStatus === 'idle' && (
        <button
          type="button"
          className="w-full rounded-md bg-purple-600/80 px-3 py-2 text-[11px] font-medium text-white transition hover:bg-purple-500"
          onClick={() => {
            // Placeholder — simulate progress
            setGenStatus('generating');
            setGenProgress(0);
            let i = 0;
            const timer = setInterval(() => {
              i++;
              setGenProgress(i);
              if (i >= withoutAI.length) {
                clearInterval(timer);
                setGenStatus('done');
              }
            }, 500);
          }}
        >
          Generate {withoutAI.length} missing block{withoutAI.length !== 1 ? 's' : ''}
        </button>
      )}

      {genStatus === 'done' && (
        <div className="text-center text-[10px] text-green-400">
          Generation complete (simulated — wire to AU-03 endpoint with model selection)
        </div>
      )}
    </div>
  );
}
