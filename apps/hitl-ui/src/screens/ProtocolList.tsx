import * as AlertDialog from '@radix-ui/react-alert-dialog';
import { Archive, ChevronLeft, ChevronRight, Loader2, RotateCcw } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ProtocolUploadDialog } from '../components/ProtocolUploadDialog';
import { Button } from '../components/ui/Button';
import { useArchiveProtocol, useProtocolList, useRetryProtocol } from '../hooks/useProtocols';
import type { Protocol } from '../hooks/useProtocols';
import { cn } from '../lib/utils';

const STATUS_OPTIONS = [
    'All',
    'uploaded',
    'extracting',
    'extraction_failed',
    'grounding',
    'grounding_failed',
    'pending_review',
    'complete',
    'dead_letter',
] as const;

const STATUS_COLORS: Record<string, string> = {
    uploaded: 'bg-blue-100 text-blue-800',
    extracting: 'bg-yellow-100 text-yellow-800',
    extraction_failed: 'bg-red-100 text-red-800',
    grounding: 'bg-cyan-100 text-cyan-800',
    grounding_failed: 'bg-orange-100 text-orange-800',
    pending_review: 'bg-indigo-100 text-indigo-800',
    complete: 'bg-green-100 text-green-800',
    dead_letter: 'bg-red-200 text-red-900',
    archived: 'bg-gray-100 text-gray-500',
    // Keep legacy statuses for backward compat
    extracted: 'bg-green-100 text-green-800',
    reviewed: 'bg-purple-100 text-purple-800',
};

const STATUS_LABELS: Record<string, string> = {
    uploaded: 'Uploaded',
    extracting: 'Extracting',
    extraction_failed: 'Extraction Failed',
    grounding: 'Grounding',
    grounding_failed: 'Grounding Failed',
    pending_review: 'Pending Review',
    complete: 'Complete',
    dead_letter: 'Dead Letter',
    archived: 'Archived',
    extracted: 'Extracted',
    reviewed: 'Reviewed',
};

function StatusBadge({ status }: { status: string }) {
    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
                STATUS_COLORS[status] ?? 'bg-gray-100 text-gray-800'
            )}
        >
            {STATUS_LABELS[status] ?? status}
        </span>
    );
}

function QualityIndicator({ score }: { score: number | null }) {
    if (score === null) {
        return <span className="text-sm text-muted-foreground">--</span>;
    }

    const percentage = Math.round(score * 100);
    let colorClass = 'text-red-600';
    if (score > 0.7) colorClass = 'text-green-600';
    else if (score >= 0.3) colorClass = 'text-yellow-600';

    return (
        <div className="flex items-center gap-2">
            <div className="h-2 w-16 rounded-full bg-muted overflow-hidden">
                <div
                    className={cn(
                        'h-full rounded-full',
                        score > 0.7 ? 'bg-green-500' : score >= 0.3 ? 'bg-yellow-500' : 'bg-red-500'
                    )}
                    style={{ width: `${percentage}%` }}
                />
            </div>
            <span className={cn('text-sm font-medium', colorClass)}>{percentage}%</span>
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

function RetryInlineButton({ protocolId }: { protocolId: string }) {
    const retryMutation = useRetryProtocol();
    return (
        <Button
            variant="outline"
            size="sm"
            disabled={retryMutation.isPending}
            onClick={(e) => {
                e.stopPropagation();
                retryMutation.mutate(protocolId);
            }}
        >
            <RotateCcw className="h-3.5 w-3.5 mr-1" />
            Retry
        </Button>
    );
}

function ArchiveInlineButton({ protocolId }: { protocolId: string }) {
    const archiveMutation = useArchiveProtocol();
    return (
        <AlertDialog.Root>
            <AlertDialog.Trigger asChild>
                <Button variant="outline" size="sm" onClick={(e) => e.stopPropagation()}>
                    <Archive className="h-3.5 w-3.5 mr-1" />
                    Archive
                </Button>
            </AlertDialog.Trigger>
            <AlertDialog.Portal>
                <AlertDialog.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
                <AlertDialog.Content className="fixed left-[50%] top-[50%] z-50 grid w-full max-w-sm translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border bg-background p-6 shadow-lg">
                    <AlertDialog.Title className="text-lg font-semibold">
                        Archive this protocol?
                    </AlertDialog.Title>
                    <AlertDialog.Description className="text-sm text-muted-foreground">
                        It will be hidden from the default list view. You can show it again using
                        the &quot;Show Archived&quot; filter.
                    </AlertDialog.Description>
                    <div className="flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2">
                        <AlertDialog.Cancel asChild>
                            <Button variant="outline">Cancel</Button>
                        </AlertDialog.Cancel>
                        <AlertDialog.Action asChild>
                            <Button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    archiveMutation.mutate(protocolId);
                                }}
                                disabled={archiveMutation.isPending}
                            >
                                Archive
                            </Button>
                        </AlertDialog.Action>
                    </div>
                </AlertDialog.Content>
            </AlertDialog.Portal>
        </AlertDialog.Root>
    );
}

