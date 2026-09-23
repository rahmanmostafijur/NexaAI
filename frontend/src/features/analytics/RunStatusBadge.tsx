import { Badge } from '@/components/ui/Badge';
import type { RunStatus } from '@/types/api';

export function RunStatusBadge({ status }: { status: RunStatus | string }) {
  const tone =
    status === 'success' || status === 'completed'
      ? 'success'
      : status === 'failed' || status === 'error'
        ? 'danger'
        : status === 'running'
          ? 'accent'
          : 'neutral';
  return <Badge tone={tone}>{status}</Badge>;
}
