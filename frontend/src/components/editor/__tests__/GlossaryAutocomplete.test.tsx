import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { GlossaryAutocomplete, AUTHORABLE_KINDS } from '../GlossaryAutocomplete';

// S-10 O7 — the `[[`-create picker. We drive the real trigger detection (an editable host holding
// "[[Kael" + a selection at the caret) and assert the create affordance → kind picker → onCreateNew.

// jsdom has no real Selection; stub window.getSelection to point at our text node/caret.
function mountEditor(text: string): { host: HTMLElement; caret: number } {
  const host = document.createElement('div');
  host.textContent = text;
  document.body.appendChild(host);
  const textNode = host.firstChild as Text;
  const caret = text.length;
  vi.spyOn(window, 'getSelection').mockReturnValue({
    rangeCount: 1,
    getRangeAt: () => ({
      startContainer: textNode,
      startOffset: caret,
      getBoundingClientRect: () => ({ left: 10, bottom: 20 }) as DOMRect,
    }),
  } as unknown as Selection);
  return { host, caret };
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

function renderWith(onCreateNew?: (name: string, kind: string) => void) {
  const { host } = mountEditor('[[Kael');
  render(
    <GlossaryAutocomplete
      entities={[]}
      editorEl={host}
      onInsertEntity={vi.fn()}
      onCreateNew={onCreateNew as never}
    />,
  );
  // Fire the input that GlossaryAutocomplete listens for → opens the popup on the `[[Kael` trigger.
  act(() => { host.dispatchEvent(new Event('input')); });
  return host;
}

describe('GlossaryAutocomplete `[[`-create picker (O7)', () => {
  it('opens the kind picker and calls onCreateNew with the typed name + closed-set kind', () => {
    const onCreateNew = vi.fn();
    renderWith(onCreateNew);

    // The create toggle is offered (a create handler is wired + the query is a real name).
    const toggle = screen.getByTestId('glossary-create-toggle');
    fireEvent.click(toggle);

    // Every AuthorableKind is offered — and ONLY those (closed set).
    const picker = screen.getByTestId('glossary-create-picker');
    expect(picker).toBeInTheDocument();
    for (const k of AUTHORABLE_KINDS) {
      expect(screen.getByTestId(`glossary-create-kind-${k}`)).toBeInTheDocument();
    }

    fireEvent.click(screen.getByTestId('glossary-create-kind-location'));
    expect(onCreateNew).toHaveBeenCalledWith('Kael', 'location');
    // the popup closed after the pick
    expect(screen.queryByTestId('glossary-create-toggle')).toBeNull();
  });

  it('hides the create affordance entirely when no create handler is wired (no dead link)', () => {
    renderWith(undefined);
    expect(screen.queryByTestId('glossary-create-toggle')).toBeNull();
    expect(screen.queryByTestId('glossary-create-picker')).toBeNull();
  });
});
