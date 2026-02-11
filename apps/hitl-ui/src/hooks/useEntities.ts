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

    if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
    }

    return response.json();
}

// --- TypeScript interfaces ---

export interface EntityResponse {
    id: string;
    criteria_id: string;
    entity_type: string;
    text: string;
    span_start: number | null;
    span_end: number | null;
    umls_cui: string | null;
    snomed_code: string | null;
    preferred_term: string | null;
    grounding_confidence: number | null;
    grounding_method: string | null;
    review_status: string | null;
    context_window: Record<string, unknown> | null;
    created_at: string;
    updated_at: string;
}

export interface EntityActionRequest {
    action: 'approve' | 'reject' | 'modify';
    reviewer_id: string;
    modified_umls_cui?: string;
    modified_snomed_code?: string;
    modified_preferred_term?: string;
    comment?: string;
}

// --- Hooks ---

export function useEntityListByCriteria(criteriaId: string) {
    return useQuery({
        queryKey: ['entities-by-criteria', criteriaId],
        queryFn: () => fetchApi<EntityResponse[]>(`/entities/criteria/${criteriaId}`),
        enabled: Boolean(criteriaId),
    });
}

export function useEntityListByBatch(batchId: string) {
    return useQuery({
        queryKey: ['entities-by-batch', batchId],
        queryFn: () => fetchApi<EntityResponse[]>(`/entities/batch/${batchId}`),
        enabled: Boolean(batchId),
    });
}

export function useEntityAction() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ entityId, ...body }: EntityActionRequest & { entityId: string }) =>
            fetchApi<EntityResponse>(`/entities/${entityId}/action`, {
                method: 'POST',
                body: JSON.stringify(body),
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['entities-by-criteria'] });
            queryClient.invalidateQueries({ queryKey: ['entities-by-batch'] });
        },
    });
}
