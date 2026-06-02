import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SourceCard } from '../SourceCard';
import type { Source } from '../../types';
import type { UserModel } from '@/features/settings/api';

const S = (over: Partial<Source> = {}): Source =>
  ({
    corpus_id: 'c-1',
    project_id: 'proj-9',
    name: '封神演義',
    kind: 'fengshen',
    license: 'public_domain',
    provenance_json: {},
    created_at: '',
    updated_at: '',
    ...over,
  } as Source);

const EMBEDS: UserModel[] = [{ user_model_id: 'm1', alias: 'bge' } as UserModel];

beforeEach(() => vi.clearAllMocks());

describe('SourceCard', () => {
  it('renders the card shell with the source name', () => {
    render(<SourceCard source={S()} embeds={EMBEDS} onIngest={vi.fn()} />);
    expect(screen.getByTestId('enrichment-source-card')).toBeInTheDocument();
    expect(screen.getByText('封神演義')).toBeInTheDocument();
  });

  it('recookable license: success-styled badge + recook_ok note, card not dimmed', () => {
    render(<SourceCard source={S({ license: 'public_domain' })} embeds={EMBEDS} onIngest={vi.fn()} />);
    const badge = screen.getByText('license.public_domain');
    expect(badge.className).toContain('text-success');
    expect(badge.className).not.toContain('text-destructive');
    expect(screen.getByText(/sources\.recook_ok/)).toBeInTheDocument();
    expect(screen.getByTestId('enrichment-source-card').className).not.toContain('opacity-80');
  });

  it('non-recookable license: destructive-styled badge + recook_refused note, card dimmed', () => {
    render(<SourceCard source={S({ license: 'copyrighted' })} embeds={EMBEDS} onIngest={vi.fn()} />);
    const badge = screen.getByText('license.copyrighted');
    expect(badge.className).toContain('text-destructive');
    expect(screen.getByText(/sources\.recook_refused/)).toBeInTheDocument();
    expect(screen.getByTestId('enrichment-source-card').className).toContain('opacity-80');
  });

  it('renders the chunk_count line key when chunk_count is present', () => {
    render(<SourceCard source={S({ chunk_count: 3 })} embeds={EMBEDS} onIngest={vi.fn()} />);
    // dotted i18n key has no {{count}} token to interpolate -> returns the key verbatim
    expect(screen.getByText(/sources\.chunks/)).toBeInTheDocument();
  });

  it('omits the chunk_count line key when chunk_count is absent', () => {
    render(<SourceCard source={S()} embeds={EMBEDS} onIngest={vi.fn()} />);
    expect(screen.queryByText(/sources\.chunks/)).toBeNull();
  });

  it('the ingest form is hidden until the ingest toggle is clicked', () => {
    render(<SourceCard source={S()} embeds={EMBEDS} onIngest={vi.fn()} />);
    expect(screen.queryByTestId('enrichment-ingest-text')).toBeNull();
    fireEvent.click(screen.getByText('sources.ingest'));
    expect(screen.getByTestId('enrichment-ingest-text')).toBeInTheDocument();
  });

  it('the save button is disabled until both text and an embed model are set', () => {
    render(<SourceCard source={S()} embeds={EMBEDS} onIngest={vi.fn()} />);
    fireEvent.click(screen.getByText('sources.ingest'));
    const save = screen.getByText('actions.save');
    // nothing entered yet
    expect(save).toBeDisabled();
    // text only -> still disabled (no embed model)
    fireEvent.change(screen.getByTestId('enrichment-ingest-text'), {
      target: { value: 'some corpus text' },
    });
    expect(save).toBeDisabled();
    // pick the embed model -> now enabled
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'm1' } });
    expect(save).not.toBeDisabled();
  });

  it('submit calls onIngest(corpusId, { text trimmed, embedding_model_ref }) then closes the form on success', async () => {
    const onIngest = vi.fn().mockResolvedValue({ corpus_id: 'c-1', chunks_embedded: 2 });
    render(<SourceCard source={S()} embeds={EMBEDS} onIngest={onIngest} />);
    fireEvent.click(screen.getByText('sources.ingest'));
    fireEvent.change(screen.getByTestId('enrichment-ingest-text'), {
      target: { value: '  padded text  ' },
    });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'm1' } });
    fireEvent.click(screen.getByText('actions.save'));
    expect(onIngest).toHaveBeenCalledWith('c-1', {
      text: 'padded text',
      embedding_model_ref: 'm1',
    });
    // success -> form collapses (text + form gone)
    await waitFor(() => expect(screen.queryByTestId('enrichment-ingest-text')).toBeNull());
  });

  it('busy: save shows the ingesting label and stays disabled', () => {
    render(<SourceCard source={S()} embeds={EMBEDS} onIngest={vi.fn()} busy />);
    fireEvent.click(screen.getByText('sources.ingest'));
    fireEvent.change(screen.getByTestId('enrichment-ingest-text'), {
      target: { value: 'text' },
    });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'm1' } });
    expect(screen.getByText('sources.ingesting')).toBeInTheDocument();
    expect(screen.getByText('sources.ingesting')).toBeDisabled();
  });
});
