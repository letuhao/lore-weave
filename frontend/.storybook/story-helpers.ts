// C13 — shared helpers for play() interactions across story files.
//
// Stories in this codebase use native `<select>` + Radix Dialog
// portals. Testing-library's default `getByRole('combobox')` /
// `getByRole('button', {name})` has drifted across versions, and
// Radix portals render into `document.body` — OUTSIDE the story
// `canvasElement` subtree. That means `within(canvasElement)` and
// `canvasElement.querySelector*` both miss portal content.
//
// Helpers below query against `document` (or `document.body`) to
// reach portal-rendered nodes. Each dialog story is rendered in
// isolation, so the "first dialog in the document" is unambiguous.

/**
 * Find the "Confirm" / "Build graph" / "Change model" primary button
 * inside the dialog footer, without coupling to the i18n literal
 * (which differs per dialog and per locale). Strategy: locate the
 * first `[role="dialog"]` in the document, drop buttons whose text
 * is "Cancel" or "Close", pick the last remaining — convention:
 * confirm is rightmost in the footer. `_root` is accepted but
 * ignored — callers pass `canvasElement` for symmetry with other
 * testing-library helpers; we query `document` because Radix
 * portals escape the canvas subtree.
 */
export function findConfirmButton(_root: HTMLElement): HTMLButtonElement | null {
  const dialog = document.querySelector('[role="dialog"]');
  if (!dialog) return null;
  const buttons = Array.from(dialog.querySelectorAll('button'));
  const candidates = buttons.filter((b) => {
    const txt = (b.textContent ?? '').trim().toLowerCase();
    return txt.length > 0 && txt !== 'cancel' && txt !== 'close';
  });
  return candidates[candidates.length - 1] ?? null;
}

/**
 * Wait for N `<select>` elements to render in the document (BuildGraph
 * has 2 — LLM + embedding picker; ChangeModel has 1 — picker). The
 * `_root` param is ignored — we query `document` because Radix
 * portals the dialog content outside `canvasElement`.
 *
 * Optionally waits for a specific option `value` to appear in the
 * target select. Native `<select>` initially renders only a
 * placeholder "<option value=''>" until the models useQuery
 * resolves — waiting for the target option lets play() fire
 * `selectOptions(selects[i], value)` without a race.
 */
export function waitForSelects(
  _root: HTMLElement,
  minCount: number,
  opts: { withOptionValue?: { selectIndex: number; value: string } } = {},
): Promise<NodeListOf<HTMLSelectElement>> {
  return new Promise((resolve, reject) => {
    const start = performance.now();
    const timeout = 5000;
    const tick = () => {
      const list = document.querySelectorAll('select');
      if (list.length >= minCount) {
        const need = opts.withOptionValue;
        if (!need) return resolve(list);
        const target = list[need.selectIndex];
        if (target && Array.from(target.options).some((o) => o.value === need.value)) {
          return resolve(list);
        }
      }
      if (performance.now() - start > timeout) {
        return reject(
          new Error(
            `waitForSelects: expected ${minCount} selects${opts.withOptionValue ? ` with option '${opts.withOptionValue.value}'` : ''}; got ${list.length}`,
          ),
        );
      }
      setTimeout(tick, 100);
    };
    tick();
  });
}

/**
 * Find the Run-benchmark CTA by its visible text. Unlike the
 * confirm button it lives inside the picker's label, not the
 * dialog footer.
 */
export function findRunBenchmarkButton(): HTMLButtonElement | null {
  const dialog = document.querySelector('[role="dialog"]');
  if (!dialog) return null;
  const buttons = Array.from(dialog.querySelectorAll('button'));
  return buttons.find((b) => /run benchmark/i.test(b.textContent ?? '')) ?? null;
}

/**
 * Wait for a single `<select>` to render with (optionally) a
 * specific option value present — ChangeModelDialog's embedding
 * picker. Convenience wrapper around waitForSelects.
 */
export async function waitForSingleSelect(
  root: HTMLElement,
  opts: { withOptionValue?: string } = {},
): Promise<HTMLSelectElement> {
  const list = await waitForSelects(root, 1, {
    withOptionValue: opts.withOptionValue
      ? { selectIndex: 0, value: opts.withOptionValue }
      : undefined,
  });
  return list[0];
}
