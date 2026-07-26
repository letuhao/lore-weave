// #12 M-H — the word-count status item (replaces the "— words" placeholder). Reads the
// Tier-4 hoist's live textContent (the editor keeps it in sync per keystroke). Counts
// space-separated words + CJK ideographs/kana as one "word" each (Vietnamese is
// space-separated; zh/ja bodies would undercount badly on a pure word regex).
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useManuscriptUnit } from '../manuscript/unit/ManuscriptUnitProvider';

const CJK_RE = /[぀-ヿ㐀-䶿一-鿿가-힯]/g;

export function countWords(text: string): number {
  if (!text) return 0;
  const cjk = text.match(CJK_RE)?.length ?? 0;
  // \p{L}\p{N}, NOT \w — JS \w stays ASCII-only even under the u flag, which would
  // shred diacritic Vietnamese ("Uyển" → 2 "words").
  const words = text.replace(CJK_RE, ' ').match(/[\p{L}\p{N}]+/gu)?.length ?? 0;
  return words + cjk;
}

export function WordCountStatusItem() {
  const { t } = useTranslation('studio');
  const unit = useManuscriptUnit();
  const text = unit?.state.chapterId ? unit.state.textContent : null;
  const count = useMemo(() => (text == null ? null : countWords(text)), [text]);
  return (
    <span data-testid="status-word-count">
      {count == null
        ? t('status.wordsPlaceholder', { defaultValue: '— words' })
        : t('status.words', { count, defaultValue: `${count.toLocaleString()} words` })}
    </span>
  );
}
