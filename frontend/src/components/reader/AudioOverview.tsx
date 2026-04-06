import type { JSONContent } from '@tiptap/react';
import { extractSpeakableBlocks, resolveAudioSource, type SpeakableBlock, type AudioSource } from '@/lib/audio-utils';
import { cn } from '@/lib/utils';

const SOURCE_COLORS: Record<AudioSource | 'none', string> = {
  attached: '#8b5cf6',
  ai: '#5496e8',
  browser: '#9e9488',
  inline: '#8b5cf6',
  none: '#4a423b',
};

const SOURCE_LABELS: Record<AudioSource | 'none', string> = {
  attached: 'Attached',
  ai: 'AI TTS',
  browser: 'Browser',
  inline: 'Audio Block',
  none: 'None',
};

interface AudioOverviewProps {
  blocks: JSONContent[];
  aiSegments?: Map<number, string>;
}

export function AudioOverview({ blocks, aiSegments }: AudioOverviewProps) {
  const speakable = extractSpeakableBlocks(blocks);

  // Count by source
  const counts: Record<string, number> = {};
  let missingCount = 0;
  let totalChars = 0;

  const rows = speakable.map((block) => {
    const { source } = resolveAudioSource(block, aiSegments);
    counts[source] = (counts[source] || 0) + 1;
    if (source === 'browser' && block.type === 'text') {
      missingCount++;
      totalChars += block.text.length;
    }
    return { block, source };
  });

  // Rough cost estimate: ~$15/1M chars for TTS
  const estimatedCost = totalChars > 0 ? (totalChars / 1_000_000) * 15 : 0;

  return (
    <div className="flex flex-col gap-3 p-3 text-xs">
      {/* Summary */}
      <div className="rounded-md border bg-secondary p-3">
        <div className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Audio Coverage
        </div>
        <div className="flex flex-wrap gap-2">
          {Object.entries(counts).map(([src, count]) => (
            <span
              key={src}
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
              style={{
                background: `${SOURCE_COLORS[src as AudioSource] || SOURCE_COLORS.none}18`,
                color: SOURCE_COLORS[src as AudioSource] || SOURCE_COLORS.none,
              }}
            >
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: SOURCE_COLORS[src as AudioSource] || SOURCE_COLORS.none }} />
              {SOURCE_LABELS[src as AudioSource] || src}: {count}
            </span>
          ))}
        </div>
        <div className="mt-2 text-[10px] text-muted-foreground">
          {speakable.length} speakable blocks · {missingCount} using browser TTS
        </div>
      </div>

      {/* Generate missing */}
      {missingCount > 0 && (
        <div className="rounded-md border border-purple-500/20 bg-purple-500/5 p-3">
          <div className="mb-1 text-[11px] font-medium text-purple-400">
            Generate Missing Audio
          </div>
          <div className="text-[10px] text-muted-foreground">
            {missingCount} block{missingCount !== 1 ? 's' : ''} · ~{totalChars.toLocaleString()} characters
            {estimatedCost > 0 && (
              <> · est. ${estimatedCost.toFixed(4)}</>
            )}
          </div>
          <button
            type="button"
            className="mt-2 rounded-md bg-purple-600 px-3 py-1.5 text-[11px] font-medium text-white transition hover:bg-purple-500"
            onClick={() => {
              // Full generation wired in AU-24
              console.info('Bulk TTS generation: requires model selection (AU-24)');
            }}
          >
            Generate All ({missingCount})
          </button>
        </div>
      )}

      {/* Per-block list */}
      <div className="space-y-1">
        <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Blocks
        </div>
        {rows.map(({ block, source }, i) => (
          <BlockRow key={i} block={block} source={source} />
        ))}
      </div>
    </div>
  );
}

function BlockRow({ block, source }: { block: SpeakableBlock; source: AudioSource }) {
  const color = SOURCE_COLORS[source];
  const label = SOURCE_LABELS[source];
  const preview = block.type === 'audio'
    ? (block.subtitle || 'Audio block')
    : block.text;

  return (
    <div className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-secondary">
      <span
        className="h-2 w-2 flex-shrink-0 rounded-full"
        style={{ background: color }}
        title={label}
      />
      <span className="min-w-0 flex-1 truncate text-foreground">
        {preview.slice(0, 80)}{preview.length > 80 ? '...' : ''}
      </span>
      <span
        className="flex-shrink-0 rounded-full px-1.5 py-0.5 text-[8px] font-medium"
        style={{ background: `${color}18`, color }}
      >
        {label}
      </span>
    </div>
  );
}
