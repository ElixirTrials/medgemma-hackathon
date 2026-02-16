import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAuthStore } from '../stores/authStore';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
    // Get auth token from store
    const token = useAuthStore.getState().token;
    const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options?.headers || {}),
    };

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...options,
        headers,
    });

    if (response.status === 401) {
        useAuthStore.getState().logout();
        throw new Error('Session expired');
    }

    if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
    }

    return response.json();
}

// --- TypeScript interfaces ---

export interface CriteriaBatch {
    id: string;
    protocol_id: string;
    protocol_title: string;
    status: 'pending_review' | 'in_progress' | 'approved' | 'rejected';
    extraction_model: string | null;
    criteria_count: number;
    reviewed_count: number;
    created_at: string;
    updated_at: string;
}

export interface BatchListResponse {
    items: CriteriaBatch[];
    total: number;
    page: number;
    page_size: number;
    pages: number;
}

// Field mapping for structured criteria edits (entity/relation/value triplet)
export interface FieldMapping {
    entity: string;
    relation: string;
    value: unknown;
}

export interface CriterionEntity {
    id: string;
    entity_type: string;
    text: string;
    umls_cui: string | null;
    snomed_code: string | null;
    preferred_term: string | null;
    grounding_confidence: number | null;
}

export interface Criterion {
    id: string;
    batch_id: string;
    criteria_type: string;
    category: string | null;
    text: string;
    temporal_constraint: Record<string, unknown> | null;
    conditions: Record<string, unknown> | null;
    numeric_thresholds: Record<string, unknown> | null;
    assertion_status: string | null;
    confidence: number;
    source_section: string | null;
    page_number: number | null;
    review_status: string | null;
    entities: CriterionEntity[];
    created_at: string;
    updated_at: string;
}

export interface ReviewActionRequest {
    action: 'approve' | 'reject' | 'modify';
    reviewer_id: string;
    modified_text?: string;
    modified_type?: string;
    modified_category?: string;
    modified_structured_fields?: {
        field_mappings?: FieldMapping[];
        [key: string]: unknown;
    };
    comment?: string;
}

export interface PdfUrlResponse {
    url: string;
    expires_in_minutes: number;
}

export interface AuditLogEntry {
    id: string;
    event_type: string;
    actor_id: string | null;
    target_type: string | null;
    target_id: string | null;
    details: Record<string, unknown>;
    created_at: string;
}

export interface AuditLogListResponse {
    items: AuditLogEntry[];
    total: number;
    page: number;
    page_size: number;
    pages: number;
}

// --- Hooks ---

export function useBatchList(page: number, pageSize: number, status?: string) {
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
    });
    if (status) {
        params.set('status', status);
    }

    return useQuery({
        queryKey: ['review-batches', page, pageSize, status],
        queryFn: () => fetchApi<BatchListResponse>(`/reviews/batches?${params.toString()}`),
    });
}

export function useBatchesByProtocol(protocolId: string) {
    return useQuery({
        queryKey: ['review-batches', 'protocol', protocolId],
        queryFn: () =>
            fetchApi<BatchListResponse>(
                `/reviews/batches?protocol_id=${encodeURIComponent(protocolId)}`
            ),
        enabled: !!protocolId,
    });
}

export function useBatchCriteria(batchId: string, sortBy?: string, sortOrder?: string) {
    const params = new URLSearchParams();
    if (sortBy) {
        params.set('sort_by', sortBy);
    }
    if (sortOrder) {
        params.set('sort_order', sortOrder);
    }
    const queryString = params.toString();
    const url = queryString
        ? `/reviews/batches/${batchId}/criteria?${queryString}`
        : `/reviews/batches/${batchId}/criteria`;

    return useQuery({
        queryKey: ['batch-criteria', batchId, sortBy, sortOrder],
        queryFn: () => fetchApi<Criterion[]>(url),
        enabled: Boolean(batchId),
    });
}

export function useReviewAction() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ criteriaId, ...body }: ReviewActionRequest & { criteriaId: string }) =>
            fetchApi<Criterion>(`/reviews/criteria/${criteriaId}/action`, {
                method: 'POST',
                body: JSON.stringify(body),
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['batch-criteria'] });
            queryClient.invalidateQueries({ queryKey: ['review-batches'] });
        },
    });
}

export function usePdfUrl(protocolId: string) {
    return useQuery({
        queryKey: ['pdf-url', protocolId],
        queryFn: () => fetchApi<PdfUrlResponse>(`/reviews/protocols/${protocolId}/pdf-url`),
        enabled: Boolean(protocolId),
        staleTime: 50 * 60 * 1000,
    });
}

export function useAuditLog(
    page: number,
    pageSize: number,
    targetType?: string,
    targetId?: string
) {
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
    });
    if (targetType) {
        params.set('target_type', targetType);
    }
    if (targetId) {
        params.set('target_id', targetId);
    }

    return useQuery({
        queryKey: ['audit-log', page, pageSize, targetType, targetId],
        queryFn: () => fetchApi<AuditLogListResponse>(`/reviews/audit-log?${params.toString()}`),
    });
}
