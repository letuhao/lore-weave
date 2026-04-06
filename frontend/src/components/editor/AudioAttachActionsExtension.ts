import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import type { EditorView } from '@tiptap/pm/view';
import { getUploadContext } from './ImageBlockNode';
import { booksApi } from '@/features/books/api';

const AUDIO_NODE_TYPES = new Set(['paragraph', 'heading', 'blockquote', 'callout']);
const ALLOWED_AUDIO_TYPES = new Set(['audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/webm', 'audio/mp4']);
const MAX_AUDIO_SIZE = 20 * 1024 * 1024;

const pluginKey = new PluginKey('audioAttachActions');

/** Get audio duration from a File or Blob client-side */
function getAudioDuration(blob: Blob): Promise<number | null> {
  return new Promise((resolve) => {
    const audio = document.createElement('audio');
    audio.preload = 'metadata';
    audio.onloadedmetadata = () => {
      const dur = isFinite(audio.duration) ? Math.round(audio.duration * 1000) : null;
      resolve(dur);
      URL.revokeObjectURL(audio.src);
    };
    audio.onerror = () => resolve(null);
    audio.src = URL.createObjectURL(blob);
  });
}

function setAudioAttrs(
  view: EditorView,
  pos: number,
  attrs: Record<string, unknown>,
) {
  const node = view.state.doc.nodeAt(pos);
  if (!node) return;
  const tr = view.state.tr.setNodeMarkup(pos, undefined, {
    ...node.attrs,
    ...attrs,
  });
  view.dispatch(tr);
}

/**
 * Creates the floating action bar element. One instance shared across all blocks.
 */
