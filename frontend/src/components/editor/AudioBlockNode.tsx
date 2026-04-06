import { Node, mergeAttributes } from '@tiptap/core';
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  type NodeViewProps,
} from '@tiptap/react';
import { Music, Upload, Loader2, Lock, Trash2, Replace, Play, Pause } from 'lucide-react';
import { useState, useCallback, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { booksApi } from '@/features/books/api';
import { getUploadContext } from './ImageBlockNode';

const MAX_AUDIO_SIZE = 20 * 1024 * 1024; // 20 MB
const ALLOWED_AUDIO_TYPES = new Set([
  'audio/mpeg',
  'audio/wav',
  'audio/ogg',
  'audio/webm',
  'audio/mp4',
]);

/** Extract audio duration client-side using HTMLAudioElement metadata */
function getAudioDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const audio = document.createElement('audio');
    audio.preload = 'metadata';
    audio.onloadedmetadata = () => {
      const dur = isFinite(audio.duration) ? Math.round(audio.duration * 1000) : null;
      resolve(dur);
      URL.revokeObjectURL(audio.src);
    };
    audio.onerror = () => resolve(null);
    audio.src = URL.createObjectURL(file);
  });
}

// --- Tiptap node extension ---
export const AudioBlockExtension = Node.create({
  name: 'audioBlock',
  group: 'block',
  atom: true,
  draggable: true,
  selectable: true,

  addAttributes() {
    return {
      blockId: {
        default: null,
        parseHTML: (el) => el.getAttribute('data-block-id'),
        renderHTML: (attrs) => ({ 'data-block-id': attrs.blockId }),
      },
      src: { default: null },
      media_key: { default: null },
      subtitle: { default: '' },
      title: { default: '' },
      duration_ms: { default: null },
      size_bytes: { default: null },
      _mode: { default: 'ai', rendered: false },
    };
  },

  parseHTML() {
    return [{ tag: 'figure[data-audio-block]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ['figure', mergeAttributes(HTMLAttributes, { 'data-audio-block': '' })];
  },

  addNodeView() {
    return ReactNodeViewRenderer(AudioBlockNodeView);
  },

  onCreate() {
    const { editor } = this;
    const { doc, tr } = editor.state;
    let modified = false;
    doc.descendants((node, pos) => {
      if (node.type.name === 'audioBlock' && !node.attrs.blockId) {
        tr.setNodeMarkup(pos, undefined, {
          ...node.attrs,
          blockId: crypto.randomUUID().slice(0, 8),
        });
        modified = true;
      }
    });
    if (modified) editor.view.dispatch(tr);
  },
});

// --- Validation ---
function validateAudioFile(file: File): string | null {
  if (!ALLOWED_AUDIO_TYPES.has(file.type)) {
    return `Unsupported type: ${file.type}. Use MP3, WAV, OGG, WebM, or M4A.`;
  }
  if (file.size > MAX_AUDIO_SIZE) {
    return `File too large: ${(file.size / 1024 / 1024).toFixed(1)} MB. Max 20 MB.`;
  }
  return null;
}

// --- Format helpers ---
function formatDuration(ms: number | null): string {
  if (!ms) return '';
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatSize(bytes: number | null): string {
  if (!bytes) return '';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// --- NodeView component ---
function AudioBlockNodeView({ node, updateAttributes, selected, editor, deleteNode }: NodeViewProps) {
  const editorMode = ((editor.storage as any).mediaGuard?.editorMode as string) || 'ai';
  const isClassic = editorMode === 'classic';
  const src = node.attrs.src as string | null;
  const subtitle = (node.attrs.subtitle as string) || '';
  const title = (node.attrs.title as string) || 'Audio';
  const durationMs = node.attrs.duration_ms as number | null;
  const sizeBytes = node.attrs.size_bytes as number | null;
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [playing, setPlaying] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Sync play state when audio ends
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onEnd = () => setPlaying(false);
    audio.addEventListener('ended', onEnd);
    return () => audio.removeEventListener('ended', onEnd);
  }, [src]);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
      setPlaying(false);
    } else {
      audio.play();
      setPlaying(true);
    }
  }, [playing]);

  // --- Upload logic ---
  const doUpload = useCallback(
    async (file: File) => {
      const err = validateAudioFile(file);
      if (err) {
        setUploadError(err);
        return;
      }
      const ctx = getUploadContext();
      if (!ctx) {
        setUploadError('Upload not available — save the chapter first.');
        return;
      }
      setUploading(true);
      setUploadPct(0);
      setUploadError(null);
      try {
        const clientDuration = await getAudioDuration(file);

        let blockId = node.attrs.blockId as string;
        if (!blockId) {
          blockId = crypto.randomUUID().slice(0, 8);
          updateAttributes({ blockId });
        }

        // Find this node's top-level block index
        let blockIndex = 0;
        editor.state.doc.forEach((child, _offset, index) => {
          if (child === node) blockIndex = index;
        });

        const result = await booksApi.uploadBlockAudio(
          ctx.token,
          ctx.bookId,
          ctx.chapterId,
          file,
          blockIndex,
          subtitle || undefined,
          (pct) => setUploadPct(pct),
        );
        updateAttributes({
          src: result.audio_url,
          media_key: result.media_key,
          title: file.name,
          size_bytes: result.size_bytes,
          duration_ms: clientDuration || result.duration_ms,
        });
      } catch (e: any) {
        setUploadError(e.message || 'Upload failed');
      } finally {
        setUploading(false);
      }
    },
    [updateAttributes, node, editor, subtitle],
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
      e.target.value = '';
    },
    [doUpload],
  );

  // --- Classic mode: compact locked placeholder ---
  if (isClassic) {
    return (
      <NodeViewWrapper className="group my-2">
        <div className="flex items-center gap-2 rounded-lg border bg-secondary px-3 py-2 text-muted-foreground">
          <Music className="h-4 w-4 flex-shrink-0 opacity-40" />
          <span className="flex-1 truncate text-xs">{title}</span>
          {sizeBytes && <span className="text-[9px] opacity-50">{formatSize(sizeBytes)}</span>}
          {durationMs && <span className="text-[9px] opacity-50">{formatDuration(durationMs)}</span>}
          {subtitle && (
            <span className="hidden text-[9px] opacity-50 group-hover:inline">{subtitle}</span>
          )}
          <span className="flex items-center gap-1 rounded bg-card px-1.5 py-0.5 text-[9px]">
            <Lock className="h-2.5 w-2.5" /> AI mode
          </span>
        </div>
      </NodeViewWrapper>
    );
  }

  return (
    <NodeViewWrapper
      className={cn(
        'my-2 overflow-hidden rounded-lg border transition-shadow',
        selected ? 'ring-2 ring-primary/40' : 'hover:border-border-hover',
      )}
    >
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="audio/mpeg,audio/wav,audio/ogg,audio/webm,audio/mp4"
        className="hidden"
        onChange={handleFileSelect}
      />

      {src ? (
        /* Audio player */
        <div className="flex items-center gap-3 px-4 py-3" contentEditable={false}>
          {/* Hidden audio element for custom controls */}
          <audio ref={audioRef} src={src} preload="metadata" />

          {/* Play/Pause button */}
          <button
            type="button"
            onClick={togglePlay}
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-purple-600 text-white transition hover:bg-purple-500"
            title={playing ? 'Pause' : 'Play'}
          >
            {playing ? <Pause className="h-4 w-4" /> : <Play className="ml-0.5 h-4 w-4" />}
          </button>

          {/* Waveform placeholder + info */}
          <div className="min-w-0 flex-1">
            <div className="flex h-6 items-center gap-[2px]">
              {Array.from({ length: 40 }).map((_, i) => (
                <span
                  key={i}
                  className="w-[2px] rounded-full bg-purple-500/40"
                  style={{ height: `${4 + Math.sin(i * 0.7) * 8 + Math.random() * 6}px` }}
                />
              ))}
            </div>
            <div className="mt-0.5 flex gap-3 text-[9px] text-muted-foreground">
              {durationMs != null && <span>{formatDuration(durationMs)}</span>}
              {sizeBytes != null && <span>{formatSize(sizeBytes)}</span>}
              {title && title !== 'Audio' && <span className="truncate">{title}</span>}
            </div>
          </div>

          {/* Quick actions */}
          <div className="flex gap-1" contentEditable={false}>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="rounded px-1.5 py-0.5 text-[9px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              title="Replace audio"
            >
              <Replace className="h-3 w-3" />
            </button>
            <button
              type="button"
              onClick={() => deleteNode()}
              className="rounded px-1.5 py-0.5 text-[9px] text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
              title="Delete audio block"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        </div>
      ) : (
        /* Upload zone */
        <div
          className={cn(
            'flex flex-col items-center justify-center gap-2 border-2 border-dashed py-8 transition-colors',
            uploading
              ? 'border-primary/40 bg-primary/5'
              : dragOver
                ? 'border-purple-500 bg-purple-500/10 text-purple-400'
                : 'border-border bg-secondary text-muted-foreground hover:border-purple-500/40 hover:text-foreground',
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
              <Loader2 className="h-6 w-6 animate-spin text-purple-500" />
              <span className="text-xs">Uploading... {uploadPct}%</span>
              <div className="mx-8 h-1.5 w-48 overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full rounded-full bg-purple-500 transition-all"
                  style={{ width: `${uploadPct}%` }}
                />
              </div>
            </>
          ) : (
            <>
              <Upload className="h-6 w-6 opacity-40" />
              <span className="text-xs font-medium">
                {dragOver ? 'Drop audio here' : 'Drop an audio file or click to browse'}
              </span>
              <span className="text-[9px] opacity-50">MP3, WAV, OGG, WebM, M4A — Max 20 MB</span>
            </>
          )}
          {uploadError && (
            <span className="mt-1 text-[10px] text-destructive">{uploadError}</span>
          )}
        </div>
      )}

      {/* Subtitle bar */}
      <div
        className="flex items-center gap-2 border-t bg-card px-3 py-1.5"
        contentEditable={false}
      >
        <Music className="h-3.5 w-3.5 flex-shrink-0 text-purple-500/60" />
        <input
          type="text"
          value={subtitle}
          onChange={(e) => updateAttributes({ subtitle: e.target.value })}
          placeholder="Add a subtitle..."
          className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground/40"
          aria-label="Audio subtitle"
        />
        {durationMs != null && (
          <span className="flex-shrink-0 text-[9px] text-muted-foreground">
            {formatDuration(durationMs)}
          </span>
        )}
      </div>
    </NodeViewWrapper>
  );
}
