import { useState } from 'react';

import { useAllProtocolBatches } from '../hooks/useCorpus';
import { cn } from '../lib/utils';
import { BatchCompareView } from './BatchCompareView';
import { Button } from './ui/Button';

interface BatchTimelineProps {
    protocolId: string;
}

const BATCH_STATUS_COLORS: Record<string, string> = {
    pending_review: 'bg-indigo-100 text-indigo-800',
    in_progress: 'bg-blue-100 text-blue-800',
    approved: 'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
    reviewed: 'bg-purple-100 text-purple-800',
    complete: 'bg-green-100 text-green-800',
};

const BATCH_STATUS_LABELS: Record<string, string> = {
    pending_review: 'Pending Review',
    in_progress: 'In Progress',
    approved: 'Approved',
    rejected: 'Rejected',
    reviewed: 'Reviewed',
    complete: 'Complete',
};

export function BatchTimeline({ protocolId }: BatchTimelineProps) {
    const { data: batches, isLoading, error } = useAllProtocolBatches(protocolId);
    const [selectedIds, setSelectedIds] = useState<string[]>([]);
    const [showCompare, setShowCompare] = useState(false);

    if (isLoading) {
        return (
            <div className="space-y-2">
                {[1, 2].map((i) => (
                    <div key={i} className="h-20 rounded-lg bg-muted animate-pulse" />
                ))}
            </div>
        );
    }

    if (error || !batches) {
        return <p className="text-sm text-muted-foreground">Could not load batch history.</p>;
    }

    if (batches.length === 0) {
        return <p className="text-sm text-muted-foreground">No batches yet.</p>;
    }

    const toggleSelect = (id: string) => {
        setSelectedIds((prev) => {
            if (prev.includes(id)) {
                return prev.filter((x) => x !== id);
            }
            if (prev.length >= 2) {
                // Replace the oldest selected with the new one
                return [prev[1], id];
            }
            return [...prev, id];
        });
        // Reset comparison view when selection changes
        setShowCompare(false);
    };

    const handleCompare = () => {
        if (selectedIds.length === 2) {
            setShowCompare(true);
        }
    };

    return (
        <div className="space-y-3">
            <div className="space-y-2">
                {batches.map((batch) => {
                    const isSelected = selectedIds.includes(batch.id);
                    const statusColor =
                        BATCH_STATUS_COLORS[batch.status] ?? 'bg-gray-100 text-gray-600';
                    const statusLabel = BATCH_STATUS_LABELS[batch.status] ?? batch.status;

                    return (
                        <div
                            key={batch.id}
                            className={cn(
                                'rounded-lg border bg-card p-3 flex items-start gap-3',
                                isSelected && 'ring-2 ring-primary',
                                batch.is_archived && 'opacity-70'
                            )}
                        >
                            <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => toggleSelect(batch.id)}
                                className="mt-1 h-4 w-4 rounded border-gray-300 cursor-pointer shrink-0"
                                aria-label={`Select batch from ${new Date(batch.created_at).toLocaleDateString()}`}
                            />
                            <div className="flex-1 min-w-0">
                                <div className="flex flex-wrap items-center gap-2 mb-1">
                                    <span className="text-sm font-medium">
                                        {new Date(batch.created_at).toLocaleString()}
                                    </span>
                                    <span
                                        className={cn(
                                            'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                                            statusColor
                                        )}
                                    >
                                        {statusLabel}
                                    </span>
                                    {batch.is_archived && (
                                        <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                                            Archived
                                        </span>
                                    )}
                                </div>
                                <div className="text-xs text-muted-foreground">
                                    {batch.reviewed_count} / {batch.criteria_count} criteria
                                    reviewed
                                    {batch.extraction_model && (
                                        <span className="ml-2 font-mono">
                                            {batch.extraction_model}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Compare button */}
            <div className="flex items-center gap-2">
                <Button
                    size="sm"
                    variant="outline"
                    disabled={selectedIds.length !== 2}
                    onClick={handleCompare}
                >
                    Compare Selected ({selectedIds.length}/2)
                </Button>
                {selectedIds.length === 2 && showCompare && (
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                            setShowCompare(false);
                            setSelectedIds([]);
                        }}
                    >
                        Clear
                    </Button>
                )}
            </div>

            {/* Comparison view — only loads when user clicks Compare */}
            {showCompare && selectedIds.length === 2 && (
                <BatchCompareView batchA={selectedIds[0]} batchB={selectedIds[1]} />
            )}
        </div>
    );
}
