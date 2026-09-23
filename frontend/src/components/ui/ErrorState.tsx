import { AlertTriangle, RotateCcw } from 'lucide-react';
import { cn } from '@/utils/cn';
import { Button } from './Button';

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
  className,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn('flex flex-col items-center justify-center px-6 py-10 text-center', className)}
    >
      <div className="mb-3 flex size-11 items-center justify-center rounded-xl bg-danger-soft text-danger">
        <AlertTriangle className="size-5" aria-hidden />
      </div>
      <p className="text-sm font-semibold text-fg">{title}</p>
      {message && <p className="mt-1 max-w-sm text-sm text-fg-muted">{message}</p>}
      {onRetry && (
        <Button
          variant="secondary"
          size="sm"
          className="mt-4"
          onClick={onRetry}
          icon={<RotateCcw className="size-3.5" aria-hidden />}
        >
          Try again
        </Button>
      )}
    </div>
  );
}
