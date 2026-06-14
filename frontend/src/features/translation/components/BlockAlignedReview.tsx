import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { JSONContent } from '@tiptap/react';
import { cn } from '@/lib/utils';
import { InlineRenderer } from '@/components/reader/InlineRenderer';
import { ContentRenderer } from '@/components/reader/ContentRenderer';

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
  /** T1: when true, translatable blocks render an editable translation pane. */
  editable?: boolean;
  /** Commit a per-block correction: the new plain text + the block to rebuild from. */
  onBlockEdit?: (index: number, newText: string, template: JSONContent) => void;
  /** The block index currently being saved (shows a spinner). */
  savingIndex?: number | null;
  /** Block indices already corrected this session (dirty dot). */
  dirtyIndices?: Set<number>;
}

export function BlockAlignedReview({
  originalBlocks,
  translatedBlocks,
  showPassthrough = true,
  activeIndex = null,
  onBlockClick,
  editable = false,
  onBlockEdit,
  savingIndex = null,
  dirtyIndices,
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
            editable={editable}
            onBlockEdit={onBlockEdit}
            saving={savingIndex === i}
            isDirty={!!dirtyIndices?.has(i)}
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
  editable?: boolean;
  onBlockEdit?: (index: number, newText: string, template: JSONContent) => void;
  saving?: boolean;
  isDirty?: boolean;
}

function BlockRow({ index, original, translated, action, isActive, onClick, editable, onBlockEdit, saving, isDirty }: BlockRowProps) {
  const { t } = useTranslation('translation');
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
            <span className="text-xs italic">{t('block_review.unchanged')}</span>
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
            <span className="text-xs text-muted-foreground">{origCaption || t('block_review.no_caption')}</span>
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
              {transCaption || t('block_review.no_caption')}
            </span>
          </div>
        </div>
      </div>
    );
  }

  // Translatable block: source | translation side by side
  const transText = extractText(translated?.content);
  const isEmpty = !transText;
  const isHeading = block.type === 'heading';
  // Per-block editing supports simple inline blocks; compound blocks (lists/quotes)
  // would lose structure if flattened to text → stay read-only even in edit mode.
  const isCompound = COMPOUND_TYPES.has(block.type ?? '');
  const canEdit = !!editable && !isCompound && !!onBlockEdit;

  return (
    <div
      className={cn(
        'flex min-h-[48px] transition-colors',
        editable ? '' : 'cursor-pointer',
        isActive ? 'bg-primary/5' : editable ? '' : 'hover:bg-secondary/30',
      )}
      onClick={editable ? undefined : onClick}
    >
      <Gutter index={index} label={label} badgeColor={badgeColor} hasWarning={isEmpty} isDirty={isDirty} saving={saving} />
      <div className="flex flex-1">
        {/* Source pane */}
        <div className={cn(
          'flex-1 px-4 py-2.5 font-serif leading-[1.7] text-foreground/80',
          isHeading ? 'text-base font-semibold' : 'text-sm',
        )}>
          {original ? <BlockContent block={original} /> : <span className="text-xs text-muted-foreground italic">{t('block_review.missing')}</span>}
        </div>
        {/* Divider */}
        <div className="w-px bg-border/50 shrink-0" />
        {/* Translation pane */}
        <div className={cn(
          'flex-1 px-4 py-2.5 font-serif leading-[1.7]',
          isHeading ? 'text-base font-semibold' : 'text-sm',
          isEmpty && !canEdit ? 'text-muted-foreground/40 italic' : 'text-foreground/90',
        )}>
          {canEdit ? (
            <EditableCell
              key={transText}
              index={index}
              initialText={transText}
              template={translated ?? { type: block.type, attrs: block.attrs }}
              isHeading={isHeading}
              onCommit={onBlockEdit!}
            />
          ) : isEmpty ? (
            t('block_review.not_translated')
          ) : translated ? (
            <BlockContent block={translated} />
          ) : (
            transText
          )}
        </div>
      </div>
    </div>
  );
}

// ── Editable translation cell (T1 per-block correction) ─────────────────────

function EditableCell({
  index, initialText, template, isHeading, onCommit,
}: {
  index: number;
  initialText: string;
  template: JSONContent;
  isHeading: boolean;
  onCommit: (index: number, newText: string, template: JSONContent) => void;
}) {
  const { t } = useTranslation('translation');
  const [val, setVal] = useState(initialText);
  return (
    <textarea
      data-testid={`correction-cell-${index}`}
      value={val}
      placeholder={t('block_review.not_translated')}
      onChange={(e) => setVal(e.target.value)}
      onBlur={() => { if (val !== initialText) onCommit(index, val, template); }}
      rows={Math.max(1, Math.ceil(val.length / 60))}
      className={cn(
        'w-full resize-none bg-transparent outline-none rounded px-1 -mx-1',
        'focus:bg-secondary/40 focus:ring-1 focus:ring-ring/30',
        isHeading ? 'text-base font-semibold' : 'text-sm',
      )}
    />
  );
}

// ── Block content renderer (picks inline vs full based on type) ────────────

const COMPOUND_TYPES = new Set(['bulletList', 'orderedList', 'blockquote', 'callout']);

function BlockContent({ block }: { block: JSONContent }) {
  if (COMPOUND_TYPES.has(block.type ?? '')) {
    return <ContentRenderer blocks={[block]} mode="compact" />;
  }
  return block.content ? <InlineRenderer content={block.content} /> : null;
}

// ── Gutter ─────────────────────────────────────────────────────────────────

function Gutter({ index, label, badgeColor, hasWarning, isDirty, saving }: { index: number; label: string; badgeColor: string; hasWarning?: boolean; isDirty?: boolean; saving?: boolean }) {
  const { t } = useTranslation('translation');
  return (
    <div className="w-9 shrink-0 flex flex-col items-center pt-2.5 gap-1 border-r border-border/30">
      <span className="font-mono text-[9px] text-border-hover font-medium">{index}</span>
      <span className={cn('text-[7px] px-1 py-px rounded font-semibold uppercase tracking-wide', badgeColor)}>
        {label}
      </span>
      {saving ? (
        <span className="h-2 w-2 rounded-full border border-primary border-t-transparent animate-spin" title={t('review.block_saving')} />
      ) : isDirty ? (
        <span className="h-1.5 w-1.5 rounded-full bg-[#3da692]" title={t('review.block_dirty')} />
      ) : hasWarning ? (
        <span className="h-1.5 w-1.5 rounded-full bg-[#e8a832]" title={t('block_review.not_translated_title')} />
      ) : null}
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
