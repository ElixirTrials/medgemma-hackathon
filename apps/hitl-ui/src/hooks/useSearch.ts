import { useQuery } from '@tanstack/react-query';

import { fetchApi } from '../lib/fetchApi';

// --- TypeScript interfaces ---

export interface SearchResult {
    id: string;
    batch_id: string;
    protocol_id: string;
    protocol_title: string;
    criteria_type: string;
    text: string;
    confidence: number;
    review_status: string | null;
    rank: number;
}

export interface SearchResponse {
    items: SearchResult[];
    total: number;
    page: number;
    page_size: number;
    pages: number;
    query: string;
}

export interface SearchFilters {
    protocol_id?: string;
    criteria_type?: string;
    review_status?: string;
}

// --- Hooks ---

export function useCriteriaSearch(
    query: string,
    filters: SearchFilters,
    page: number,
    pageSize: number
) {
    const params = new URLSearchParams({
        q: query,
        page: String(page),
        page_size: String(pageSize),
    });

    if (filters.protocol_id) {
        params.set('protocol_id', filters.protocol_id);
    }
    if (filters.criteria_type) {
        params.set('criteria_type', filters.criteria_type);
    }
    if (filters.review_status) {
        params.set('review_status', filters.review_status);
    }

    return useQuery({
        queryKey: ['criteria-search', query, filters, page, pageSize],
        queryFn: () => fetchApi<SearchResponse>(`/criteria/search?${params.toString()}`),
        enabled: query.length >= 2,
    });
}
