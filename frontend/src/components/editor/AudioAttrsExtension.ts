import { Extension } from '@tiptap/core';

/**
 * Adds audio attachment attributes to text block types (paragraph, heading,
 * blockquote, callout). All default to null — no visual change to existing
 * content. AU-08 (AudioAttachBar) will render a mini player when audio_url
 * is set.
 *
 * Attrs persist in Tiptap JSON and are saved via patchDraft automatically.
 */
export const AudioAttrsExtension = Extension.create({
  name: 'audioAttrs',

  addGlobalAttributes() {
    const audioAttrs = {
      audio_url: {
        default: null,
        parseHTML: (el: HTMLElement) => el.getAttribute('data-audio-url') || null,
        renderHTML: (attrs: Record<string, unknown>) =>
          attrs.audio_url ? { 'data-audio-url': attrs.audio_url } : {},
      },
      audio_key: {
        default: null,
        parseHTML: (el: HTMLElement) => el.getAttribute('data-audio-key') || null,
        renderHTML: (attrs: Record<string, unknown>) =>
          attrs.audio_key ? { 'data-audio-key': attrs.audio_key } : {},
      },
      audio_subtitle: {
        default: null,
        parseHTML: (el: HTMLElement) => el.getAttribute('data-audio-subtitle') || null,
        renderHTML: (attrs: Record<string, unknown>) =>
          attrs.audio_subtitle ? { 'data-audio-subtitle': attrs.audio_subtitle } : {},
      },
      audio_duration_ms: {
        default: null,
        parseHTML: (el: HTMLElement) => {
          const v = el.getAttribute('data-audio-duration-ms');
          return v ? Number(v) : null;
        },
        renderHTML: (attrs: Record<string, unknown>) =>
          attrs.audio_duration_ms != null
            ? { 'data-audio-duration-ms': String(attrs.audio_duration_ms) }
            : {},
      },
      audio_source: {
        default: null,
        parseHTML: (el: HTMLElement) => el.getAttribute('data-audio-source') || null,
        renderHTML: (attrs: Record<string, unknown>) =>
          attrs.audio_source ? { 'data-audio-source': attrs.audio_source } : {},
      },
    };

    return [
      {
        types: ['paragraph', 'heading', 'blockquote', 'callout'],
        attributes: audioAttrs,
      },
    ];
  },
});
