import { SentenceBuffer } from './SentenceBuffer';

// Simple test runner (no jest needed)
let passed = 0;
let failed = 0;
function assert(label: string, condition: boolean) {
  if (condition) { console.log(`  ✓ ${label}`); passed++; }
  else { console.error(`  ✗ ${label}`); failed++; }
}

function collectSentences(tokens: string[], opts = {}): string[] {
  const results: string[] = [];
  const buf = new SentenceBuffer((s) => results.push(s), opts);
  for (const t of tokens) buf.addToken(t);
  buf.markStreamComplete();
  return results;
}

// ── Tests ──────────────────────────────────────────────────────────

console.log('SentenceBuffer Tests:');

// T1: Basic sentence splitting
const t1 = collectSentences(['Hello world. ', 'How are you? ', 'Fine!']);
assert('T1: splits 3 sentences', t1.length === 3);
assert('T1a: first sentence', t1[0] === 'Hello world.');
assert('T1b: second sentence', t1[1] === 'How are you?');
assert('T1c: third sentence', t1[2] === 'Fine!');

// T2: Token-by-token (LLM style)
const t2 = collectSentences(['The ', 'castle ', 'stood ', 'on ', 'a ', 'hill.', ' It ', 'was ', 'old.']);
assert('T2: splits on period boundaries', t2.length === 2);
assert('T2a: first', t2[0] === 'The castle stood on a hill.');
assert('T2b: second', t2[1] === 'It was old.');

// T3: CJK boundaries
const t3 = collectSentences(['魔王站在城楼上。', '他看着远方！']);
assert('T3: CJK boundaries', t3.length === 2);

// T4: Newline as boundary
const t4 = collectSentences(['First line content here\n', 'Second line content here']);
assert('T4: newline is boundary', t4.length === 2);

// T5: Stream complete flushes partial
const t5 = collectSentences(['No period at end']);
assert('T5: flush on stream complete', t5.length === 1);
assert('T5a: content', t5[0] === 'No period at end');

// T6: Quoted speech boundary
const t6 = collectSentences(['"Hello!" ', 'she said with a gentle smile.']);
assert('T6: quoted speech', t6.length === 2);

// T7: Abbreviation not a boundary
const t7 = collectSentences(['Dr. Smith went to the store. ', 'He bought milk.']);
assert('T7: Dr. not a boundary, period after store is', t7.length === 2);
assert('T7a: first includes Dr.', t7[0].includes('Dr.'));

// T8: Force-split long text
const longText = 'A'.repeat(400);
const t8 = collectSentences([longText], { maxLength: 300 });
assert('T8: force-splits >300 chars', t8.length >= 2);
assert('T8a: each chunk <= 300', t8.every(s => s.length <= 300));

// T9: Cancel clears buffer
const results9: string[] = [];
const buf9 = new SentenceBuffer((s) => results9.push(s));
buf9.addToken('Hello world');
buf9.cancel();
buf9.markStreamComplete();
assert('T9: cancel clears buffer', results9.length === 0);

// T10: Empty tokens
const t10 = collectSentences(['', '', 'Hi.', '', '']);
assert('T10: handles empty tokens', t10.length === 1);

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
