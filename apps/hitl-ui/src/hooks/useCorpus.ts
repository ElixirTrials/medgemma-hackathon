import { useMutation, useQuery } from '@tanstack/react-query';

import { fetchApi } from '../lib/fetchApi';

// --- TypeScript interfaces ---

export interface BatchMetrics {
    batch_id: string;
    total_criteria: number;
    approved: number;
    rejected: number;
    modified: number;
    pending: number;
    approved_pct: number;
    rejected_pct: number;
    modified_pct: number;
    modification_breakdown: Record<string, number>;
    per_criterion_details: Array<{
        criterion_id: string;
        criterion_text: string;
        review_status: string;
        criteria_type: string;
    }>;
}

export interface BatchSummary {
    id: string;
    protocol_id: string;
    status: string;
    is_archived: boolean;
    criteria_count: number;
    reviewed_count: number;
    extraction_model: string | null;
    created_at: string;
}

export interface CriterionCompareRow {
    status: 'added' | 'removed' | 'changed' | 'unchanged';
    batch_a_criterion: Record<string, unknown> | null;
    batch_b_criterion: Record<string, unknown> | null;
    match_score: number | null;
}

export interface BatchCompareResponse {
    batch_a_id: string;
    batch_b_id: string;
    added: number;
    removed: number;
    changed: number;
    unchanged: number;
    rows: CriterionCompareRow[];
}

export interface CriterionRerunResponse {
    original_criterion: Record<string, unknown>;
    revised_criterion: Record<string, unknown>;
}

// --- Hooks ---

export function useBatchMetrics(batchId: string) {
    return useQuery({
        queryKey: ['batch-metrics', batchId],
        queryFn: () => fetchApi<BatchMetrics>(`/reviews/batches/${batchId}/metrics`),
        enabled: !!batchId,
    });
}

export function useAllProtocolBatches(protocolId: string) {
    return useQuery({
        queryKey: ['protocol-batches-all', protocolId],
        queryFn: () => fetchApi<BatchSummary[]>(`/protocols/${protocolId}/batches`),
        enabled: !!protocolId,
    });
}

export function useBatchCompare(batchA: string, batchB: string) {
    return useQuery({
        queryKey: ['batch-compare', batchA, batchB],
        queryFn: () =>
            fetchApi<BatchCompareResponse>(
                `/reviews/batch-compare?batch_a=${encodeURIComponent(batchA)}&batch_b=${encodeURIComponent(batchB)}`
            ),
        enabled: !!batchA && !!batchB,
    });
}

export function useCriterionRerun() {
    return useMutation({
        mutationFn: ({
            criterionId,
            reviewer_feedback,
        }: {
            criterionId: string;
            reviewer_feedback: string;
        }) =>
            fetchApi<CriterionRerunResponse>(`/reviews/criteria/${criterionId}/rerun`, {
                method: 'POST',
                body: JSON.stringify({ reviewer_feedback }),
            }),
        // No cache invalidation — this is a read-only proposal, not committed to DB
    });
}
