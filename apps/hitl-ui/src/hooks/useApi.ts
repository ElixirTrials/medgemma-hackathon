import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

import { fetchApi, fetchPublicApi } from '../lib/fetchApi';
import { useAuthStore } from '../stores/authStore';

interface HealthChecks {
    database: string;
    omop_vocab: string;
    omop_concept_count?: number;
    gcs?: string;
    breakers?: Record<string, string>;
}

interface HealthResponse {
    status: string;
    checks?: HealthChecks;
}

export function useHealthCheck() {
    const result = useQuery({
        queryKey: ['health'],
        queryFn: () => fetchPublicApi<HealthResponse>('/health'),
        refetchInterval: 30000, // Check every 30 seconds
        retry: 5,
        retryDelay: (attemptIndex) => {
            // First retry waits 10s (backend startup), subsequent retries 3s
            return attemptIndex === 0 ? 10000 : 3000;
        },
    });
    // When backend reports Google creds expired, show login modal (do not retry).
    useEffect(() => {
        if (result.data?.checks?.gcs === 'auth_expired') {
            useAuthStore.getState().setSessionExpired();
        }
    }, [result.data?.checks?.gcs]);
    return result;
}

interface ReadinessResponse {
    status: string;
    database: string;
}

export function useReadinessCheck() {
    return useQuery({
        queryKey: ['ready'],
        queryFn: () => fetchPublicApi<ReadinessResponse>('/ready'),
    });
}

interface Task {
    id: string;
    status: string;
    input_data: Record<string, unknown>;
    output_data: Record<string, unknown>;
}

export function useTasks() {
    return useQuery({
        queryKey: ['tasks'],
        queryFn: () => fetchApi<Task[]>('/api/tasks'),
    });
}

export function useApproveTask() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (taskId: string) =>
            fetchApi(`/api/tasks/${taskId}/approve`, { method: 'POST' }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tasks'] });
        },
    });
}

export function useRejectTask() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (taskId: string) => fetchApi(`/api/tasks/${taskId}/reject`, { method: 'POST' }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tasks'] });
        },
    });
}