function createActionBar(view: EditorView): HTMLElement {
  let currentPos = -1;
  let recording = false;
  let mediaRecorder: MediaRecorder | null = null;
  let recordedChunks: Blob[] = [];

  const bar = document.createElement('div');
  bar.className = 'audio-attach-actions-bar';
  bar.contentEditable = 'false';
  bar.style.cssText = `
    position: absolute; display: none; z-index: 5;
    right: -4px; top: 2px;
    padding: 2px; border-radius: 6px;
    background: var(--card, #1e1a17); border: 1px solid var(--border, #332d28);
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    display: none; gap: 2px; align-items: center;
  `;

  function makeBtn(label: string, title: string, onClick: () => void): HTMLElement {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = label;
    btn.title = title;
    btn.style.cssText = `
      width: 26px; height: 26px; border-radius: 4px; border: none; cursor: pointer;
      background: transparent; color: var(--muted-foreground, #9e9488); font-size: 12px;
      display: flex; align-items: center; justify-content: center;
    `;
    btn.addEventListener('mouseenter', () => {
      btn.style.background = 'var(--secondary, #282320)';
      btn.style.color = 'var(--foreground, #f5efe8)';
    });
    btn.addEventListener('mouseleave', () => {
      if (!(recording && btn === recordBtn)) {
        btn.style.background = 'transparent';
        btn.style.color = 'var(--muted-foreground, #9e9488)';
      }
    });
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      onClick();
    });
    return btn;
  }

  // Hidden file input
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = 'audio/mpeg,audio/wav,audio/ogg,audio/webm,audio/mp4';
  fileInput.style.display = 'none';
  fileInput.addEventListener('change', async () => {
    const file = fileInput.files?.[0];
    fileInput.value = '';
    if (!file || currentPos < 0) return;
    if (!ALLOWED_AUDIO_TYPES.has(file.type)) return;
    if (file.size > MAX_AUDIO_SIZE) return;

    const ctx = getUploadContext();
    if (!ctx) return;

    // Find block index
    let blockIndex = 0;
    view.state.doc.forEach((_child, _offset, index) => {
      if (_offset <= currentPos && currentPos < _offset + _child.nodeSize) {
        blockIndex = index;
      }
    });

    const duration = await getAudioDuration(file);

    try {
      const result = await booksApi.uploadBlockAudio(
        ctx.token, ctx.bookId, ctx.chapterId,
        file, blockIndex, undefined,
      );
      setAudioAttrs(view, currentPos, {
        audio_url: result.audio_url,
        audio_key: result.media_key,
        audio_duration_ms: duration || result.duration_ms,
        audio_source: 'uploaded',
        audio_subtitle: null,
      });
    } catch (err) {
      console.error('Audio upload failed:', err);
    }
    hide();
  });
  bar.appendChild(fileInput);

  // Upload button
  const uploadBtn = makeBtn('\uD83D\uDCC1', 'Upload audio', () => {
    fileInput.click();
  });
  bar.appendChild(uploadBtn);

  // Record button
  const recordBtn = makeBtn('\uD83C\uDFA4', 'Record audio', async () => {
    if (recording && mediaRecorder) {
      // Stop recording
      mediaRecorder.stop();
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordedChunks = [];
      mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) recordedChunks.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        recording = false;
        recordBtn.textContent = '\uD83C\uDFA4';
        recordBtn.style.background = 'transparent';
        recordBtn.style.color = 'var(--muted-foreground, #9e9488)';
        stream.getTracks().forEach((t) => t.stop());

        if (recordedChunks.length === 0 || currentPos < 0) return;

        const blob = new Blob(recordedChunks, { type: 'audio/webm' });
        const file = new File([blob], `recording-${Date.now()}.webm`, { type: 'audio/webm' });
        const ctx = getUploadContext();
        if (!ctx) return;

        let blockIndex = 0;
        view.state.doc.forEach((_child, _offset, index) => {
          if (_offset <= currentPos && currentPos < _offset + _child.nodeSize) {
            blockIndex = index;
          }
        });

        const duration = await getAudioDuration(file);

        try {
          const result = await booksApi.uploadBlockAudio(
            ctx.token, ctx.bookId, ctx.chapterId,
            file, blockIndex, undefined,
          );
          setAudioAttrs(view, currentPos, {
            audio_url: result.audio_url,
            audio_key: result.media_key,
            audio_duration_ms: duration || result.duration_ms,
            audio_source: 'recorded',
            audio_subtitle: null,
          });
        } catch (err) {
          console.error('Audio record upload failed:', err);
        }
        hide();
      };

      mediaRecorder.start();
      recording = true;
      recordBtn.textContent = '\u23F9';
      recordBtn.style.background = 'rgba(220,78,78,0.2)';
      recordBtn.style.color = '#dc4e4e';
    } catch (err) {
      console.error('Microphone access denied:', err);
    }
  });
  bar.appendChild(recordBtn);

  // AI Generate button — uses TTS model from localStorage prefs
  const aiBtn = makeBtn('\u2728', 'Generate AI audio (TTS)', async () => {
    if (currentPos < 0) return;
    const ctx = getUploadContext();
    if (!ctx) return;

    // Read TTS prefs from localStorage
    let ttsModelId: string | null = null;
    let ttsVoice = 'alloy';
    try {
      const raw = localStorage.getItem('lw_tts_prefs');
      if (raw) {
        const p = JSON.parse(raw);
        ttsModelId = p.ttsModelId || null;
        ttsVoice = p.ttsVoice || 'alloy';
      }
    } catch { /* ignore */ }

    if (!ttsModelId) {
      alert('Select a TTS model in Reader > TTS Settings first.');
      return;
    }

    const node = view.state.doc.nodeAt(currentPos);
    if (!node) return;
    const text = node.textContent.trim();
    if (!text) return;

    let blockIndex = 0;
    view.state.doc.forEach((_child, _offset, index) => {
      if (_offset <= currentPos && currentPos < _offset + _child.nodeSize) blockIndex = index;
    });

    try {
      const result = await booksApi.generateAudio(ctx.token, ctx.bookId, ctx.chapterId, {
        language: 'en',
        voice: ttsVoice,
        model_ref: ttsModelId,
        blocks: [{ index: blockIndex, text }],
      });
      if (result.segments.length > 0) {
        const seg = result.segments[0];
        setAudioAttrs(view, currentPos, {
          audio_url: seg.media_url,
          audio_key: seg.media_key,
          audio_duration_ms: seg.duration_ms,
          audio_source: 'ai',
          audio_subtitle: text,
        });
      } else if (result.errors.length > 0) {
        console.error('TTS generation error:', result.errors[0].error);
      }
    } catch (err) {
      console.error('TTS generation failed:', err);
    }
    hide();
  });
  bar.appendChild(aiBtn);

  function show(pos: number, blockDom: HTMLElement) {
    currentPos = pos;
    const wrapper = view.dom.closest('.tiptap-editor-wrapper');
    if (!wrapper) return;

    // Position relative to the block element
    const blockRect = blockDom.getBoundingClientRect();
    const wrapperRect = wrapper.getBoundingClientRect();
    const scrollTop = wrapper.scrollTop;

    bar.style.display = 'flex';
    bar.style.top = `${blockRect.top - wrapperRect.top + scrollTop + 2}px`;
    bar.style.right = '4px';
  }

  function hide() {
    if (recording) return; // don't hide while recording
    bar.style.display = 'none';
    currentPos = -1;
  }

  // Attach to bar for external access
  (bar as any)._show = show;
  (bar as any)._hide = hide;
  (bar as any)._isRecording = () => recording;

  return bar;
}

