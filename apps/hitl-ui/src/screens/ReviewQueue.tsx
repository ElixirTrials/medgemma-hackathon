import { ArrowLeft, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { Button } from '../components/ui/Button';
import type { CriteriaBatch } from '../hooks/useReviews';
import { useBatchList } from '../hooks/useReviews';
import { cn } from '../lib/utils';

const STATUS_OPTIONS = [
    { label: 'All', value: undefined },
    { label: 'Pending Review', value: 'pending_review' },
    { label: 'In Progress', value: 'in_progress' },
    { label: 'Approved', value: 'approved' },
    { label: 'Rejected', value: 'rejected' },
] as const;

const STATUS_COLORS: Record<string, string> = {
    pending_review: 'bg-yellow-100 text-yellow-800',
    in_progress: 'bg-blue-100 text-blue-800',
    approved: 'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
};

function StatusBadge({ status }: { status: string }) {
    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
                STATUS_COLORS[status] ?? 'bg-gray-100 text-gray-800'
            )}
        >
            {status.replace(/_/g, ' ')}
        </span>
    );
}

function ProgressBar({ reviewed, total }: { reviewed: number; total: number }) {
    const percentage = total > 0 ? Math.round((reviewed / total) * 100) : 0;

    return (
        <div className="flex items-center gap-2">
            <div className="h-2 w-16 rounded-full bg-muted overflow-hidden">
                <div
                    className={cn(
                        'h-full rounded-full transition-all',
                        percentage === 100 ? 'bg-green-500' : 'bg-blue-500'
                    )}
                    style={{ width: `${percentage}%` }}
                />
            </div>
            <span className="text-sm text-muted-foreground">
                {reviewed}/{total}
            </span>
        </div>
    );
}

function formatRelativeTime(dateStr: string): string {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHr = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHr / 24);

    if (diffSec < 60) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHr < 24) return `${diffHr}h ago`;
    if (diffDay < 30) return `${diffDay}d ago`;
    return date.toLocaleDateString();
}

export default function ReviewQueue() {
    const [page, setPage] = useState(1);
    const [pageSize] = useState(20);
    const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

    const navigate = useNavigate();
    const { data, isLoading, error } = useBatchList(page, pageSize, statusFilter);

    const handleRowClick = (batch: CriteriaBatch) => {
        navigate(`/reviews/${batch.id}`);
    };

    return (
        <div className="container mx-auto p-6">
            {/* Back link */}
            <Link
                to="/"
                className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-6"
            >
                <ArrowLeft className="h-4 w-4 mr-1" />
                Back to Dashboard
            </Link>

            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <h1 className="text-3xl font-bold text-foreground">Review Queue</h1>
            </div>

            {/* Status filter chips */}
            <div className="flex flex-wrap gap-2 mb-6">
                {STATUS_OPTIONS.map((opt) => {
                    const isActive =
                        opt.value === undefined ? !statusFilter : statusFilter === opt.value;
                    return (
                        <button
                            key={opt.label}
                            type="button"
                            className={cn(
                                'rounded-full px-3 py-1 text-sm font-medium transition-colors border',
                                isActive
                                    ? 'bg-primary text-primary-foreground border-primary'
                                    : 'bg-background text-foreground border-input hover:bg-accent'
                            )}
                            onClick={() => {
                                setStatusFilter(opt.value);
                                setPage(1);
                            }}
                        >
                            {opt.label}
                        </button>
                    );
                })}
            </div>

            {/* Loading state */}
            {isLoading && (
                <div className="flex items-center justify-center py-16">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
            )}

            {/* Error state */}
            {error && (
                <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
                    <p className="text-sm text-destructive">
                        Failed to load review queue: {error.message}
                    </p>
                </div>
            )}

            {/* Empty state */}
            {data && data.items.length === 0 && (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                    <p className="text-lg text-muted-foreground">No criteria batches found</p>
                </div>
            )}

            {/* Batch table */}
            {data && data.items.length > 0 && (
                <div className="rounded-lg border bg-card shadow-sm overflow-hidden">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b bg-muted/50">
                                <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
                                    Protocol Title
                                </th>
                                <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
                                    Criteria Count
                                </th>
                                <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
                                    Reviewed
                                </th>
                                <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
                                    Status
                                </th>
                                <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
                                    Created
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.items.map((batch) => (
                                <tr
                                    key={batch.id}
                                    className="border-b last:border-b-0 hover:bg-muted/30 cursor-pointer transition-colors"
                                    onClick={() => handleRowClick(batch)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            handleRowClick(batch);
                                        }
                                    }}
                                    tabIndex={0}
                                >
                                    <td className="px-4 py-3 text-sm font-medium text-foreground">
                                        {batch.protocol_title}
                                    </td>
                                    <td className="px-4 py-3 text-sm text-muted-foreground">
                                        {batch.criteria_count}
                                    </td>
                                    <td className="px-4 py-3">
                                        <ProgressBar
                                            reviewed={batch.reviewed_count}
                                            total={batch.criteria_count}
                                        />
                                    </td>
                                    <td className="px-4 py-3">
                                        <StatusBadge status={batch.status} />
                                    </td>
                                    <td className="px-4 py-3 text-sm text-muted-foreground">
                                        {formatRelativeTime(batch.created_at)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Pagination */}
            {data && data.pages > 1 && (
                <div className="flex items-center justify-between mt-4">
                    <p className="text-sm text-muted-foreground">
                        Page {data.page} of {data.pages} ({data.total} total)
                    </p>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setPage((p) => Math.max(1, p - 1))}
                            disabled={page <= 1}
                        >
                            <ChevronLeft className="h-4 w-4 mr-1" />
                            Previous
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                            disabled={page >= data.pages}
                        >
                            Next
                            <ChevronRight className="h-4 w-4 ml-1" />
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
}
