import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { useAuthStore } from '../stores/authStore';
import type { TerminologySystem } from '../components/TerminologyBadge';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface TerminologySearchResult {
    code: string;
    display: string;
    system: string;
    semantic_type?: string;
    confidence: number;
}

export function useTerminologySearch(
    system: TerminologySystem,
    query: string
): {
    results: TerminologySearchResult[];
    isLoading: boolean;
    isError: boolean;
    isCircuitOpen: boolean;
    validationHint: string | null;
} {
    // Debounce query by 300ms
    const [debouncedQuery, setDebouncedQuery] = useState(query);
    const [isCircuitOpen, setIsCircuitOpen] = useState(false);

    useEffect(() => {
        const timeout = setTimeout(() => {
            setDebouncedQuery(query);
        }, 150);

        return () => {
            clearTimeout(timeout);
        };
    }, [query]);

    // Numeric-only queries are invalid for text name search
    const isNumericOnly = /^\d+$/.test(debouncedQuery.trim());

    // Only enable when debouncedQuery has at least 3 characters and is not numeric-only
    const enabled = debouncedQuery.trim().length >= 3 && !isNumericOnly;

    const { data, isFetching, isError } = useQuery({
        queryKey: ['terminology-search', system, debouncedQuery],
        queryFn: async ({ signal }) => {
            const token = useAuthStore.getState().token;
            const headers: HeadersInit = {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
            };

            const response = await fetch(
                `${API_BASE_URL}/api/terminology/${system}/search?q=${encodeURIComponent(debouncedQuery)}`,
                {
                    headers,
                    signal,
                }
            );

            if (response.status === 401) {
                useAuthStore.getState().logout();
                throw new Error('Session expired');
            }

            // 503 signals circuit breaker is open — track state separately
            if (response.status === 503) {
                setIsCircuitOpen(true);
                throw new Error('Terminology service temporarily unavailable');
            }

            if (response.ok) {
                setIsCircuitOpen(false); // Reset on successful response
            }

            if (!response.ok) {
                throw new Error(`API Error: ${response.status} ${response.statusText}`);
            }

            return response.json() as Promise<TerminologySearchResult[]>;
        },
        enabled,
        staleTime: 5 * 60 * 1000, // 5 minutes
        gcTime: 10 * 60 * 1000, // 10 minutes
        retry: 1,
        refetchOnWindowFocus: false,
    });

    const validationHint = (() => {
        const trimmed = debouncedQuery.trim();
        if (trimmed.length > 0 && trimmed.length < 3) return 'Type at least 3 characters';
        if (isNumericOnly && trimmed.length >= 3) return 'Enter a term name, not a code number';
        if (isCircuitOpen) return 'Terminology search temporarily unavailable';
        return null;
    })();

    return {
        results: data ?? [],
        isLoading: isFetching,
        isError,
        isCircuitOpen,
        validationHint,
    };
}
