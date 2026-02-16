import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { useAuthStore } from '../stores/authStore';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface UmlsSearchResult {
    cui: string;
    snomed_code: string;
    preferred_term: string;
    semantic_type: string;
    confidence: number;
}

export function useUmlsSearch(query: string): {
    results: UmlsSearchResult[];
    isLoading: boolean;
    isError: boolean;
    error: Error | null;
} {
    // Debounce the query input by 300ms
    const [debouncedQuery, setDebouncedQuery] = useState(query);

    useEffect(() => {
        const timeout = setTimeout(() => {
            setDebouncedQuery(query);
        }, 300);

        return () => {
            clearTimeout(timeout);
        };
    }, [query]);

    // Only enable the query when debouncedQuery has at least 3 characters
    const enabled = debouncedQuery.trim().length >= 3;

    const { data, isFetching, isError, error } = useQuery({
        queryKey: ['umls-search', debouncedQuery],
        queryFn: async ({ signal }) => {
            const token = useAuthStore.getState().token;
            const headers: HeadersInit = {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
            };

            const response = await fetch(
                `${API_BASE_URL}/api/umls/search?q=${encodeURIComponent(debouncedQuery)}`,
                {
                    headers,
                    signal,
                }
            );

            if (response.status === 401) {
                useAuthStore.getState().logout();
                throw new Error('Session expired');
            }

            if (!response.ok) {
                throw new Error(`API Error: ${response.status} ${response.statusText}`);
            }

            return response.json() as Promise<UmlsSearchResult[]>;
        },
        enabled,
        staleTime: 5 * 60 * 1000, // 5 minutes
        gcTime: 10 * 60 * 1000, // 10 minutes
        retry: 1,
        refetchOnWindowFocus: false,
    });

    return {
        results: data ?? [],
        isLoading: isFetching,
        isError,
        error: error as Error | null,
    };
}
