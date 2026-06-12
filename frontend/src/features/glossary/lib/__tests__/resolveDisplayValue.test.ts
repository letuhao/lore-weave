import { describe, it, expect } from 'vitest';
import { resolveAttrValue, resolveEntityDisplayName, hasTranslationForLang } from '../resolveDisplayValue';
import type { AttributeValue } from '../../types';

const baseAttr = (overrides: Partial<AttributeValue> = {}): AttributeValue => ({
  attr_value_id: 'av-1',
  entity_id: 'e-1',
  attr_def_id: 'ad-1',
  attribute_def: {
    attr_def_id: 'ad-1',
    code: 'name',
    name: 'Name',
    field_type: 'text',
    is_required: true,
    is_system: true,
    is_active: true,
    sort_order: 1,
    genre_tags: [],
  },
  original_language: 'zh',
  original_value: '焰魔',
  translations: [],
  evidences: [],
  ...overrides,
});

describe('resolveAttrValue', () => {
  it('returns original when display lang equals original', () => {
    const attr = baseAttr();
    expect(resolveAttrValue(attr, 'zh', 'zh')).toBe('焰魔');
  });

  it('returns translation when present', () => {
    const attr = baseAttr({
      translations: [
        {
          translation_id: 't-1',
          attr_value_id: 'av-1',
          language_code: 'vi',
          value: 'Diễm Ma',
          confidence: 'machine',
          translator: null,
          updated_at: '',
        },
      ],
    });
    expect(resolveAttrValue(attr, 'vi', 'zh')).toBe('Diễm Ma');
  });

  it('falls back to original when translation missing', () => {
    const attr = baseAttr();
    expect(resolveAttrValue(attr, 'vi', 'zh')).toBe('焰魔');
  });

  it('falls back when translation is empty string', () => {
    const attr = baseAttr({
      translations: [
        {
          translation_id: 't-1',
          attr_value_id: 'av-1',
          language_code: 'vi',
          value: '   ',
          confidence: 'draft',
          translator: null,
          updated_at: '',
        },
      ],
    });
    expect(resolveAttrValue(attr, 'vi', 'zh')).toBe('焰魔');
  });
});

describe('resolveEntityDisplayName', () => {
  it('picks name attribute', () => {
    const attrs = [
      baseAttr(),
      baseAttr({
        attr_value_id: 'av-2',
        attribute_def: { ...baseAttr().attribute_def, code: 'description' },
        original_value: 'desc',
      }),
    ];
    expect(resolveEntityDisplayName(attrs, 'zh', 'zh')).toBe('焰魔');
  });
});

describe('hasTranslationForLang', () => {
  it('detects non-empty translation', () => {
    expect(
      hasTranslationForLang(
        [{ translation_id: '1', attr_value_id: 'a', language_code: 'vi', value: 'x', confidence: 'draft', translator: null, updated_at: '' }],
        'vi',
      ),
    ).toBe(true);
  });
});
