import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import type { Node as PmNode } from '@tiptap/pm/model';
import type { EditorView } from '@tiptap/pm/view';

const AUDIO_NODE_TYPES = new Set(['paragraph', 'heading', 'blockquote', 'callout']);

const pluginKey = new PluginKey('audioAttachBar');

// Shared audio element for playback across all bars
let sharedAudio: HTMLAudioElement | null = null;
let activePlayBtn: HTMLElement | null = null;

function getSharedAudio(): HTMLAudioElement {
  if (!sharedAudio) {
    sharedAudio = document.createElement('audio');
    sharedAudio.preload = 'metadata';
    sharedAudio.addEventListener('ended', () => {
      if (activePlayBtn) {
        activePlayBtn.textContent = '\u25B6';
        activePlayBtn = null;
      }
    });
  }
  return sharedAudio;
}

function formatDuration(ms: number): string {
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function normalize(s: string): string {
  return s.replace(/\s+/g, ' ').trim().toLowerCase();
}

function createBar(
  node: PmNode,
  pos: number,
  getView: () => EditorView | null,
): HTMLElement {
  const audioUrl = node.attrs.audio_url as string;
  const audioSource = (node.attrs.audio_source as string) || 'uploaded';
  const durationMs = node.attrs.audio_duration_ms as number | null;
  const subtitle = node.attrs.audio_subtitle as string | null;

  const blockText = node.textContent.trim();
  const hasMismatch = subtitle != null && subtitle.trim() !== '' && blockText !== '' &&
    normalize(blockText) !== normalize(subtitle);

  const bar = document.createElement('div');
  bar.className = 'audio-attach-bar';
  bar.contentEditable = 'false';
  bar.style.cssText = `
    margin: 4px 0 2px; padding: 6px 10px; background: var(--secondary, #282320);
    border-radius: 6px; border: 1px solid var(--border, #332d28);
    display: flex; align-items: center; gap: 8px; font-size: 11px;
    user-select: none;
  `;

  // Play button
  const playBtn = document.createElement('button');
  playBtn.type = 'button';
  playBtn.textContent = '\u25B6';
  playBtn.title = 'Play/Pause';
  playBtn.style.cssText = `
    width: 26px; height: 26px; border-radius: 50%; border: none; cursor: pointer;
    background: #8b5cf6; color: white; font-size: 10px;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  `;
  playBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    const audio = getSharedAudio();
    if (audio.src === audioUrl && !audio.paused) {
      audio.pause();
      playBtn.textContent = '\u25B6';
      activePlayBtn = null;
    } else {
      if (activePlayBtn && activePlayBtn !== playBtn) {
        activePlayBtn.textContent = '\u25B6';
      }
      audio.src = audioUrl;
      audio.play();
      playBtn.textContent = '\u23F8';
      activePlayBtn = playBtn;
    }
  });
  bar.appendChild(playBtn);

  // Waveform placeholder
  const waveform = document.createElement('div');
  waveform.style.cssText = 'flex: 1; display: flex; align-items: center; gap: 1px; height: 20px;';
  for (let i = 0; i < 30; i++) {
    const line = document.createElement('span');
    const h = 3 + Math.sin(i * 0.8) * 6 + Math.random() * 4;
    line.style.cssText = `width: 2px; height: ${h}px; background: #8b5cf6; opacity: 0.35; border-radius: 1px;`;
    waveform.appendChild(line);
  }
  bar.appendChild(waveform);

  // Source badge
  const badge = document.createElement('span');
  const badgeColors: Record<string, string> = {
    uploaded: 'rgba(139,92,246,0.15)',
    recorded: 'rgba(139,92,246,0.15)',
    ai: 'rgba(84,150,232,0.15)',
  };
  const badgeTextColors: Record<string, string> = {
    uploaded: '#8b5cf6',
    recorded: '#8b5cf6',
    ai: '#5496e8',
  };
  badge.textContent = audioSource;
  badge.style.cssText = `
    font-size: 9px; font-weight: 500; padding: 1px 6px; border-radius: 99px;
    background: ${badgeColors[audioSource] || badgeColors.uploaded};
    color: ${badgeTextColors[audioSource] || badgeTextColors.uploaded};
  `;
  bar.appendChild(badge);

  // Duration
  if (durationMs) {
    const dur = document.createElement('span');
    dur.textContent = formatDuration(durationMs);
    dur.style.cssText = 'font-size: 9px; color: var(--muted-foreground, #9e9488);';
    bar.appendChild(dur);
  }

  // Mismatch indicator
  if (hasMismatch) {
    const warn = document.createElement('span');
    warn.textContent = '\u26A0 mismatch';
    warn.title = 'Audio subtitle differs from block text';
    warn.style.cssText = 'font-size: 9px; color: #e8a832; cursor: help;';
    bar.appendChild(warn);
  }

  // Remove button
  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.textContent = '\u2715';
  removeBtn.title = 'Remove audio';
  removeBtn.style.cssText = `
    width: 20px; height: 20px; border-radius: 4px; border: none; cursor: pointer;
    background: transparent; color: var(--muted-foreground, #9e9488); font-size: 10px;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  `;
  removeBtn.addEventListener('mouseenter', () => {
    removeBtn.style.background = 'rgba(220,78,78,0.1)';
    removeBtn.style.color = '#dc4e4e';
  });
  removeBtn.addEventListener('mouseleave', () => {
    removeBtn.style.background = 'transparent';
    removeBtn.style.color = 'var(--muted-foreground, #9e9488)';
  });
  removeBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    const audio = getSharedAudio();
    if (audio.src === audioUrl) {
      audio.pause();
      audio.src = '';
      if (activePlayBtn) {
        activePlayBtn.textContent = '\u25B6';
        activePlayBtn = null;
      }
    }
    const view = getView();
    if (!view) return;
    const tr = view.state.tr.setNodeMarkup(pos, undefined, {
      ...node.attrs,
      audio_url: null,
      audio_key: null,
      audio_subtitle: null,
      audio_duration_ms: null,
      audio_source: null,
    });
    view.dispatch(tr);
  });
  bar.appendChild(removeBtn);

  return bar;
}

function buildDecorations(doc: PmNode, getView: () => EditorView | null): DecorationSet {
  const decorations: Decoration[] = [];

  doc.descendants((node, pos) => {
    if (!AUDIO_NODE_TYPES.has(node.type.name)) return;
    if (!node.attrs.audio_url) return;

    const widgetPos = pos + node.nodeSize;
    decorations.push(
      Decoration.widget(widgetPos, () => createBar(node, pos, getView), {
        side: -1,
        key: `audio-bar-${pos}`,
      }),
    );
  });

  return DecorationSet.create(doc, decorations);
}

/**
 * Renders AudioAttachBar widgets below text blocks that have audio_url.
 * Uses ProseMirror widget decorations — no NodeView replacement needed.
 */
export const AudioAttachBarExtension = Extension.create({
  name: 'audioAttachBar',

  addProseMirrorPlugins() {
    let editorView: EditorView | null = null;
    const getView = () => editorView;

    return [
      new Plugin({
        key: pluginKey,
        view(view) {
          editorView = view;
          return {
            update(v) { editorView = v; },
            destroy() { editorView = null; },
          };
        },
        state: {
          init(_, { doc }) {
            return buildDecorations(doc, getView);
          },
          apply(tr, old) {
            if (!tr.docChanged) return old;
            return buildDecorations(tr.doc, getView);
          },
        },
        props: {
          decorations(state) {
            return pluginKey.getState(state);
          },
        },
      }),
    ];
  },
});
