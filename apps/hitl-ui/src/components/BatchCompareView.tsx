import { useBatchCompare } from '../hooks/useCorpus';
import { cn } from '../lib/utils';

interface BatchCompareViewProps {
    batchA: string;
    batchB: string;
}

const STATUS_CONFIG = {
    added: {
        label: 'Added',
        statColor: 'bg-green-100 text-green-800',
        borderColor: 'border-l-green-500',
    },
    removed: {
        label: 'Removed',
        statColor: 'bg-red-100 text-red-800',
        borderColor: 'border-l-red-500',
    },
    changed: {
        label: 'Changed',
        statColor: 'bg-yellow-100 text-yellow-800',
        borderColor: 'border-l-yellow-500',
    },
    unchanged: {
        label: 'Unchanged',
        statColor: 'bg-gray-100 text-gray-600',
        borderColor: 'border-l-gray-300',
    },
} as const;

function getCriterionText(criterion: Record<string, unknown> | null): string {
    if (!criterion) return '';
    return (criterion.text as string) ?? '';
}

export function BatchCompareView({ batchA, batchB }: BatchCompareViewProps) {
    const { data, isLoading, error } = useBatchCompare(batchA, batchB);

    if (isLoading) {
        return (
            <div className="rounded-lg border bg-card p-4 shadow-sm space-y-3">
                <div className="h-16 rounded bg-muted animate-pulse" />
                <div className="space-y-2">
                    {[1, 2, 3].map((i) => (
                        <div key={i} className="h-12 rounded bg-muted animate-pulse" />
                    ))}
                </div>
            </div>
        );
    }

    if (error || !data) {
        return (
            <div className="rounded-lg border bg-card p-4 shadow-sm">
                <p className="text-sm text-muted-foreground">Could not load comparison data.</p>
            </div>
        );
    }

    return (
        <div className="rounded-lg border bg-card p-4 shadow-sm space-y-4">
            {/* Aggregate stats bar */}
            <div className="grid grid-cols-4 gap-2">
                {(['added', 'removed', 'changed', 'unchanged'] as const).map((key) => (
                    <div
                        key={key}
                        className={cn(
                            'rounded-lg border p-3 text-center',
                            STATUS_CONFIG[key].statColor
                        )}
                    >
                        <div className="text-xl font-bold">{data[key]}</div>
                        <div className="text-xs font-medium capitalize">
                            {STATUS_CONFIG[key].label}
                        </div>
                    </div>
                ))}
            </div>

            {/* Per-criterion rows */}
            <div className="space-y-2">
                {data.rows
                    .filter((row) => row.status !== 'unchanged')
                    .concat(data.rows.filter((row) => row.status === 'unchanged'))
                    .map((row) => {
                        const config = STATUS_CONFIG[row.status];
                        const textA = getCriterionText(row.batch_a_criterion);
                        const textB = getCriterionText(row.batch_b_criterion);
                        const rowKey = String(
                            row.batch_a_criterion?.id ??
                                row.batch_b_criterion?.id ??
                                `${row.status}-${textA ?? textB}`
                        );

                        return (
                            <div
                                key={rowKey}
                                className={cn(
                                    'border-l-4 pl-3 py-2 text-sm rounded-r-lg border border-l-0',
                                    config.borderColor
                                )}
                            >
                                {row.status === 'added' && (
                                    <p className="text-green-800">{textB}</p>
                                )}
                                {row.status === 'removed' && (
                                    <p className="text-red-800">{textA}</p>
                                )}
                                {row.status === 'changed' && (
                                    <div className="grid grid-cols-2 gap-3">
                                        <div>
                                            <p className="text-xs font-medium text-muted-foreground mb-1">
                                                Batch A
                                            </p>
                                            <p className="text-foreground">{textA}</p>
                                        </div>
                                        <div>
                                            <p className="text-xs font-medium text-muted-foreground mb-1">
                                                Batch B
                                            </p>
                                            <p className="text-foreground">{textB}</p>
                                        </div>
                                        {row.match_score !== null && (
                                            <div className="col-span-2">
                                                <span className="inline-flex items-center rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
                                                    Match: {row.match_score.toFixed(0)}%
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                )}
                                {row.status === 'unchanged' && (
                                    <div className="flex items-center gap-2">
                                        <p className="text-muted-foreground flex-1">{textA}</p>
                                        {row.match_score !== null && (
                                            <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 shrink-0">
                                                {row.match_score.toFixed(0)}%
                                            </span>
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })}
            </div>
        </div>
    );
}
