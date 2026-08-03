import { describe, expect, it, beforeEach, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { VerifyPage } from '../VerifyPage';
import { apiJson } from '../../../api';

vi.mock('../../../api', () => ({
  apiJson: vi.fn(),
}));

const mockedApiJson = vi.mocked(apiJson);

function renderPage(entry = '/verify') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <VerifyPage />
    </MemoryRouter>,
  );
}

describe('VerifyPage', () => {
  beforeEach(() => {
    mockedApiJson.mockReset();
  });

  it('automatically confirms a token from the email link', async () => {
    mockedApiJson.mockResolvedValue({ status: 'verified' });

    renderPage('/verify?token=email-token');

    await waitFor(() => expect(mockedApiJson).toHaveBeenCalledWith(
      '/v1/auth/verify-email/confirm',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ token: 'email-token' }),
      }),
    ));
    expect(await screen.findByTestId('verify-success')).toBeInTheDocument();
  });

  it('allows a token to be pasted and reports API errors', async () => {
    mockedApiJson.mockRejectedValue(new Error('token expired'));

    renderPage();
    fireEvent.change(screen.getByTestId('verify-token-input'), { target: { value: 'pasted-token' } });
    fireEvent.click(screen.getByTestId('verify-submit-button'));

    expect(await screen.findByTestId('verify-error')).toHaveTextContent('token expired');
    expect(mockedApiJson).toHaveBeenCalledWith(
      '/v1/auth/verify-email/confirm',
      expect.objectContaining({ body: JSON.stringify({ token: 'pasted-token' }) }),
    );
  });
});
