const numberFormatter = new Intl.NumberFormat('en-US');
const bdtFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'BDT',
  currencyDisplay: 'narrowSymbol',
  maximumFractionDigits: 2,
});

export function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

/** Bangladeshi Taka with the ৳ symbol and South Asian digit grouping, e.g. ৳12,34,567.50 */
export function formatBDT(value: number): string {
  return bdtFormatter.format(value).replace(/^BDT\s?/, '৳');
}

/** 0..1 → "87%" */
export function formatPercent(ratio: number, fractionDigits = 0): string {
  const clamped = Math.min(Math.max(ratio, 0), 1);
  return `${(clamped * 100).toFixed(fractionDigits)}%`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB'] as const;

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '—';
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || value >= 100 ? 0 : 1;
  return `${value.toFixed(digits)} ${BYTE_UNITS[unit]}`;
}

const relativeFormatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
const RELATIVE_STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 31_536_000],
  ['month', 2_592_000],
  ['week', 604_800],
  ['day', 86_400],
  ['hour', 3_600],
  ['minute', 60],
];

export function formatRelativeTime(iso: string, now: number = Date.now()): string {
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return '—';
  const diffSeconds = Math.round((time - now) / 1000);
  const abs = Math.abs(diffSeconds);
  if (abs < 45) return 'just now';
  for (const [unit, seconds] of RELATIVE_STEPS) {
    if (abs >= seconds) return relativeFormatter.format(Math.round(diffSeconds / seconds), unit);
  }
  return relativeFormatter.format(Math.round(diffSeconds / 60), 'minute');
}

const dateTimeFormatter = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'medium',
  timeStyle: 'short',
});

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '—' : dateTimeFormatter.format(date);
}
