import * as Collapsible from '@radix-ui/react-collapsible';
import { CheckCircle, ChevronDown, ChevronRight, Edit, XCircle } from 'lucide-react';
import { useState } from 'react';

import { useBatchMetrics } from '../hooks/useCorpus';
import { cn } from '../lib/utils';

interface AgreementMetricsProps {
    batchId: string;
}

function formatBreakdownKey(key: string): string {
    const map: Record<string, string> = {
        text_edits: 'Text Edits',
        structured_edits: 'Structured Edits',
        field_mapping_changes: 'Field Mapping Changes',
    };
    return (
        map[key] ??
        key
            .replace(/_/g, ' ')
            .replace(/\b\w/g, (c) => c.toUpperCase())
    );
}

interface MetricCardProps {
    label: string;
    count: number;
    pct: number;
    icon: React.ReactNode;
    colorClass: string;
}

function MetricCard({ label, count, pct, icon, colorClass }: MetricCardProps) {
    return (
        <div className={cn('rounded-lg border p-4', colorClass)}>
            <div className="flex items-center gap-2 mb-1">
                {icon}
                <span className="text-sm font-medium">{label}</span>
            </div>
            <div className="text-2xl font-bold">{count}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{pct.toFixed(1)}%</div>
        </div>
    );
}

export function AgreementMetrics({ batchId }: AgreementMetricsProps) {
    const { data: metrics, isLoading, error } = useBatchMetrics(batchId);
    const [breakdownOpen, setBreakdownOpen] = useState(false);
    const [detailsOpen, setDetailsOpen] = useState<Record<string, boolean>>({});

    if (isLoading) {
        return (
            <div className="rounded-lg border bg-card p-4 shadow-sm">
                <p className="text-sm text-muted-foreground animate-pulse">Loading metrics...</p>
            </div>
        );
    }

    if (error || !metrics) {
        return (
            <div className="rounded-lg border bg-card p-4 shadow-sm">
                <p className="text-sm text-muted-foreground">Metrics unavailable</p>
            </div>
        );
    }

    const toggleDetail = (key: string) => {
        setDetailsOpen((prev) => ({ ...prev, [key]: !prev[key] }));
    };

    const approvedCriteria = metrics.per_criterion_details.filter(
        (c) => c.review_status === 'approved'
    );
    const rejectedCriteria = metrics.per_criterion_details.filter(
        (c) => c.review_status === 'rejected'
    );
    const modifiedCriteria = metrics.per_criterion_details.filter(
        (c) => c.review_status === 'modified'
    );

    const breakdownKeys = Object.keys(metrics.modification_breakdown);

    return (
        <div className="rounded-lg border bg-card p-4 shadow-sm space-y-4">
            {/* Layer 1: Summary stats (always visible) */}
            <div className="grid grid-cols-3 gap-3">
                <MetricCard
                    label="Approved"
                    count={metrics.approved}
                    pct={metrics.approved_pct}
                    icon={<CheckCircle className="h-4 w-4 text-green-600" />}
                    colorClass="border-green-200 bg-green-50"
                />
                <MetricCard
                    label="Rejected"
                    count={metrics.rejected}
                    pct={metrics.rejected_pct}
                    icon={<XCircle className="h-4 w-4 text-red-600" />}
                    colorClass="border-red-200 bg-red-50"
                />
                <MetricCard
                    label="Modified"
                    count={metrics.modified}
                    pct={metrics.modified_pct}
                    icon={<Edit className="h-4 w-4 text-yellow-600" />}
                    colorClass="border-yellow-200 bg-yellow-50"
                />
            </div>
            {metrics.pending > 0 && (
                <p className="text-xs text-muted-foreground">
                    Pending review: {metrics.pending} of {metrics.total_criteria}
                </p>
            )}

            {/* Layer 2: Modification breakdown (Radix Collapsible) */}
            {breakdownKeys.length > 0 && (
                <Collapsible.Root open={breakdownOpen} onOpenChange={setBreakdownOpen}>
                    <Collapsible.Trigger asChild>
                        <button
                            type="button"
                            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                        >
                            {breakdownOpen ? (
                                <ChevronDown className="h-4 w-4" />
                            ) : (
                                <ChevronRight className="h-4 w-4" />
                            )}
                            {breakdownOpen ? 'Hide breakdown' : 'Show modification breakdown'}
                        </button>
                    </Collapsible.Trigger>
                    <Collapsible.Content className="mt-2 space-y-2">
                        <div className="rounded-lg border bg-background p-3 space-y-1.5">
                            {breakdownKeys.map((key) => (
                                <div key={key} className="flex items-center justify-between text-sm">
                                    <span className="text-muted-foreground">{formatBreakdownKey(key)}</span>
                                    <span className="font-medium">{metrics.modification_breakdown[key]}</span>
                                </div>
                            ))}
                        </div>

                        {/* Layer 3: Per-criterion details (nested Collapsibles) */}
                        <div className="space-y-2 pt-1">
                            {[
                                { label: 'Approved criteria', items: approvedCriteria, colorClass: 'border-l-green-400' },
                                { label: 'Rejected criteria', items: rejectedCriteria, colorClass: 'border-l-red-400' },
                                { label: 'Modified criteria', items: modifiedCriteria, colorClass: 'border-l-yellow-400' },
                            ]
                                .filter(({ items }) => items.length > 0)
                                .map(({ label, items, colorClass }) => (
                                    <Collapsible.Root
                                        key={label}
                                        open={detailsOpen[label] ?? false}
                                        onOpenChange={() => toggleDetail(label)}
                                    >
                                        <Collapsible.Trigger asChild>
                                            <button
                                                type="button"
                                                className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
                                            >
                                                {detailsOpen[label] ? (
                                                    <ChevronDown className="h-3.5 w-3.5" />
                                                ) : (
                                                    <ChevronRight className="h-3.5 w-3.5" />
                                                )}
                                                {label} ({items.length})
                                            </button>
                                        </Collapsible.Trigger>
                                        <Collapsible.Content className="mt-1 space-y-1">
                                            {items.map((c) => (
                                                <div
                                                    key={c.criterion_id}
                                                    className={cn(
                                                        'border-l-2 pl-3 py-1 text-xs',
                                                        colorClass
                                                    )}
                                                >
                                                    <span className="text-foreground">
                                                        {c.criterion_text.length > 100
                                                            ? `${c.criterion_text.slice(0, 100)}...`
                                                            : c.criterion_text}
                                                    </span>
                                                    <span className="ml-2 inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700 capitalize">
                                                        {c.criteria_type}
                                                    </span>
                                                </div>
                                            ))}
                                        </Collapsible.Content>
                                    </Collapsible.Root>
                                ))}
                        </div>
                    </Collapsible.Content>
                </Collapsible.Root>
            )}
        </div>
    );
}
