import { Node, mergeAttributes } from '@tiptap/core';
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  type NodeViewProps,
} from '@tiptap/react';
import { ImageIcon, Accessibility, Upload, Loader2 } from 'lucide-react';
import { useState, useCallback, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { booksApi } from '@/features/books/api';

// --- Upload context (set by the editor page, read by NodeView) ---
export interface ImageUploadContext {
  token: string;
  bookId: string;
  chapterId: string;
}

let _uploadCtx: ImageUploadContext | null = null;
export function setImageUploadContext(ctx: ImageUploadContext | null) {
  _uploadCtx = ctx;
}

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
const ALLOWED_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp']);

// --- Tiptap node extension ---
export const ImageBlockExtension = Node.create({
  name: 'imageBlock',
  group: 'block',
  atom: true,
  draggable: true,
  selectable: true,

  addAttributes() {
    return {
      src: { default: null },
      alt: { default: '' },
      caption: { default: '' },
      width: { default: 100 },
      title: { default: '' },
    };
  },

  parseHTML() {
    return [{ tag: 'figure[data-image-block]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ['figure', mergeAttributes(HTMLAttributes, { 'data-image-block': '' })];
  },

  addNodeView() {
    return ReactNodeViewRenderer(ImageBlockNodeView);
  },
});

// --- Resize hook ---
function useResize(
  initialWidth: number,
  onResizeEnd: (width: number) => void,
  containerRef: React.RefObject<HTMLDivElement | null>,
) {
  const [currentWidth, setCurrentWidth] = useState(initialWidth);
  const isResizing = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      isResizing.current = true;
      startX.current = e.clientX;
      startWidth.current = currentWidth;

      const parentWidth = containerRef.current?.parentElement?.clientWidth ?? 1;

      const onMove = (ev: PointerEvent) => {
        if (!isResizing.current) return;
        const deltaX = ev.clientX - startX.current;
        const deltaPct = (deltaX / parentWidth) * 100;
        const newWidth = Math.round(Math.min(100, Math.max(10, startWidth.current + deltaPct)));
        setCurrentWidth(newWidth);
      };

      const onUp = () => {
        isResizing.current = false;
        document.removeEventListener('pointermove', onMove);
        document.removeEventListener('pointerup', onUp);
        setCurrentWidth((w) => {
          onResizeEnd(w);
          return w;
        });
      };

      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp);
    },
    [currentWidth, onResizeEnd, containerRef],
  );

  return { currentWidth, setCurrentWidth, handlePointerDown };
}

// --- Upload validation ---
function validateFile(file: File): string | null {
  if (!ALLOWED_TYPES.has(file.type)) {
    return `Unsupported type: ${file.type}. Use PNG, JPG, GIF, or WebP.`;
  }
  if (file.size > MAX_FILE_SIZE) {
    return `File too large: ${(file.size / 1024 / 1024).toFixed(1)} MB. Max 10 MB.`;
  }
  return null;
}

