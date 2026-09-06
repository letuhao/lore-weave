import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// R7 — a chat model with too small a window cannot chat AT ALL, and nothing said so.
//
// 🔴 MEASURED LIVE 2026-09-04. Registered an 8,192-window model on a throwaway account and sent one
// message. It never reached the provider:
//
//     the assembled prompt overflows this model's context window:
//     input=9732 + safety=1228 = 10960 > context_length=8192
//
// **The advertised tool surface alone is ~9.7K tokens**, before a single word of the book. The Add
// Model form accepted 8192 without a murmur, and the author's only feedback was a message that
// vanished — which is R6, the worst possible place to learn this.
//
// ⚠️ ADVISORY, NOT A GATE, and that is a decision rather than laziness. The real floor RISES with
// how many tools a turn advertises, so promoting one measurement to a hard limit would let a
// harness constant decide a product rule. It warns; the user may still proceed.
//
// ⚠️ CHAT-CAPABLE ONLY. A reranker or embedding model legitimately has a small window —
// `bge-reranker-v2-m3` is registered on this very account at a fraction of it — and warning there
// would be noise that teaches people to ignore the banner.
//
// 🔴 THIS IS A SOURCE SCAN. Rendering the modal needs a provider list, a model catalogue and auth;
// what actually has to hold is the SHAPE of the condition, and a render test that mounted a stub
// would pass with the condition inverted. The conditions are asserted where they are written.
const SRC = readFileSync(
  resolve(process.cwd(), 'src/features/settings/AddModelModal.tsx'),
  'utf-8',
);

describe('AddModelModal — the chat context floor', () => {
  it('declares a floor derived from the measurement, not a round number', () => {
    expect(SRC).toContain('CHAT_CONTEXT_FLOOR');
    const m = /CHAT_CONTEXT_FLOOR\s*=\s*([\d_]+)/.exec(SRC);
    expect(m, 'the floor must be a literal the reader can check').toBeTruthy();
    const floor = Number(m![1].replace(/_/g, ''));
    // It must clear the measured 10,960 (9,732 tools + 1,228 safety) with headroom, and must not
    // be so high it rejects ordinary 16K models.
    expect(floor).toBeGreaterThan(10_960);
    expect(floor).toBeLessThanOrEqual(16_000);
  });

  it('cites the measurement that produced it', () => {
    // A threshold with no provenance is the next person's mystery constant.
    expect(SRC).toContain('9,732');
    expect(SRC).toContain('1,228');
  });

  it('🔴 warns only for CHAT-capable models', () => {
    // Without this the banner fires on every reranker and embedding model, and a banner that is
    // usually wrong is one people learn to skip past.
    const cond = /\{flags\.chat && contextLength[\s\S]{0,160}?CHAT_CONTEXT_FLOOR/.exec(SRC);
    expect(cond, 'the warning must be gated on flags.chat').toBeTruthy();
  });

  it('🔴 says nothing when the field is empty', () => {
    // An empty context length means "unknown", not "zero". Warning there would fire on every
    // model the user has not filled in yet.
    expect(SRC).toMatch(/contextLength\s*&&\s*Number\(contextLength\)\s*>\s*0/);
  });

  it('is advisory — it does not disable submit', () => {
    // The arm that keeps the decision honest. If a future change turns this into a gate, the
    // reason it was advisory (the floor moves with the tool count) has to be re-argued first.
    const banner = SRC.slice(SRC.indexOf('model-context-too-small'));
    expect(banner.slice(0, 400)).not.toMatch(/disabled=\{[^}]*CHAT_CONTEXT_FLOOR/);
  });

  it('the context-length input is declarable', () => {
    // R7 also closes a small parity hole: this form had no testids at all.
    expect(SRC).toContain('data-testid="model-context-length"');
  });
});
