// Plan Hub — the pure node-card presentation helpers (status → texture).
import { describe, expect, it } from 'vitest';
import { chapterCardClass, normStatus, statusDotClass } from '../flowPresentation';

describe('status maps', () => {
  it('normalises unknown status to outline', () => {
    expect(normStatus('done')).toBe('done');
    expect(normStatus('weird')).toBe('outline');
  });

  it('empty is a dashed transparent card; done is success-tinted; drafting dot is amber', () => {
    expect(chapterCardClass('empty')).toContain('border-dashed');
    expect(chapterCardClass('done')).toContain('success');
    expect(statusDotClass('drafting')).toContain('bg-primary');
  });
});
