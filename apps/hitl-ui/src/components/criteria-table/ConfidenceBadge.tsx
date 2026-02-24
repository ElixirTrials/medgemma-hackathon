import { cn } from '../../lib/utils';

interface ConfidenceBadgeProps {
    value: number;
    className?: string;
}

export function ConfidenceBadge({ value, className }: ConfidenceBadgeProps) {
    const pct = Math.round(value * 100);

    const colorClass =
        value >= 0.7
            ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
            : value >= 0.5
              ? 'bg-amber-100 text-amber-800 border-amber-300'
              : 'bg-red-100 text-red-800 border-red-300';

    const barColor = value >= 0.7 ? 'bg-emerald-500' : value >= 0.5 ? 'bg-amber-500' : 'bg-red-500';

    return (
        <div className={cn('inline-flex items-center gap-1.5', className)}>
            <span
                className={cn(
                    'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold tabular-nums',
                    colorClass
                )}
            >
                {pct}%
            </span>
            <div className="w-12 h-1.5 rounded-full bg-muted overflow-hidden">
                <div
                    className={cn(
                        'h-full rounded-full transition-all duration-500 ease-out',
                        barColor
                    )}
                    style={{ width: `${pct}%` }}
                />
            </div>
        </div>
    );
}
