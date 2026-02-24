import { useQuery } from '@tanstack/react-query';

import { fetchApi } from '../lib/fetchApi';

export interface EntitySummary {
    id: string;
    entity_type: string;
    text: string;
    grounding_code: string | null;
    grounding_system: string | null;
    preferred_term: string | null;
    grounding_confidence: number | null;
    omop_concept_id: string | null;
    reconciliation_status: string | null;
}

export interface StructuredCriterionRow {
    id: string;
    protocol_id: string | null;
    protocol_title: string | null;
    text: string;
    criteria_type: string;
    category: string | null;
    confidence: number;
    assertion_status: string | null;
    entities: EntitySummary[];
    field_mappings: Array<Record<string, unknown>>;
    structured_criterion: Record<string, unknown> | null;
    review_status: string | null;
    page_number: number | null;
    source_section: string | null;
}

export interface StructuredCriteriaResponse {
    items: StructuredCriterionRow[];
    total: number;
    page: number;
    page_size: number;
    pages: number;
}

export interface CriteriaFilters {
    page: number;
    pageSize: number;
    criteriaType?: string;
    category?: string;
    protocolId?: string;
    minConfidence?: number;
    sortBy?: string;
    sortOrder?: 'asc' | 'desc';
    hasGrounding?: boolean;
}

export function useCriteriaSpreadsheet(filters: CriteriaFilters) {
    const params = new URLSearchParams({
        page: String(filters.page),
        page_size: String(filters.pageSize),
    });

    if (filters.criteriaType) params.set('criteria_type', filters.criteriaType);
    if (filters.category) params.set('category', filters.category);
    if (filters.protocolId) params.set('protocol_id', filters.protocolId);
    if (filters.minConfidence !== undefined)
        params.set('min_confidence', String(filters.minConfidence));
    if (filters.sortBy) params.set('sort_by', filters.sortBy);
    if (filters.sortOrder) params.set('sort_order', filters.sortOrder);
    if (filters.hasGrounding !== undefined)
        params.set('has_grounding', String(filters.hasGrounding));

    return useQuery({
        queryKey: ['criteria-structured', filters],
        queryFn: () =>
            fetchApi<StructuredCriteriaResponse>(`/criteria/structured?${params.toString()}`),
        staleTime: 30_000,
    });
}
