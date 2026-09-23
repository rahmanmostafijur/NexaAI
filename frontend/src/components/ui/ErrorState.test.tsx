import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ErrorState } from './ErrorState';

describe('ErrorState', () => {
  it('shows the message and calls onRetry when "Try again" is clicked', async () => {
    const onRetry = vi.fn();
    render(<ErrorState title="Couldn't load" message="Server unavailable" onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toHaveTextContent("Couldn't load");
    expect(screen.getByText('Server unavailable')).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('hides the retry button when no callback is given', () => {
    render(<ErrorState message="Nope" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