/**
 * Shows upload/record/generate action buttons on hover over text blocks
 * that don't already have audio_url attached.
 */
export const AudioAttachActionsExtension = Extension.create({
  name: 'audioAttachActions',

  addProseMirrorPlugins() {
    let actionBar: HTMLElement | null = null;
    let hideTimeout: ReturnType<typeof setTimeout> | null = null;

    return [
      new Plugin({
        key: pluginKey,
        view(editorView) {
          actionBar = createActionBar(editorView);
          // Append to the editor wrapper (position: relative parent)
          const wrapper = editorView.dom.closest('.tiptap-editor-wrapper');
          if (wrapper) {
            wrapper.appendChild(actionBar);
          }

          // Keep bar visible when hovering over the bar itself
          actionBar.addEventListener('mouseenter', () => {
            if (hideTimeout) {
              clearTimeout(hideTimeout);
              hideTimeout = null;
            }
          });
          actionBar.addEventListener('mouseleave', () => {
            if (!(actionBar as any)?._isRecording()) {
              hideTimeout = setTimeout(() => (actionBar as any)?._hide(), 200);
            }
          });

          return {
            destroy() {
              actionBar?.remove();
              actionBar = null;
            },
          };
        },
        props: {
          handleDOMEvents: {
            mouseover(view, event) {
              if (!actionBar) return false;

              const target = event.target as HTMLElement;

              // Don't activate when hovering over the action bar itself
              if (actionBar.contains(target)) return false;

              // Find the ProseMirror node at this DOM position
              const pos = view.posAtDOM(target, 0);
              if (pos == null) return false;

              const $pos = view.state.doc.resolve(pos);
              // Walk up to find the top-level block node
              const depth = $pos.depth;
              let blockPos = -1;
              let blockNode = null;
              for (let d = depth; d >= 1; d--) {
                const node = $pos.node(d);
                if (AUDIO_NODE_TYPES.has(node.type.name)) {
                  blockPos = $pos.before(d);
                  blockNode = node;
                  break;
                }
              }

              if (!blockNode || blockPos < 0) {
                // Not over an audio-eligible block — schedule hide
                if (hideTimeout) clearTimeout(hideTimeout);
                hideTimeout = setTimeout(() => (actionBar as any)?._hide(), 200);
                return false;
              }

              // Skip blocks that already have audio (AU-08 bar handles those)
              if (blockNode.attrs.audio_url) {
                if (hideTimeout) clearTimeout(hideTimeout);
                hideTimeout = setTimeout(() => (actionBar as any)?._hide(), 200);
                return false;
              }

              // Check editor mode — only show in AI mode
              const editorMode = ((view as any).editor?.storage as any)?.mediaGuard?.editorMode;
              if (editorMode === 'classic') return false;

              // Find the DOM element for this block
              const blockDom = view.nodeDOM(blockPos) as HTMLElement | null;
              if (!blockDom) return false;

              // Show the action bar
              if (hideTimeout) {
                clearTimeout(hideTimeout);
                hideTimeout = null;
              }
              (actionBar as any)._show(blockPos, blockDom);

              return false;
            },
          },
        },
      }),
    ];
  },
});