export default function ProtocolList() {
    const [page, setPage] = useState(1);
    const [pageSize] = useState(20);
    const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
    const [uploadOpen, setUploadOpen] = useState(false);
    const [showArchived, setShowArchived] = useState(false);

    const navigate = useNavigate();
    const effectiveStatus = showArchived ? 'archived' : statusFilter;
    const { data, isLoading, error } = useProtocolList(
        page,
        pageSize,
        effectiveStatus,
        !showArchived
    );

    const handleRowClick = (protocol: Protocol) => {
        navigate(`/protocols/${protocol.id}`);
    };

    return (
        <div className="container mx-auto p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <h1 className="text-3xl font-bold text-foreground">Protocols</h1>
                <Button onClick={() => setUploadOpen(true)}>Upload Protocol</Button>
            </div>

            {/* Status filter chips */}
            <div className="flex flex-wrap gap-2 mb-6">
                {STATUS_OPTIONS.map((opt) => {
                    const isActive = opt === 'All' ? !statusFilter : statusFilter === opt;
                    return (
                        <button
                            key={opt}
                            type="button"
                            className={cn(
                                'rounded-full px-3 py-1 text-sm font-medium transition-colors border',
                                isActive && !showArchived
                                    ? 'bg-primary text-primary-foreground border-primary'
                                    : 'bg-background text-foreground border-input hover:bg-accent'
                            )}
                            onClick={() => {
                                setShowArchived(false);
                                setStatusFilter(opt === 'All' ? undefined : opt);
                                setPage(1);
                            }}
                        >
                            {opt === 'All' ? 'All' : (STATUS_LABELS[opt] ?? opt)}
                        </button>
                    );
                })}
                <button
                    type="button"
                    className={cn(
                        'rounded-full px-3 py-1 text-sm font-medium transition-colors border',
                        showArchived
                            ? 'bg-primary text-primary-foreground border-primary'
                            : 'bg-background text-foreground border-input hover:bg-accent'
                    )}
                    onClick={() => {
                        setShowArchived((v) => !v);
                        setPage(1);
                    }}
                >
                    {showArchived ? 'Hide Archived' : 'Show Archived'}
                </button>
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
                        Failed to load protocols: {error.message}
                    </p>
                </div>
            )}

            {/* Empty state */}
            {data && data.items.length === 0 && (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                    <p className="text-lg text-muted-foreground mb-4">
                        {statusFilter
                            ? `No ${statusFilter} protocols found.`
                            : 'No protocols uploaded yet. Click Upload Protocol to get started.'}
                    </p>
                    <Button onClick={() => setUploadOpen(true)}>Upload Protocol</Button>
                </div>
            )}

            {/* Protocol table */}
            {data && data.items.length > 0 && (
                <div className="rounded-lg border bg-card shadow-sm overflow-hidden">
                    <table className="w-full">
                        <thead>
                            <tr className="border-b bg-muted/50">
                                <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
                                    Title
                                </th>
                                <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
                                    Status
                                </th>
                                <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
                                    Pages
                                </th>
                                <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
                                    Quality Score
                                </th>
                                <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
                                    Uploaded
                                </th>
                                <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
                                    Actions
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.items.map((protocol) => {
                                const isActionable = [
                                    'dead_letter',
                                    'extraction_failed',
                                    'grounding_failed',
                                ].includes(protocol.status);
                                return (
                                    <tr
                                        key={protocol.id}
                                        className={cn(
                                            'border-b last:border-b-0 cursor-pointer transition-colors',
                                            isActionable
                                                ? 'bg-red-50/50 hover:bg-red-100/50 border-l-2 border-l-red-400'
                                                : 'hover:bg-muted/30'
                                        )}
                                        onClick={() => handleRowClick(protocol)}
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter' || e.key === ' ') {
                                                handleRowClick(protocol);
                                            }
                                        }}
                                        tabIndex={0}
                                    >
                                        <td className="px-4 py-3 text-sm font-medium text-foreground">
                                            <span className="flex items-center gap-1.5">
                                                {protocol.title}
                                                {(protocol.version_count ?? 1) > 1 && (
                                                    <span className="inline-flex items-center rounded-full bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
                                                        v{protocol.version_count}
                                                    </span>
                                                )}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3">
                                            <StatusBadge status={protocol.status} />
                                        </td>
                                        <td className="px-4 py-3 text-sm text-muted-foreground">
                                            {protocol.page_count ?? '--'}
                                        </td>
                                        <td className="px-4 py-3">
                                            <QualityIndicator score={protocol.quality_score} />
                                        </td>
                                        <td className="px-4 py-3 text-sm text-muted-foreground">
                                            {formatRelativeTime(protocol.created_at)}
                                        </td>
                                        <td
                                            className="px-4 py-3"
                                            onClick={(e) => e.stopPropagation()}
                                            onKeyDown={(e) => e.stopPropagation()}
                                        >
                                            {isActionable && (
                                                <div className="flex items-center gap-1.5">
                                                    <RetryInlineButton protocolId={protocol.id} />
                                                    <ArchiveInlineButton protocolId={protocol.id} />
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                );
                            })}
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

            {/* Upload Dialog */}
            <ProtocolUploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
        </div>
    );
}
