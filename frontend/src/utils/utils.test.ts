import { describe, expect, it } from 'vitest';
import { stripCitations } from './citations';
import {
  formatBDT,
  formatBytes,
  formatDuration,
  formatPercent,
  formatRelativeTime,
} from './format';
import { detectScript, langFor } from './script';

describe('format helpers', () => {
  it('formats Bangladeshi Taka with the ৳ symbol and lakh grouping', () => {
    expect(formatBDT(1234567.5)).toBe('৳12,34,567.50');
    expect(formatBDT(0)).toBe('৳0.00');
  });

  it('formats bytes, durations and percentages', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatDuration(850)).toBe('850 ms');
    expect(formatDuration(1500)).toBe('1.50 s');
    expect(formatDuration(null)).toBe('—');
    expect(formatPercent(0.873)).toBe('87%');
    expect(formatPercent(3)).toBe('100%');
  });

  it('formats relative times', () => {
    const now = Date.parse('2026-01-01T12:00:00Z');
    expect(formatRelativeTime('2026-01-01T11:59:50Z', now)).toBe('just now');
    expect(formatRelativeTime('2026-01-01T09:00:00Z', now)).toBe('3 hours ago');
    expect(formatRelativeTime('not a date', now)).toBe('—');
  });
});

describe('script detection', () => {
  it('detects Bengali characters in the U+0980–U+09FF block', () => {
    expect(detectScript('গত মাসে')).toBe('bengali');
    expect(detectScript('Kon product beshi sell hoise')).toBe('latin');
    expect(langFor('mixed ভাষা text')).toBe('bn');
    expect(langFor('English')).toBeUndefined();
  });
});

describe('stripCitations', () => {
  it('removes markers and tidies punctuation', () => {
    expect(stripCitations('Revenue grew [DB1]. Returns take 7 days [S1][S2].')).toBe(
      'Revenue grew. Returns take 7 days.',
    );
  });
});
