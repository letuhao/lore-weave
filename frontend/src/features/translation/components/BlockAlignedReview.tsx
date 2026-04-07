import { useState, useRef, useCallback, useEffect } from 'react';
import type { JSONContent } from '@tiptap/react';
import { cn } from '@/lib/utils';
import { InlineRenderer } from '@/components/reader/InlineRenderer';

// ── Block type classification ──────────────────────────────────────────────

const TRANSLATE_TYPES = new Set(['paragraph', 'heading', 'blockquote', 'callout', 'bulletList', 'orderedList', 'listItem']);
const PASSTHROUGH_TYPES = new Set(['horizontalRule', 'codeBlock']);
const CAPTION_TYPES = new Set(['imageBlock', 'videoBlock', 'audioBlock']);

type BlockAction = 'translate' | 'passthrough' | 'caption';

function classifyBlock(block: JSONContent): BlockAction {
  const t = block.type ?? '';
  if (PASSTHROUGH_TYPES.has(t)) return 'passthrough';
  if (CAPTION_TYPES.has(t)) return 'caption';
  if (TRANSLATE_TYPES.has(t)) return 'translate';
  return 'passthrough';
}

function blockTypeLabel(block: JSONContent): string {
  switch (block.type) {
    case 'paragraph': return 'P';
    case 'heading': return `H${block.attrs?.level ?? ''}`;
    case 'blockquote': return 'BQ';
    case 'callout': return 'NOTE';
    case 'bulletList': return 'UL';
    case 'orderedList': return 'OL';
    case 'codeBlock': return 'CODE';
    case 'imageBlock': return 'IMG';
    case 'videoBlock': return 'VID';
    case 'audioBlock': return 'AUD';
    case 'horizontalRule': return 'HR';
    default: return block.type?.slice(0, 4)?.toUpperCase() ?? '?';
  }
}

function typeBadgeColor(action: BlockAction): string {
  switch (action) {
    case 'translate': return 'bg-secondary text-muted-foreground';
    case 'passthrough': return 'bg-muted text-muted-foreground/60';
    case 'caption': return 'bg-[#3da692]/10 text-[#3da692]';
  }
}

// ── Extract plain text for diff comparison ─────────────────────────────────

function extractText(content?: JSONContent[]): string {
  if (!content) return '';
  return content.map(n => {
    if (n.type === 'text') return n.text || '';
    if (n.type === 'hardBreak') return '\n';
    return extractText(n.content);
  }).join('');
}

// ── Props ──────────────────────────────────────────────────────────────────

interface BlockAlignedReviewProps {
  originalBlocks: JSONContent[];
  translatedBlocks: JSONContent[];
  showPassthrough?: boolean;
  activeIndex?: number | null;
  onBlockClick?: (index: number) => void;
}

export function BlockAlignedReview({
  originalBlocks,
  translatedBlocks,
  showPassthrough = true,
  activeIndex = null,
  onBlockClick,
}: BlockAlignedReviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const maxLen = Math.max(originalBlocks.length, translatedBlocks.length);

  return (
    <div ref={containerRef} className="flex flex-col divide-y divide-border/30">
      {Array.from({ length: maxLen }, (_, i) => {
        const orig = originalBlocks[i];
        const trans = translatedBlocks[i];
        const block = orig ?? trans;
        if (!block) return null;

        const action = classifyBlock(block);
        if (!showPassthrough && action === 'passthrough') return null;

        return (
          <BlockRow
            key={i}
            index={i}
            original={orig}
            translated={trans}
            action={action}
            isActive={activeIndex === i}
            onClick={() => onBlockClick?.(i)}
          />
        );
      })}
    </div>
  );
}

// ── Single block row ───────────────────────────────────────────────────────

interface BlockRowProps {
  index: number;
  original?: JSONContent;
  translated?: JSONContent;
  action: BlockAction;
  isActive: boolean;
  onClick: () => void;
}

