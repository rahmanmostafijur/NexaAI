import { useId } from 'react';
import { cn } from '@/utils/cn';

export function LogoMark({ className }: { className?: string }) {
  const gradientId = useId();
  return (
    <svg viewBox="0 0 64 64" aria-hidden className={cn('size-8 shrink-0', className)}>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6366f1" />
          <stop offset="1" stopColor="#14b8a6" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill={`url(#${gradientId})`} />
      <path
        d="M19 45V19l26 26V19"
        fill="none"
        stroke="#fff"
        strokeWidth="5.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="45" cy="19" r="4" fill="#fff" />
      <circle cx="19" cy="45" r="4" fill="#fff" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <LogoMark />
      <span className="text-[15px] font-semibold tracking-tight text-fg">
        NexaAI <span className="font-normal text-fg-muted">Agent</span>
      </span>
    </span>
  );
}
