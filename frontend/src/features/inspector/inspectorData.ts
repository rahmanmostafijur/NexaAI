import type { ChatMessage } from '@/features/chat/types';
import type { PlanStep, Route, SqlResult, Source, StageTiming } from '@/types/api';

export interface InspectorData {
  route: Route | null;
  confidence: number | null;
  reason: string | null;
  language: string | null;
  standaloneQuery: string | null;
  plan: PlanStep[];
  sql: SqlResult[];
  sources: Source[];
  timings: { total_ms: number; stages: StageTiming[] } | null;
  warnings: string[];
  grounded: boolean | null;
  streaming: boolean;
}

const LANGUAGE_LABELS: Record<string, string> = {
  en: 'English',
  bn: 'Bengali',
  banglish: 'Banglish',
  mixed: 'Mixed',
};

export function languageLabel(value: string): string {
  return LANGUAGE_LABELS[value.toLowerCase()] ?? value;
}

/** Normalises final `details` or live stream state into one inspector view model. */
export function inspectorDataFor(message: ChatMessage): InspectorData {
  const details = message.details;
  if (details) {
    return {
      route: details.route,
      confidence: details.confidence,
      reason: details.reason,
      language: languageLabel(details.language),
      standaloneQuery: null,
      plan: details.plan,
      sql: details.sql,
      sources: details.sources,
      timings: details.timings,
      warnings: details.warnings,
      grounded: details.grounded,
      streaming: false,
    };
  }
  const live = message.live;
  const analysis = live?.analysis ?? null;
  return {
    route: analysis?.route ?? null,
    confidence: analysis?.confidence ?? null,
    reason: analysis?.reason ?? null,
    language: analysis ? analysis.language.label || languageLabel(analysis.language.code) : null,
    standaloneQuery: analysis?.standalone_query ?? null,
    plan: live?.plan ?? [],
    sql: live?.sql ?? [],
    sources: live?.sources ?? [],
    timings: null,
    warnings: [],
    grounded: null,
    streaming: live?.streaming ?? false,
  };
}
