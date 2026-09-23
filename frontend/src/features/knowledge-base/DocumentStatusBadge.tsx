import { Badge, type BadgeTone } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { Tooltip } from '@/components/ui/Tooltip';
import type { KbDocument } from '@/types/api';

const TONES: Record<KbDocument['status'], BadgeTone> = {
  pending: 'neutral',
  processing: 'accent',
  indexed: 'success',
  failed: 'danger',
};

const LABELS: Record<KbDocument['status'], string> = {
  pending: 'Pending',
  processing: 'Processing',
  indexed: 'Indexed',
  failed: 'Failed',
};

export function DocumentStatusBadge({ doc }: { doc: KbDocument }) {
  const badge = (
    <Badge tone={TONES[doc.status]}>
      {(doc.status === 'pending' || doc.status === 'processing') && (
        <Spinner size="sm" className="size-2.5!" />
      )}
      {LABELS[doc.status]}
    </Badge>
  );
  if (doc.status !== 'failed' || !doc.error) return badge;
  return (
    <Tooltip content={doc.error}>
      {(describedBy) => (
        <span tabIndex={0} aria-describedby={describedBy} className="rounded-full">
          {badge}
        </span>
      )}
    </Tooltip>
  );
}
