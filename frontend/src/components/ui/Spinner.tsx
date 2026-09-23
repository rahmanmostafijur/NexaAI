import { cn } from '@/utils/cn';

const SIZES = { sm: 'size-3.5 border-[1.5px]', md: 'size-5 border-2', lg: 'size-8 border-2' };

export function Spinner({
  size = 'md',
  className,
  label,
}: {
  size?: keyof typeof SIZES;
  className?: string;
  label?: string;
}) {
  return (
    <span
      role={label ? 'status' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn(
        'inline-block shrink-0 animate-spin rounded-full border-current border-r-transparent opacity-80',
        SIZES[size],
        className,
      )}
    />
  );
}
