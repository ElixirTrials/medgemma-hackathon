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

export interface Protocol {
    id: string;
    title: string;
    file_uri: string;
    status:
        | 'uploaded'
        | 'extracting'
        | 'extraction_failed'
        | 'grounding'
        | 'grounding_failed'
        | 'pending_review'
        | 'complete'
        | 'dead_letter'
        | 'archived';
    error_reason: string | null;
    page_count: number | null;
    quality_score: number | null;
    metadata_: Record<string, unknown>;
    created_at: string;
    updated_at: string;
}

export interface ProtocolListResponse {
    items: Protocol[];
    total: number;
    page: number;
    page_size: number;
    pages: number;
}

export interface UploadResponse {
    protocol_id: string;
    upload_url: string;
    gcs_path: string;
}

// --- Hooks ---

export function useProtocolList(page: number, pageSize: number, status?: string) {
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
    });
    if (status) {
        params.set('status', status);
    }

    return useQuery({
        queryKey: ['protocols', page, pageSize, status],
        queryFn: () => fetchApi<ProtocolListResponse>(`/protocols?${params.toString()}`),
    });
}

export function useProtocol(id: string) {
    return useQuery({
        queryKey: ['protocols', id],
        queryFn: () => fetchApi<Protocol>(`/protocols/${id}`),
        enabled: Boolean(id),
    });
}

export function useUploadProtocol() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ file }: { file: File }) => {
            // Step 1: Get signed upload URL from backend
            const uploadResp = await fetchApi<UploadResponse>('/protocols/upload', {
                method: 'POST',
                body: JSON.stringify({
                    filename: file.name,
                    content_type: file.type,
                    file_size_bytes: file.size,
                }),
            });

            // Step 2: Upload file directly to GCS via signed URL
            const putResp = await fetch(uploadResp.upload_url, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/pdf' },
                body: file,
            });

            if (!putResp.ok) {
                throw new Error(`Upload failed: ${putResp.status} ${putResp.statusText}`);
            }

            // Step 3: Read file as base64 for quality scoring, then confirm
            const arrayBuffer = await file.arrayBuffer();
            const bytes = new Uint8Array(arrayBuffer);
            let binary = '';
            for (let i = 0; i < bytes.length; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            const pdfBase64 = btoa(binary);

            await fetchApi(`/protocols/${uploadResp.protocol_id}/confirm-upload`, {
                method: 'POST',
                body: JSON.stringify({ pdf_bytes_base64: pdfBase64 }),
            });

            return uploadResp;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['protocols'] });
        },
    });
}

export function useConfirmUpload() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: ({ id, pdfBase64 }: { id: string; pdfBase64?: string }) =>
            fetchApi(`/protocols/${id}/confirm-upload`, {
                method: 'POST',
                body: JSON.stringify(pdfBase64 ? { pdf_bytes_base64: pdfBase64 } : {}),
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['protocols'] });
        },
    });
}

export function useRetryProtocol() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (protocolId: string) =>
            fetchApi<{ status: string; protocol_id: string }>(
                `/protocols/${protocolId}/retry`,
                { method: 'POST' }
            ),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['protocols'] });
        },
    });
}
