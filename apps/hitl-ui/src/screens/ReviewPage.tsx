import { ArrowLeft, ChevronDown, ChevronUp, Loader2, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { Link, useParams } from 'react-router-dom';
import { useDebounce } from 'use-debounce';

import * as Tabs from '@radix-ui/react-tabs';
import CriterionCard from '../components/CriterionCard';
import EntityCard from '../components/EntityCard';
import PdfViewer from '../components/PdfViewer';
import type { EntityActionRequest, EntityResponse } from '../hooks/useEntities';
import { useEntityAction, useEntityListByBatch } from '../hooks/useEntities';
import type { Criterion, ReviewActionRequest } from '../hooks/useReviews';
import {
    useAuditLog,
    useBatchCriteria,
    useBatchList,
    usePdfUrl,
    useReviewAction,
} from '../hooks/useReviews';
import { cn } from '../lib/utils';

function formatTimestamp(dateStr: string): string {
    return new Date(dateStr).toLocaleString();
}

export default function ReviewPage() {
    const { batchId } = useParams<{ batchId: string }>();
    const [auditOpen, setAuditOpen] = useState(false);
    const [activeTab, setActiveTab] = useState('criteria');
    const [activeCriterion, setActiveCriterion] = useState<Criterion | null>(null);

    // Filter state
    const [searchText, setSearchText] = useState('');
    const [statusFilter, setStatusFilter] = useState<string>('all');
    const [typeFilter, setTypeFilter] = useState<string>('all');
    const [confidenceFilter, setConfidenceFilter] = useState<string>('all');
    const [debouncedSearch] = useDebounce(searchText, 300);

    // Fetch batch criteria
    const {
        data: criteria,
        isLoading: criteriaLoading,
        error: criteriaError,
    } = useBatchCriteria(batchId ?? '', 'confidence', 'asc');

    // Fetch batch info (find batch from list)
    const { data: batchListData } = useBatchList(1, 100);
    const batch = batchListData?.items.find((b) => b.id === batchId);

    // Fetch PDF URL using protocol_id from batch
    const { data: pdfData, isLoading: pdfLoading } = usePdfUrl(batch?.protocol_id ?? '');

    // Review action mutation
    const reviewAction = useReviewAction();

    // Entity data
    const { data: entities } = useEntityListByBatch(batchId ?? '');
    const entityAction = useEntityAction();

    // Audit log
    const { data: auditData } = useAuditLog(1, 20, 'criteria');

    function handleAction(criterionId: string, action: ReviewActionRequest) {
        reviewAction.mutate({ criteriaId: criterionId, ...action });
    }

    function handleEntityAction(entityId: string, action: EntityActionRequest) {
        entityAction.mutate({ entityId, ...action });
    }

    function handleCriterionClick(criterion: Criterion) {
        // Toggle: clicking the same criterion deselects it
        if (activeCriterion?.id === criterion.id) {
            setActiveCriterion(null);
        } else {
            setActiveCriterion(criterion);
        }
    }

    const reviewedCount = criteria?.filter((c) => c.review_status !== null).length ?? 0;
    const totalCount = criteria?.length ?? 0;
    const progressPercent = totalCount > 0 ? Math.round((reviewedCount / totalCount) * 100) : 0;

    // Group entities by criteria_id
    const groupedEntities: Record<string, EntityResponse[]> = {};
    if (entities) {
        for (const entity of entities) {
            if (!groupedEntities[entity.criteria_id]) {
                groupedEntities[entity.criteria_id] = [];
            }
            groupedEntities[entity.criteria_id]?.push(entity);
        }
    }

    // Client-side filtering
    const filteredCriteria = useMemo(() => {
        if (!criteria) return [];
        return criteria.filter((c) => {
            // Text search (case-insensitive)
            if (debouncedSearch && !c.text.toLowerCase().includes(debouncedSearch.toLowerCase())) {
                return false;
            }
            // Status filter
            if (statusFilter !== 'all') {
                const isReviewed = c.review_status !== null;
                if (statusFilter === 'reviewed' && !isReviewed) return false;
                if (statusFilter === 'pending' && isReviewed) return false;
            }
            // Type filter
            if (typeFilter !== 'all' && c.criteria_type !== typeFilter) {
                return false;
            }
            // Confidence filter (high>=0.85, medium>=0.7, low<0.7)
            if (confidenceFilter !== 'all') {
                if (confidenceFilter === 'high' && c.confidence < 0.85) return false;
                if (confidenceFilter === 'medium' && (c.confidence < 0.7 || c.confidence >= 0.85))
                    return false;
                if (confidenceFilter === 'low' && c.confidence >= 0.7) return false;
            }
            return true;
        });
    }, [criteria, debouncedSearch, statusFilter, typeFilter, confidenceFilter]);

    // Section grouping with pending-first sort
    const { uncategorizedCriteria, inclusionCriteria, exclusionCriteria } = useMemo(() => {
        const uncategorized: Criterion[] = [];
        const inclusion: Criterion[] = [];
        const exclusion: Criterion[] = [];

        for (const c of filteredCriteria) {
            if (
                !c.criteria_type ||
                (c.criteria_type !== 'inclusion' && c.criteria_type !== 'exclusion')
            ) {
                uncategorized.push(c);
            } else if (c.criteria_type === 'inclusion') {
                inclusion.push(c);
            } else {
                exclusion.push(c);
            }
        }

        const sortFn = (a: Criterion, b: Criterion) => {
            const aPending = a.review_status === null;
            const bPending = b.review_status === null;
            if (aPending && !bPending) return -1;
            if (!aPending && bPending) return 1;
            return 0;
        };
        uncategorized.sort(sortFn);
        inclusion.sort(sortFn);
        exclusion.sort(sortFn);

        return {
            uncategorizedCriteria: uncategorized,
            inclusionCriteria: inclusion,
            exclusionCriteria: exclusion,
        };
    }, [filteredCriteria]);

    const countReviewed = (list: Criterion[]) =>
        list.filter((c) => c.review_status !== null).length;

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
                                <PdfViewer
                                    url={pdfData.url}
                                    targetPage={activeCriterion?.page_number ?? null}
                                    highlightText={activeCriterion?.text ?? null}
                                />
                            ) : (
                                <div className="flex items-center justify-center h-full">
                                    <p className="text-muted-foreground">No PDF available</p>
                                </div>
                            )}
                        </div>
                    </div>
                </Panel>

                <PanelResizeHandle className="w-1 bg-border hover:bg-primary/20 transition-colors" />

                {/* Right panel: Criteria and Entities Review */}
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
                        </div>

                        {/* Tabs for Criteria and Entities */}
                        <Tabs.Root value={activeTab} onValueChange={setActiveTab}>
                            <Tabs.List className="flex border-b bg-card px-4">
                                <Tabs.Trigger
                                    value="criteria"
                                    className={cn(
                                        'px-4 py-2 text-sm font-medium border-b-2 transition-colors',
                                        activeTab === 'criteria'
                                            ? 'border-primary text-foreground'
                                            : 'border-transparent text-muted-foreground hover:text-foreground'
                                    )}
                                >
                                    Criteria
                                </Tabs.Trigger>
                                <Tabs.Trigger
                                    value="entities"
                                    className={cn(
                                        'px-4 py-2 text-sm font-medium border-b-2 transition-colors',
                                        activeTab === 'entities'
                                            ? 'border-primary text-foreground'
                                            : 'border-transparent text-muted-foreground hover:text-foreground'
                                    )}
                                >
                                    Entities
                                </Tabs.Trigger>
                            </Tabs.List>

                            {/* Criteria Tab Content */}
                            <Tabs.Content value="criteria" className="">
                                {/* Sticky filter bar */}
                                <div className="sticky top-0 z-10 bg-card border-b px-4 py-3">
                                    <div className="flex items-center gap-3 flex-wrap">
                                        <div className="relative flex-1 min-w-[200px]">
                                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                            <input
                                                type="text"
                                                value={searchText}
                                                onChange={(e) => setSearchText(e.target.value)}
                                                placeholder="Search criteria..."
                                                className="w-full rounded-md border border-input bg-background pl-9 pr-3 py-2 text-sm"
                                            />
                                        </div>
                                        <select
                                            value={statusFilter}
                                            onChange={(e) => setStatusFilter(e.target.value)}
                                            className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        >
                                            <option value="all">All Status</option>
                                            <option value="pending">Pending</option>
                                            <option value="reviewed">Reviewed</option>
                                        </select>
                                        <select
                                            value={typeFilter}
                                            onChange={(e) => setTypeFilter(e.target.value)}
                                            className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        >
                                            <option value="all">All Types</option>
                                            <option value="inclusion">Inclusion</option>
                                            <option value="exclusion">Exclusion</option>
                                        </select>
                                        <select
                                            value={confidenceFilter}
                                            onChange={(e) => setConfidenceFilter(e.target.value)}
                                            className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        >
                                            <option value="all">All Confidence</option>
                                            <option value="high">High (≥85%)</option>
                                            <option value="medium">Medium (70-84%)</option>
                                            <option value="low">Low (&lt;70%)</option>
                                        </select>
                                    </div>
                                </div>

                                {/* Criteria sections */}
                                <div className="p-4 space-y-6">
                                    {/* To Be Sorted — appears at top if any uncategorized criteria exist */}
                                    {uncategorizedCriteria.length > 0 && (
                                        <section>
                                            <h2 className="text-lg font-bold mb-3 text-foreground">
                                                To Be Sorted ({countReviewed(uncategorizedCriteria)}
                                                /{uncategorizedCriteria.length} reviewed)
                                            </h2>
                                            <div className="space-y-4">
                                                {uncategorizedCriteria.map((c) => (
                                                    <CriterionCard
                                                        key={c.id}
                                                        criterion={c}
                                                        onAction={handleAction}
                                                        isSubmitting={reviewAction.isPending}
                                                        onCriterionClick={handleCriterionClick}
                                                        isActive={activeCriterion?.id === c.id}
                                                    />
                                                ))}
                                            </div>
                                        </section>
                                    )}

                                    {/* Inclusion Criteria section */}
                                    {inclusionCriteria.length > 0 && (
                                        <section>
                                            <h2 className="text-lg font-bold mb-3 text-foreground">
                                                Inclusion Criteria (
                                                {countReviewed(inclusionCriteria)}/
                                                {inclusionCriteria.length} reviewed)
                                            </h2>
                                            <div className="space-y-4">
                                                {inclusionCriteria.map((c) => (
                                                    <CriterionCard
                                                        key={c.id}
                                                        criterion={c}
                                                        onAction={handleAction}
                                                        isSubmitting={reviewAction.isPending}
                                                        onCriterionClick={handleCriterionClick}
                                                        isActive={activeCriterion?.id === c.id}
                                                    />
                                                ))}
                                            </div>
                                        </section>
                                    )}

                                    {/* Exclusion Criteria section */}
                                    {exclusionCriteria.length > 0 && (
                                        <section>
                                            <h2 className="text-lg font-bold mb-3 text-foreground">
                                                Exclusion Criteria (
                                                {countReviewed(exclusionCriteria)}/
                                                {exclusionCriteria.length} reviewed)
                                            </h2>
                                            <div className="space-y-4">
                                                {exclusionCriteria.map((c) => (
                                                    <CriterionCard
                                                        key={c.id}
                                                        criterion={c}
                                                        onAction={handleAction}
                                                        isSubmitting={reviewAction.isPending}
                                                        onCriterionClick={handleCriterionClick}
                                                        isActive={activeCriterion?.id === c.id}
                                                    />
                                                ))}
                                            </div>
                                        </section>
                                    )}

                                    {/* Empty state when filters match nothing */}
                                    {filteredCriteria.length === 0 &&
                                        criteria &&
                                        criteria.length > 0 && (
                                            <div className="text-center py-8">
                                                <p className="text-muted-foreground">
                                                    No criteria match your filters
                                                </p>
                                            </div>
                                        )}

                                    {/* Original empty state when no criteria at all */}
                                    {(!criteria || criteria.length === 0) && (
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
                                                            {entry.target_type &&
                                                                entry.target_id && (
                                                                    <span className="text-muted-foreground">
                                                                        on {entry.target_type}:
                                                                        {entry.target_id.slice(
                                                                            0,
                                                                            8
                                                                        )}
                                                                    </span>
                                                                )}
                                                        </div>
                                                    ))
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </Tabs.Content>

                            {/* Entities Tab Content */}
                            <Tabs.Content value="entities" className="p-4">
                                {entities && entities.length > 0 ? (
                                    <div className="space-y-6">
                                        {Object.entries(groupedEntities).map(
                                            ([criteriaId, criteriaEntities]) =>
                                                criteriaEntities ? (
                                                    <div key={criteriaId} className="space-y-3">
                                                        <h3 className="text-sm font-medium text-muted-foreground">
                                                            Criterion: {criteriaId.slice(0, 8)}...
                                                        </h3>
                                                        {criteriaEntities.map((entity) => (
                                                            <EntityCard
                                                                key={entity.id}
                                                                entity={entity}
                                                                onAction={handleEntityAction}
                                                                isSubmitting={
                                                                    entityAction.isPending
                                                                }
                                                            />
                                                        ))}
                                                    </div>
                                                ) : null
                                        )}
                                    </div>
                                ) : (
                                    <div className="text-center py-8">
                                        <p className="text-muted-foreground">
                                            No entities found for this batch
                                        </p>
                                    </div>
                                )}
                            </Tabs.Content>
                        </Tabs.Root>
                    </div>
                </Panel>
            </PanelGroup>
        </div>
    );
}
