/**
 * An EMPTY translation must not hide text the app already has.
 *
 * 🔴 THE DEFECT THIS PINS, measured 2026-09-13. All 48
 * `composition.structureTemplates.beats.*.purpose` keys are `""` in `en` and fully written in
 * the other 17 locales. `localizedBeat()` asks for them as
 *
 *     t(base + '.purpose', { defaultValue: beat.purpose ?? '' })
 *
 * and the server DOES send an English purpose -- `migrate.py` seeds
 * `"A snapshot of the hero's world + tone before change."` and 47 more. But i18next's
 * `returnEmptyString` defaults to TRUE, so `""` in the resource is a legitimate VALUE, not a
 * miss: `t()` returns `""` and `defaultValue` is never consulted. `StructureTemplatesPanel`
 * renders `{lb.purpose && <div>…}`, so the line simply is not drawn.
 *
 * The result is the reverse of how the i18n risk has been described all along: **English is the
 * degraded locale.** A Vietnamese author reads what each story beat is for; an English author
 * gets a blank, for Save the Cat, Hero's Journey, Story Circle, Kishotenketsu and Web Novel --
 * the product's core planning feature.
 *
 * The fix is `returnEmptyString: false` in `src/i18n/index.ts`, which makes `""` mean "missing"
 * so the `defaultValue` the call site already passes is used. Blast radius is exactly these 48
 * keys: they are the ONLY empty values in any of the 18 locales.
 */
import { describe, it, expect, beforeAll } from 'vitest';
import i18n from '../index';
import { localizedBeat } from '../../features/composition/structureTemplateLocalization';
import type { Beat, StructureTemplate } from '../../features/composition/types';

// A SYSTEM template (owner_user_id null) — user-owned ones bypass localization entirely.
const SYSTEM = { kind: 'save_the_cat', owner_user_id: null } as unknown as Pick<
  StructureTemplate,
  'kind' | 'owner_user_id'
>;

// What composition-service actually seeds for this beat (services/composition-service/app/db/migrate.py).
const SERVER_PURPOSE = "A snapshot of the hero's world + tone before change.";
const BEAT = { key: 'opening_image', label: 'Opening Image', purpose: SERVER_PURPOSE } as unknown as Beat;

describe('an empty translation must not suppress content the app already has', () => {
  beforeAll(async () => {
    if (!i18n.isInitialized) await i18n.init();
    await i18n.changeLanguage('en');
  });

  it('gives an English reader the beat purpose the server sent', () => {
    const t = i18n.getFixedT(null, 'composition');
    const out = localizedBeat(t, SYSTEM, BEAT);
    expect(
      out.purpose,
      'the English `purpose` resource is "" while the server sends real text; if an empty ' +
        'string wins, an English author sees a blank where every other language shows what ' +
        'the beat is for',
    ).toBe(SERVER_PURPOSE);
  });

  it('still prefers a real translation over the server default', async () => {
    await i18n.changeLanguage('vi');
    const t = i18n.getFixedT(null, 'composition');
    const out = localizedBeat(t, SYSTEM, BEAT);
    expect(
      out.purpose,
      'Vietnamese HAS this string; the fallback must not start overriding real translations',
    ).not.toBe(SERVER_PURPOSE);
    expect(out.purpose.length).toBeGreaterThan(0);
    await i18n.changeLanguage('en');
  });

  it('is the only class affected: no locale has an empty value except those 48 purposes', async () => {
    const mods = import.meta.glob('../locales/*/*.json', { eager: true }) as Record<
      string,
      { default: unknown }
    >;
    const empties: string[] = [];
    const walk = (node: unknown, path: string) => {
      if (typeof node === 'string') {
        if (!node.trim()) empties.push(path);
        return;
      }
      if (node && typeof node === 'object') {
        for (const [k, v] of Object.entries(node as Record<string, unknown>)) walk(v, `${path}.${k}`);
      }
    };
    for (const [file, mod] of Object.entries(mods)) walk(mod.default, file);
    const offenders = empties.filter((p) => !p.endsWith('.purpose'));
    expect(
      offenders,
      'returnEmptyString:false makes every empty value fall back. That is safe only while the ' +
        'ONLY empty values are these beat purposes — a new one elsewhere would silently start ' +
        'rendering its defaultValue, or its key.',
    ).toEqual([]);
  });
});
