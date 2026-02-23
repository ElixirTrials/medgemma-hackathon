import { toast } from 'sonner';

import { useAuthStore } from '../stores/authStore';

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export class SessionExpiredError extends Error {
    constructor() {
        super('Session expired');
        this.name = 'SessionExpiredError';
    }
}

let _sessionExpiredToastShown = false;

function _handleSessionExpired(): void {
    useAuthStore.getState().setSessionExpired();
    if (!_sessionExpiredToastShown) {
        _sessionExpiredToastShown = true;
        toast.error('Session expired — please sign in again', {
            duration: 6000,
            onDismiss: () => {
                _sessionExpiredToastShown = false;
            },
            onAutoClose: () => {
                _sessionExpiredToastShown = false;
            },
        });
    }
}

/**
 * Authenticated fetch wrapper. Attaches JWT and handles 401 → session expired.
 */
export async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
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
        _handleSessionExpired();
        throw new SessionExpiredError();
    }

    if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
    }

    return response.json();
}

/**
 * Public (unauthenticated) fetch wrapper for endpoints like /health and /ready.
 */
export async function fetchPublicApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options?.headers,
        },
    });

    if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
    }

    return response.json();
}