// --- NodeView component ---
function ImageBlockNodeView({ node, updateAttributes, selected }: NodeViewProps) {
  const src = node.attrs.src as string | null;
  const alt = (node.attrs.alt as string) || '';
  const caption = (node.attrs.caption as string) || '';
  const width = (node.attrs.width as number) || 100;
  const [showAlt, setShowAlt] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleResizeEnd = useCallback(
    (newWidth: number) => {
      updateAttributes({ width: newWidth });
    },
    [updateAttributes],
  );

  const { currentWidth, setCurrentWidth, handlePointerDown } = useResize(
    width,
    handleResizeEnd,
    containerRef,
  );

  // Sync width when attrs change externally (e.g. undo/redo)
  useEffect(() => {
    setCurrentWidth(width);
  }, [width, setCurrentWidth]);

  const handleCaptionChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      updateAttributes({ caption: e.target.value });
    },
    [updateAttributes],
  );

  const handleAltChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      updateAttributes({ alt: e.target.value });
    },
    [updateAttributes],
  );

  // --- Upload logic ---
  const doUpload = useCallback(
    async (file: File) => {
      const err = validateFile(file);
      if (err) {
        setUploadError(err);
        return;
      }
      if (!_uploadCtx) {
        setUploadError('Upload not available — save the chapter first.');
        return;
      }
      setUploading(true);
      setUploadPct(0);
      setUploadError(null);
      try {
        const result = await booksApi.uploadChapterMedia(
          _uploadCtx.token,
          _uploadCtx.bookId,
          _uploadCtx.chapterId,
          file,
          (pct) => setUploadPct(pct),
        );
        updateAttributes({
          src: result.url,
          title: result.filename,
        });
      } catch (e: any) {
        setUploadError(e.message || 'Upload failed');
      } finally {
        setUploading(false);
      }
    },
    [updateAttributes],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) doUpload(file);
    },
    [doUpload],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => setDragOver(false), []);

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) doUpload(file);
      // Reset input so the same file can be re-selected
      e.target.value = '';
    },
    [doUpload],
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      const items = e.clipboardData.items;
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.startsWith('image/')) {
          const file = items[i].getAsFile();
          if (file) {
            e.preventDefault();
            doUpload(file);
            return;
          }
        }
      }
    },
    [doUpload],
  );

  return (
    <NodeViewWrapper
      className={cn(
        'my-2 overflow-hidden rounded-lg border transition-shadow',
        selected ? 'ring-2 ring-primary/40' : 'hover:border-border-hover',
      )}
      onPaste={!src ? handlePaste : undefined}
    >
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp"
        className="hidden"
        onChange={handleFileSelect}
      />

      {/* Image container with percentage width */}
      <div
        ref={containerRef}
        className="group relative mx-auto"
        style={{ width: `${currentWidth}%` }}
      >
        {src ? (
          <img
            src={src}
            alt={alt}
            title={node.attrs.title as string}
            className="block w-full rounded-t-lg object-cover"
            draggable={false}
          />
        ) : (
          /* Upload zone */
          <div
            className={cn(
              'flex aspect-video flex-col items-center justify-center gap-2 rounded-t-lg border-2 border-dashed transition-colors',
              uploading
                ? 'border-primary/40 bg-primary/5'
                : dragOver
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border bg-secondary text-muted-foreground hover:border-primary/40 hover:text-foreground',
            )}
            contentEditable={false}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => !uploading && fileInputRef.current?.click()}
            style={{ cursor: uploading ? 'default' : 'pointer' }}
          >
            {uploading ? (
              <>
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
                <span className="text-xs">Uploading... {uploadPct}%</span>
                <div className="mx-8 h-1.5 w-48 overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${uploadPct}%` }}
                  />
                </div>
              </>
            ) : (
              <>
                <Upload className="h-6 w-6 opacity-40" />
                <span className="text-xs font-medium">
                  {dragOver ? 'Drop image here' : 'Drop an image, click to browse, or Ctrl+V'}
                </span>
                <span className="text-[9px] opacity-50">
                  PNG, JPG, GIF, WebP — Max 10 MB
                </span>
              </>
            )}
            {uploadError && (
              <span className="mt-1 text-[10px] text-destructive">{uploadError}</span>
            )}
          </div>
        )}

        {/* Resize handle — bottom-right corner (only when image loaded) */}
        {src && (
          <div
            className={cn(
              'absolute bottom-1 right-1 flex h-4 w-4 cursor-nwse-resize items-center justify-center rounded-sm bg-primary/70 transition-opacity',
              selected ? 'opacity-80' : 'opacity-0 group-hover:opacity-100',
            )}
            onPointerDown={handlePointerDown}
            contentEditable={false}
            title={`Width: ${currentWidth}%`}
          >
            <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor" className="text-primary-fg">
              <circle cx="6" cy="6" r="1" />
              <circle cx="6" cy="3" r="1" />
              <circle cx="3" cy="6" r="1" />
            </svg>
          </div>
        )}
      </div>

      {/* Caption + metadata bar */}
      <div
        className="flex items-center gap-2 border-t bg-card px-3 py-1.5"
        contentEditable={false}
      >
        <ImageIcon className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
        <input
          type="text"
          value={caption}
          onChange={handleCaptionChange}
          placeholder="Add a caption..."
          className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground/40"
          aria-label="Image caption"
        />
        {currentWidth < 100 && (
          <span className="flex-shrink-0 font-mono text-[9px] text-muted-foreground">
            {currentWidth}%
          </span>
        )}
      </div>

      {/* Alt text — collapsible */}
      <div className="border-t" contentEditable={false}>
        <button
          type="button"
          onClick={() => setShowAlt(!showAlt)}
          className="flex w-full items-center gap-1.5 px-3 py-1 text-[10px] text-muted-foreground transition-colors hover:text-foreground"
          aria-expanded={showAlt}
        >
          <Accessibility className="h-3 w-3" />
          <span>Alt text</span>
          {alt && <span className="rounded bg-success/10 px-1 text-[8px] text-success">set</span>}
          <span className="ml-auto text-[9px]">{showAlt ? '▾' : '▸'}</span>
        </button>
        {showAlt && (
          <div className="border-t px-3 py-1.5">
            <input
              type="text"
              value={alt}
              onChange={handleAltChange}
              placeholder="Describe this image for screen readers and EPUB export..."
              className="w-full bg-transparent text-[11px] text-foreground outline-none placeholder:text-muted-foreground/40"
              aria-label="Image alt text"
            />
            <p className="mt-1 text-[9px] text-muted-foreground/60">
              Used by screen readers, search, and EPUB export. Different from caption.
            </p>
          </div>
        )}
      </div>
    </NodeViewWrapper>
  );
}
