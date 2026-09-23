import { AlertTriangle, ShieldCheck } from 'lucide-react';
import type { ReactNode } from 'react';
import { RoutePill } from '@/components/RoutePill';
import { Badge } from '@/components/ui/Badge';
import { SqlBlock } from '@/features/chat/SqlBlock';
import { sourceLabel } from '@/features/chat/sourceLabel';
import { PlanChecklist } from '@/features/chat/ToolActivity';
import { formatDuration, formatPercent } from '@/utils/format';
import { langFor } from '@/utils/script';
import type { InspectorData } from './inspectorData';

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-b border-line px-4 py-4 last:border-b-0">
      <h3 className="mb-2.5 text-[11px] font-semibold tracking-wide text-fg-subtle uppercase">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1 text-sm">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="min-w-0 text-right text-fg">{children}</dd>
    </div>
  );
}

export function AnalysisSection({ data }: { data: InspectorData }) {
  const confidence = data.confidence;
  return (
    <Section title="Query analysis">
      <dl>
        <Row label="Language">{data.language ?? '—'}</Row>
        <Row label="Route">{data.route ? <RoutePill route={data.route} /> : '—'}</Row>
        <Row label="Confidence">{confidence !== null ? formatPercent(confidence) : '—'}</Row>
      </dl>
      {confidence !== null && (
        <div
          className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-3"
          role="meter"
          aria-label="Routing confidence"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(confidence * 100)}
        >
          <div
            className="h-full rounded-full bg-accent"
            style={{ width: formatPercent(confidence) }}
          />
        </div>
      )}
      {data.reason && (
        <p className="mt-3 text-sm text-fg-muted" lang={langFor(data.reason)}>
          {data.reason}
        </p>
      )}
      {data.standaloneQuery && (
        <p
          className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-xs text-fg-muted"
          lang={langFor(data.standaloneQuery)}
        >
          <span className="font-medium text-fg">Resolved query: </span>
          {data.standaloneQuery}
        </p>
      )}
      {data.grounded !== null && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {data.grounded ? (
            <Badge tone="success">
              <ShieldCheck className="size-3" aria-hidden /> Grounded in sources
            </Badge>
          ) : (
            <Badge tone="warning">Not grounded</Badge>
          )}
        </div>
      )}
      {data.warnings.length > 0 && (
        <ul className="mt-3 space-y-1">
          {data.warnings.map((w) => (
            <li key={w} className="flex items-start gap-1.5 text-xs text-warning">
              <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden /> {w}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export function ToolsSection({ data }: { data: InspectorData }) {
  const tools = data.plan.filter((s) => s.status !== 'pending');
  if (tools.length === 0) return null;
  return (
    <Section title="Tools used">
      <ul className="space-y-1">
        {tools.map((step) => (
          <li key={step.id} className="flex justify-between gap-2 text-sm">
            <span className="font-mono text-xs text-fg">
              {step.tool}
              <span className="ml-1.5 font-sans text-fg-subtle">{step.status}</span>
            </span>
            <span className="text-xs text-fg-muted tabular-nums">
              {formatDuration(step.duration_ms)}
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

export function SourcesSection({ data }: { data: InspectorData }) {
  if (data.sources.length === 0) return null;
  return (
    <Section title="Sources">
      <ul className="space-y-1.5">
        {data.sources.map((s) => (
          <li key={s.id} className="flex gap-2 text-sm">
            <span className="font-mono text-xs font-semibold text-fg-subtle">{s.id}</span>
            <span className="min-w-0 flex-1 text-fg" lang={langFor(s.title)}>
              {sourceLabel(s)}
              {s.type === 'document' && (
                <span className="ml-1.5 text-xs text-fg-subtle">score {s.score.toFixed(2)}</span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

export function SqlSection({ data }: { data: InspectorData }) {
  if (data.sql.length === 0) return null;
  return (
    <Section title="Generated SQL">
      {data.sql.map((result) => (
        <SqlBlock key={result.step_id} result={result} />
      ))}
    </Section>
  );
}

export function TimingsSection({ data }: { data: InspectorData }) {
  const timings = data.timings;
  if (!timings) return null;
  const max = Math.max(1, ...timings.stages.map((s) => s.duration_ms));
  return (
    <Section title="Timings">
      <p className="mb-2 text-sm text-fg">
        Total <span className="font-semibold tabular-nums">{formatDuration(timings.total_ms)}</span>
      </p>
      <ul className="space-y-1.5">
        {timings.stages.map((stage) => (
          <li key={stage.name} className="text-xs">
            <div className="flex justify-between text-fg-muted">
              <span>{stage.name}</span>
              <span className="tabular-nums">{formatDuration(stage.duration_ms)}</span>
            </div>
            <div className="mt-0.5 h-1 rounded-full bg-surface-3">
              <div
                className="h-full rounded-full bg-accent/70"
                style={{ width: `${(stage.duration_ms / max) * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </Section>
  );
}

export function PlanSection({ data }: { data: InspectorData }) {
  if (data.plan.length === 0) return null;
  return (
    <Section title="Plan">
      <PlanChecklist steps={data.plan} />
    </Section>
  );
}
