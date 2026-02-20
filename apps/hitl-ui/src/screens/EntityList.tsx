import { ArrowLeft, Loader2 } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';

import EntityCard from '../components/EntityCard';
import type { EntityActionRequest, EntityResponse } from '../hooks/useEntities';
import { useEntityAction, useEntityListByBatch } from '../hooks/useEntities';

export default function EntityList() {
    const { batchId } = useParams<{ batchId: string }>();

    const { data: entities, isLoading, error } = useEntityListByBatch(batchId ?? '');

    const entityAction = useEntityAction();

    function handleAction(entityId: string, action: EntityActionRequest) {
        entityAction.mutate({ entityId, ...action });
    }

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

    const totalCount = entities?.length ?? 0;
    const approvedCount = entities?.filter((e) => e.review_status === 'approved').length ?? 0;
    const rejectedCount = entities?.filter((e) => e.review_status === 'rejected').length ?? 0;
    const pendingCount = entities?.filter((e) => e.review_status === null).length ?? 0;

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-screen">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (error) {
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
                    <p className="text-destructive">Failed to load entities: {error.message}</p>
                </div>
            </div>
        );
    }

    return (
        <div className="container mx-auto p-6">
            <Link
                to={`/reviews/${batchId}`}
                className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-6"
            >
                <ArrowLeft className="h-4 w-4 mr-1" />
                Back to Review
            </Link>

            <header className="mb-6">
                <h1 className="text-3xl font-bold text-foreground mb-2">Entity Review</h1>
                <p className="text-muted-foreground">
                    Review UMLS and SNOMED grounding for extracted entities
                </p>
            </header>

            {/* Summary stats */}
            <div className="grid grid-cols-4 gap-4 mb-6">
                <div className="rounded-lg border bg-card p-4">
                    <p className="text-sm text-muted-foreground">Total Entities</p>
                    <p className="text-2xl font-bold">{totalCount}</p>
                </div>
                <div className="rounded-lg border bg-card p-4">
                    <p className="text-sm text-muted-foreground">Approved</p>
                    <p className="text-2xl font-bold text-green-600">{approvedCount}</p>
                </div>
                <div className="rounded-lg border bg-card p-4">
                    <p className="text-sm text-muted-foreground">Pending</p>
                    <p className="text-2xl font-bold text-yellow-600">{pendingCount}</p>
                </div>
                <div className="rounded-lg border bg-card p-4">
                    <p className="text-sm text-muted-foreground">Rejected</p>
                    <p className="text-2xl font-bold text-red-600">{rejectedCount}</p>
                </div>
            </div>

            {/* Grouped entities */}
            {Object.keys(groupedEntities).length === 0 ? (
                <div className="text-center py-8 rounded-lg border bg-card">
                    <p className="text-muted-foreground">No entities found for this batch</p>
                </div>
            ) : (
                <div className="space-y-6">
                    {Object.entries(groupedEntities).map(([criteriaId, criteriaEntities]) =>
                        criteriaEntities ? (
                            <div key={criteriaId} className="rounded-lg border bg-card p-4">
                                <h3 className="text-sm font-medium text-muted-foreground mb-4">
                                    Criterion: {criteriaId.slice(0, 8)}...
                                </h3>
                                <div className="space-y-3">
                                    {criteriaEntities.map((entity) => (
                                        <EntityCard
                                            key={entity.id}
                                            entity={entity}
                                            onAction={handleAction}
                                            isSubmitting={entityAction.isPending}
                                        />
                                    ))}
                                </div>
                            </div>
                        ) : null
                    )}
                </div>
            )}
        </div>
    );
}
