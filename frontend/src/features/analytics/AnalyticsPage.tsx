import { useQuery } from '@tanstack/react-query';
import { Activity, CheckCircle2, Gauge, Timer } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import { languageLabel } from '@/features/inspector/inspectorData';
import { getStats, listRuns } from '@/services/agentRuns';
import { errorMessage } from '@/services/http';
import { queryKeys } from '@/services/queryKeys';
import type { Stats } from '@/types/api';
import { formatDuration, formatNumber, formatPercent } from '@/utils/format';
import { ROUTE_META, isRoute } from '@/utils/routes';
import { BarList, type BarDatum } from './BarList';
import { RunDetailDrawer } from './RunDetailDrawer';
import { RunsTable } from './RunsTable';

const RUN_LIMIT = 50;
const LANGUAGE_BAR = 'bg-teal-500';

function StatCard({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs font-medium text-fg-muted">
        {icon}
        {label}
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-fg tabular-nums">{value}</p>
    </Card>
  );
}

/** Contract gives success_rate as a ratio (0..1); tolerate a 0..100 percentage too. */
function normaliseRate(rate: number): number {
  return rate > 1 ? rate / 100 : rate;
}

function toBars(record: Record<string, number>, kind: 'route' | 'language'): BarDatum[] {
  return Object.entries(record)
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => {
      if (kind === 'route' && isRoute(key)) {
        return { key, value, label: ROUTE_META[key].label, barClass: ROUTE_META[key].bar };
      }
      return {
        key,
        value,
        label: kind === 'language' ? languageLabel(key) : key,
        barClass: LANGUAGE_BAR,
      };
    });
}

function StatsOverview({ stats }: { stats: Stats }) {
  return (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          icon={<Activity className="size-4" aria-hidden />}
          label="Total runs"
          value={formatNumber(stats.total_runs)}
        />
        <StatCard
          icon={<CheckCircle2 className="size-4" aria-hidden />}
          label="Success rate"
          value={formatPercent(normaliseRate(stats.success_rate), 1)}
        />
        <StatCard
          icon={<Timer className="size-4" aria-hidden />}
          label="Avg latency"
          value={formatDuration(stats.avg_latency_ms)}
        />
        <StatCard
          icon={<Gauge className="size-4" aria-hidden />}
          label="p95 latency"
          value={formatDuration(stats.p95_latency_ms)}
        />
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Card className="p-5">
          <BarList title="Route distribution" data={toBars(stats.routes, 'route')} />
        </Card>
        <Card className="p-5">
          <BarList title="Language distribution" data={toBars(stats.languages, 'language')} />
        </Card>
      </div>
    </>
  );
}

export function AnalyticsPage() {
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const stats = useQuery({ queryKey: queryKeys.stats, queryFn: getStats });
  const runs = useQuery({ queryKey: queryKeys.runs, queryFn: () => listRuns(RUN_LIMIT) });

  return (
    <PageContainer title="Analytics" description="How the agent is being used and how it performs.">
      <section aria-label="Summary">
        {stats.isPending ? (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        ) : stats.isError ? (
          <ErrorState
            title="Couldn't load statistics"
            message={errorMessage(stats.error)}
            onRetry={() => void stats.refetch()}
          />
        ) : (
          <StatsOverview stats={stats.data} />
        )}
      </section>

      <section aria-labelledby="recent-runs" className="mt-8">
        <h2 id="recent-runs" className="mb-3 text-base font-semibold text-fg">
          Recent runs
        </h2>
        {runs.isPending ? (
          <Skeleton className="h-64 w-full" />
        ) : runs.isError ? (
          <ErrorState
            title="Couldn't load runs"
            message={errorMessage(runs.error)}
            onRetry={() => void runs.refetch()}
          />
        ) : runs.data.length === 0 ? (
          <EmptyState
            icon={<Activity className="size-5" aria-hidden />}
            title="No runs yet"
            description="Runs appear here after you ask the agent a question."
          />
        ) : (
          <RunsTable runs={runs.data} onSelect={setSelectedRun} />
        )}
      </section>
      <RunDetailDrawer runId={selectedRun} onClose={() => setSelectedRun(null)} />
    </PageContainer>
  );
}
