import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IntentScreen } from '../IntentScreen';
import '@/i18n';

// C22 — the intent screen renders exactly four choices and reports the picked
// intent through onChoose (explicit callback — NOT a useEffect reaction).

describe('IntentScreen (C22)', () => {
  it('renders exactly four intent choices', () => {
    render(<IntentScreen onChoose={() => {}} />);
    const list = screen.getByTestId('intent-choices');
    expect(list.querySelectorAll('button')).toHaveLength(4);
    expect(screen.getByTestId('intent-write')).toBeInTheDocument();
    expect(screen.getByTestId('intent-world')).toBeInTheDocument();
    expect(screen.getByTestId('intent-translate')).toBeInTheDocument();
    expect(screen.getByTestId('intent-explore')).toBeInTheDocument();
  });

  it.each(['write', 'world', 'translate', 'explore'] as const)(
    'fires onChoose("%s") when that card is clicked',
    (id) => {
      const onChoose = vi.fn();
      render(<IntentScreen onChoose={onChoose} />);
      fireEvent.click(screen.getByTestId(`intent-${id}`));
      expect(onChoose).toHaveBeenCalledTimes(1);
      expect(onChoose).toHaveBeenCalledWith(id);
    },
  );
});
