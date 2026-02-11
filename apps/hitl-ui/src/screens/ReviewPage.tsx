import { ArrowLeft, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { Link, useParams } from 'react-router-dom';

import CriterionCard from '../components/CriterionCard';
import PdfViewer from '../components/PdfViewer';
import { Button } from '../components/ui/Button';
import type { ReviewActionRequest } from '../hooks/useReviews';
import {
    useAuditLog,
    useBatchCriteria,
    useBatchList,
    usePdfUrl,
    useReviewAction,
} from '../hooks/useReviews';
import { cn } from '../lib/utils';

const SORT_OPTIONS = [
    { label: 'Confidence', value: 'confidence' },
    { label: 'Type', value: 'criteria_type' },
    { label: 'Status', value: 'review_status' },
] as const;

function formatTimestamp(dateStr: string): string {
    return new Date(dateStr).toLocaleString();
}

export default function ReviewPage() {
    const { batchId } = useParams<{ batchId: string }>();
    const [sortBy, setSortBy] = useState('confidence');
    const [sortOrder, setSortOrder] = useState('asc');
    const [auditOpen, setAuditOpen] = useState(false);

    // Fetch batch criteria
    const {
        data: criteria,
        isLoading: criteriaLoading,
        error: criteriaError,
    } = useBatchCriteria(batchId ?? '', sortBy, sortOrder);

    // Fetch batch info (find batch from list)
    const { data: batchListData } = useBatchList(1, 100);
    const batch = batchListData?.items.find((b) => b.id === batchId);

    // Fetch PDF URL using protocol_id from batch
    const { data: pdfData, isLoading: pdfLoading } = usePdfUrl(batch?.protocol_id ?? '');

    // Review action mutation
    const reviewAction = useReviewAction();

    // Audit log
    const { data: auditData } = useAuditLog(1, 20, 'criteria');

    function handleAction(criterionId: string, action: ReviewActionRequest) {
        reviewAction.mutate({ criteriaId: criterionId, ...action });
    }

    const reviewedCount = criteria?.filter((c) => c.review_status !== null).length ?? 0;
    const totalCount = criteria?.length ?? 0;
    const progressPercent = totalCount > 0 ? Math.round((reviewedCount / totalCount) * 100) : 0;

    if (criteriaLoading) {
        return (
            <div className="flex items-center justify-center h-screen">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (criteriaError) {
        return (
            <div className="container mx-auto p-6">
                <Link
                    to="/reviews"
                    className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-6"
                >
                    <ArrowLeft className="h-4 w-4 mr-1" />
                    Back to Review Queue
                </Link>
                <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6 text-center">
                    <p className="text-destructive">
                        Failed to load criteria: {criteriaError.message}
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="h-screen flex flex-col">
            <PanelGroup direction="horizontal" className="flex-1">
                {/* Left panel: PDF Viewer */}
                <Panel defaultSize={50} minSize={30}>
                    <div className="h-full flex flex-col">
                        <div className="px-4 py-2 border-b bg-card">
                            <h2 className="text-sm font-medium text-muted-foreground">
                                Protocol PDF
                            </h2>
                        </div>
                        <div className="flex-1 overflow-hidden">
                            {pdfLoading ? (
                                <div className="flex items-center justify-center h-full">
                                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                                </div>
                            ) : pdfData?.url ? (
                                <PdfViewer url={pdfData.url} />
                            ) : (
                                <div className="flex items-center justify-center h-full">
                                    <p className="text-muted-foreground">No PDF available</p>
                                </div>
                            )}
                        </div>
                    </div>
                </Panel>

                <PanelResizeHandle className="w-1 bg-border hover:bg-primary/20 transition-colors" />

                {/* Right panel: Criteria Review */}
                <Panel defaultSize={50} minSize={30}>
                    <div className="h-full overflow-auto">
                        {/* Header */}
                        <div className="sticky top-0 z-10 bg-card border-b px-4 py-3 space-y-3">
                            <div className="flex items-center justify-between">
                                <Link
                                    to="/reviews"
                                    className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
                                >
                                    <ArrowLeft className="h-4 w-4 mr-1" />
                                    Review Queue
                                </Link>
                                {batch && (
                                    <span
                                        className={cn(
                                            'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
                                            batch.status === 'approved'
                                                ? 'bg-green-100 text-green-800'
                                                : batch.status === 'rejected'
                                                  ? 'bg-red-100 text-red-800'
                                                  : batch.status === 'in_progress'
                                                    ? 'bg-blue-100 text-blue-800'
                                                    : 'bg-yellow-100 text-yellow-800'
                                        )}
                                    >
                                        {batch.status.replace(/_/g, ' ')}
                                    </span>
                                )}
                            </div>

                            {/* Progress bar */}
                            <div>
                                <div className="flex items-center justify-between mb-1">
                                    <span className="text-sm text-muted-foreground">
                                        {reviewedCount}/{totalCount} criteria reviewed
                                    </span>
                                    <span className="text-sm font-medium">{progressPercent}%</span>
                                </div>
                                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                                    <div
                                        className={cn(
                                            'h-full rounded-full transition-all',
                                            progressPercent === 100 ? 'bg-green-500' : 'bg-blue-500'
                                        )}
                                        style={{ width: `${progressPercent}%` }}
                                    />
                                </div>
                            </div>

                            {/* Sort controls */}
                            <div className="flex items-center gap-2">
                                <span className="text-sm text-muted-foreground">Sort by:</span>
                                <select
                                    value={sortBy}
                                    onChange={(e) => setSortBy(e.target.value)}
                                    className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                                >
                                    {SORT_OPTIONS.map((opt) => (
                                        <option key={opt.value} value={opt.value}>
                                            {opt.label}
                                        </option>
                                    ))}
                                </select>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() =>
                                        setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'))
                                    }
                                >
                                    {sortOrder === 'asc' ? (
                                        <ChevronUp className="h-4 w-4" />
                                    ) : (
                                        <ChevronDown className="h-4 w-4" />
                                    )}
                                </Button>
                            </div>
                        </div>

                        {/* Criteria cards */}
                        <div className="p-4 space-y-4">
                            {criteria && criteria.length > 0 ? (
                                criteria.map((criterion) => (
                                    <CriterionCard
                                        key={criterion.id}
                                        criterion={criterion}
                                        onAction={handleAction}
                                        isSubmitting={reviewAction.isPending}
                                    />
                                ))
                            ) : (
                                <div className="text-center py-8">
                                    <p className="text-muted-foreground">
                                        No criteria found for this batch
                                    </p>
                                </div>
                            )}

                            {/* Audit trail section */}
                            <div className="mt-6 border-t pt-4">
                                <button
                                    type="button"
                                    className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                                    onClick={() => setAuditOpen(!auditOpen)}
                                >
                                    {auditOpen ? (
                                        <ChevronUp className="h-4 w-4" />
                                    ) : (
                                        <ChevronDown className="h-4 w-4" />
                                    )}
                                    Audit Trail
                                </button>

                                {auditOpen && auditData && (
                                    <div className="mt-3 space-y-2">
                                        {auditData.items.length === 0 ? (
                                            <p className="text-sm text-muted-foreground">
                                                No audit entries yet
                                            </p>
                                        ) : (
                                            auditData.items.map((entry) => (
                                                <div
                                                    key={entry.id}
                                                    className="flex items-start gap-3 rounded-md border bg-muted/30 px-3 py-2 text-xs"
                                                >
                                                    <span className="text-muted-foreground whitespace-nowrap">
                                                        {formatTimestamp(entry.created_at)}
                                                    </span>
                                                    <span className="font-medium">
                                                        {entry.event_type}
                                                    </span>
                                                    {entry.actor_id && (
                                                        <span className="text-muted-foreground">
                                                            by {entry.actor_id}
                                                        </span>
                                                    )}
                                                    {entry.target_type && entry.target_id && (
                                                        <span className="text-muted-foreground">
                                                            on {entry.target_type}:
                                                            {entry.target_id.slice(0, 8)}
                                                        </span>
                                                    )}
                                                </div>
                                            ))
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </Panel>
            </PanelGroup>
        </div>
    );
}
