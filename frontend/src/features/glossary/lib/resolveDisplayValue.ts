import type { AttributeValue } from '../types';

/** True when the UI should show translated text for the picked display language. */
export function isDisplayingTranslation(
  displayLang: string | undefined,
  bookOriginalLang?: string,
): boolean {
  if (!displayLang) return false;
  if (!bookOriginalLang) return true;
  return displayLang !== bookOriginalLang;
}

/** Resolve attribute text for glossary display: translation if non-empty, else original. */
export function resolveAttrValue(
  attr: Pick<AttributeValue, 'original_value' | 'translations'>,
  displayLang: string | undefined,
  originalLang: string | undefined,
): string {
  if (!displayLang) {
    return attr.original_value ?? '';
  }
  if (originalLang && displayLang === originalLang) {
    return attr.original_value ?? '';
  }
  const tr = attr.translations.find(
    (t) => t.language_code === displayLang && t.value.trim() !== '',
  );
  return tr?.value ?? attr.original_value ?? '';
}

function pickNameAttribute(attributeValues: AttributeValue[]): AttributeValue | undefined {
  const candidates = attributeValues
    .filter((av) => ['name', 'term'].includes(av.attribute_def.code))
    .sort((a, b) => a.attribute_def.sort_order - b.attribute_def.sort_order);
  return candidates[0];
}

/** Resolve entity display name from name/term attributes (matches BE sort_order). */
export function resolveEntityDisplayName(
  attributeValues: AttributeValue[],
  displayLang: string | undefined,
  originalLang: string | undefined,
): string {
  const nameAttr = pickNameAttribute(attributeValues);
  if (!nameAttr) return '';
  return resolveAttrValue(nameAttr, displayLang, originalLang);
}
