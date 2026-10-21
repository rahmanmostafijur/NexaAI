import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { readSession } from '@/services/session';
import { TEST_ADMIN, jsonResponse, renderWithProviders, requestUrl, signIn } from '@/test/utils';
import { SecurityCard } from './SecurityCard';

function stubChangePassword(response: Response) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) =>
      requestUrl(input).endsWith('/auth/change-password') ? response : jsonResponse(TEST_ADMIN),
    ),
  );
}

async function fillAndSubmit() {
  await userEvent.type(await screen.findByLabelText('Current password'), 'old-pass-1');
  await userEvent.type(screen.getByLabelText(/^New password/), 'new-pass-2');
  await userEvent.click(screen.getByRole('button', { name: 'Change password' }));
}

describe('SecurityCard', () => {
  it('shows a clear message when the current password is wrong', async () => {
    signIn();
    stubChangePassword(
      jsonResponse({ error: { code: 'invalid_credentials', message: 'nope' } }, 401),
    );
    renderWithProviders(<SecurityCard />);

    await fillAndSubmit();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your current password is incorrect.',
    );
  });

  it('keeps the user signed in on this device after a successful change', async () => {
    signIn();
    stubChangePassword(
      jsonResponse({
        access_token: 'fresh-token',
        token_type: 'bearer',
        expires_in: 900,
        user: TEST_ADMIN,
      }),
    );
    renderWithProviders(<SecurityCard />);

    await fillAndSubmit();

    await waitFor(() => expect(readSession()?.token).toBe('fresh-token'));
    expect(await screen.findByText('Password changed')).toBeInTheDocument();
  });
});
