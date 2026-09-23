import { Check, Circle, Minus, X } from 'lucide-react';
import { Spinner } from '@/components/ui/Spinner';
import type { PlanStep, StatusEvent, StepStatus } from '@/types/api';
import { cn } from '@/utils/cn';
import { formatDuration } from '@/utils/format';
import { STAGE_LABELS } from './chatState';

const TOOL_LABELS: Record<PlanStep['tool'], string> = {
  sql: 'Database',
  rag: 'Knowledge base',
  general: 'Reasoning',
};

export function StepIcon({ status }: { status: StepStatus }) {
  switch (status) {
    case 'running':
      return <Spinner size="sm" className="text-accent" />;
    case 'completed':
      return <Check className="size-3.5 text-success" aria-hidden />;
    case 'failed':
      return <X className="size-3.5 text-danger" aria-hidden />;
    case 'skipped':
      return <Minus className="size-3.5 text-fg-subtle" aria-hidden />;
    default:
      return <Circle className="size-3 text-fg-subtle" aria-hidden />;
  }
}

export function PlanChecklist({ steps }: { steps: PlanStep[] }) {
  if (steps.length === 0) return null;
  return (
    <ol className="space-y-1.5" aria-label="Plan">
      {steps.map((step) => (
        <li key={step.id} className="flex items-start gap-2 text-[13px]">
          <span className="mt-0.5 flex size-4 items-center justify-center" aria-label={step.status}>
            <StepIcon status={step.status} />
          </span>
          <div className="min-w-0 flex-1">
            <p
              className={cn('text-fg', step.status === 'skipped' && 'text-fg-subtle line-through')}
            >
              <span className="mr-1.5 text-[11px] font-medium text-fg-subtle uppercase">
                {TOOL_LABELS[step.tool]}
              </span>
              {step.description}
            </p>
            {step.summary && <p className="text-xs text-fg-muted">{step.summary}</p>}
          </div>
          {step.duration_ms !== undefined && (
            <span className="shrink-0 text-xs text-fg-subtle tabular-nums">
              {formatDuration(step.duration_ms)}
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}

/** Live status line and plan checklist shown while the agent works. */
export function ToolActivity({ status, plan }: { status: StatusEvent | null; plan: PlanStep[] }) {
  const label = status ? status.label || STAGE_LABELS[status.stage] : STAGE_LABELS.analyzing;
  return (
    <div
      className="mb-3 rounded-xl border border-line bg-surface-2/60 p-3"
      data-testid="tool-activity"
    >
      <p className="flex items-center gap-2 text-[13px] font-medium text-fg-muted">
        <Spinner size="sm" className="text-accent" />
        {label}
      </p>
      {plan.length > 0 && (
        <div className="mt-2.5 border-t border-line pt-2.5">
          <PlanChecklist steps={plan} />
        </div>
      )}
    </div>
  );
}