function BlockRow({ index, original, translated, action, isActive, onClick }: BlockRowProps) {
  const block = original ?? translated!;
  const label = blockTypeLabel(block);
  const badgeColor = typeBadgeColor(action);

  // Passthrough: show once, spanning full width
  if (action === 'passthrough') {
    return (
      <div
        className={cn(
          'flex min-h-[40px] transition-colors cursor-pointer',
          isActive ? 'bg-primary/5' : 'hover:bg-secondary/30',
        )}
        onClick={onClick}
      >
        <Gutter index={index} label={label} badgeColor={badgeColor} />
        <div className="flex-1 px-4 py-2.5 text-muted-foreground/60">
          {block.type === 'horizontalRule' ? (
            <hr className="border-border/50 my-2" />
          ) : block.type === 'codeBlock' ? (
            <pre className="font-mono text-[11px] leading-relaxed bg-secondary/50 rounded px-3 py-2 overflow-x-auto">
              {extractText(block.content)}
            </pre>
          ) : (
            <span className="text-xs italic">Unchanged</span>
          )}
        </div>
      </div>
    );
  }

  // Caption-only: show image/media with caption comparison
  if (action === 'caption') {
    const origCaption = original?.attrs?.caption ?? '';
    const transCaption = translated?.attrs?.caption ?? origCaption;
    const src = block.attrs?.src;

    return (
      <div
        className={cn(
          'flex min-h-[48px] transition-colors cursor-pointer',
          isActive ? 'bg-primary/5' : 'hover:bg-secondary/30',
        )}
        onClick={onClick}
      >
        <Gutter index={index} label={label} badgeColor={badgeColor} />
        <div className="flex flex-1">
          {/* Source side */}
          <div className="flex-1 px-4 py-2.5 flex items-center gap-3">
            {src && (
              <div className="w-16 h-10 rounded bg-secondary flex items-center justify-center overflow-hidden shrink-0 border border-border/50">
                <img src={src} alt="" className="w-full h-full object-cover" onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }} />
              </div>
            )}
            <span className="text-xs text-muted-foreground">{origCaption || '(no caption)'}</span>
          </div>
          {/* Divider */}
          <div className="w-px bg-border/50 shrink-0" />
          {/* Translation side */}
          <div className="flex-1 px-4 py-2.5 flex items-center gap-3">
            {src && (
              <div className="w-16 h-10 rounded bg-secondary flex items-center justify-center overflow-hidden shrink-0 border border-border/50">
                <img src={src} alt="" className="w-full h-full object-cover" onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }} />
              </div>
            )}
            <span className={cn('text-xs', transCaption !== origCaption ? 'text-foreground' : 'text-muted-foreground')}>
              {transCaption || '(no caption)'}
            </span>
          </div>
        </div>
      </div>
    );
  }

  // Translatable block: source | translation side by side
  const origText = extractText(original?.content);
  const transText = extractText(translated?.content);
  const isEmpty = !transText;
  const isHeading = block.type === 'heading';

  return (
    <div
      className={cn(
        'flex min-h-[48px] transition-colors cursor-pointer',
        isActive ? 'bg-primary/5' : 'hover:bg-secondary/30',
      )}
      onClick={onClick}
    >
      <Gutter index={index} label={label} badgeColor={badgeColor} hasWarning={isEmpty} />
      <div className="flex flex-1">
        {/* Source pane */}
        <div className={cn(
          'flex-1 px-4 py-2.5 font-serif leading-[1.7] text-foreground/80',
          isHeading ? 'text-base font-semibold' : 'text-sm',
        )}>
          {original?.content ? <InlineRenderer content={original.content} /> : <span className="text-xs text-muted-foreground italic">(missing)</span>}
        </div>
        {/* Divider */}
        <div className="w-px bg-border/50 shrink-0" />
        {/* Translation pane */}
        <div className={cn(
          'flex-1 px-4 py-2.5 font-serif leading-[1.7]',
          isHeading ? 'text-base font-semibold' : 'text-sm',
          isEmpty ? 'text-muted-foreground/40 italic' : 'text-foreground/90',
        )}>
          {isEmpty ? (
            '(not translated)'
          ) : translated?.content ? (
            <InlineRenderer content={translated.content} />
          ) : (
            transText
          )}
        </div>
      </div>
    </div>
  );
}

// ── Gutter ─────────────────────────────────────────────────────────────────

function Gutter({ index, label, badgeColor, hasWarning }: { index: number; label: string; badgeColor: string; hasWarning?: boolean }) {
  return (
    <div className="w-9 shrink-0 flex flex-col items-center pt-2.5 gap-1 border-r border-border/30">
      <span className="font-mono text-[9px] text-border-hover font-medium">{index}</span>
      <span className={cn('text-[7px] px-1 py-px rounded font-semibold uppercase tracking-wide', badgeColor)}>
        {label}
      </span>
      {hasWarning && (
        <span className="h-1.5 w-1.5 rounded-full bg-[#e8a832]" title="Not translated" />
      )}
    </div>
  );
}

// ── Stats helper ───────────────────────────────────────────────────────────

export function computeReviewStats(originalBlocks: JSONContent[], translatedBlocks: JSONContent[]) {
  let translate = 0, passthrough = 0, caption = 0, translated = 0, empty = 0;
  const maxLen = Math.max(originalBlocks.length, translatedBlocks.length);
  for (let i = 0; i < maxLen; i++) {
    const block = originalBlocks[i] ?? translatedBlocks[i];
    if (!block) continue;
    const action = classifyBlock(block);
    if (action === 'passthrough') { passthrough++; continue; }
    if (action === 'caption') { caption++; }
    else { translate++; }
    const trans = translatedBlocks[i];
    const text = extractText(trans?.content) || trans?.attrs?.caption;
    if (text) translated++;
    else empty++;
  }
  return { total: maxLen, translate, passthrough, caption, translated, empty };
}
