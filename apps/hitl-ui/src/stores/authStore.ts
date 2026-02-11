import { create } from 'zustand';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface User {
    id: string;
    email: string;
    name: string | null;
}

interface AuthState {
    token: string | null;
    user: User | null;
    setAuth: (token: string, user: User) => void;
    logout: () => void;
    isAuthenticated: () => boolean;
}

// Initialize from localStorage
function getStoredAuth(): { token: string | null; user: User | null } {
    try {
        const token = localStorage.getItem('auth_token');
        const userStr = localStorage.getItem('auth_user');
        const user = userStr ? JSON.parse(userStr) : null;
        return { token, user };
    } catch {
        return { token: null, user: null };
    }
}

export const useAuthStore = create<AuthState>((set, get) => ({
    ...getStoredAuth(),
    setAuth: (token: string, user: User) => {
        localStorage.setItem('auth_token', token);
        localStorage.setItem('auth_user', JSON.stringify(user));
        set({ token, user });
    },
    logout: () => {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_user');
        set({ token: null, user: null });
    },
    isAuthenticated: () => {
        const state = get();
        return Boolean(state.token && state.user);
    },
}));

// Utility function to get auth headers
export function getAuthHeaders(): Record<string, string> {
    const token = useAuthStore.getState().token;
    return token ? { Authorization: `Bearer ${token}` } : {};
}

// Login function that redirects to OAuth endpoint
export function initiateLogin(): void {
    window.location.href = `${API_BASE_URL}/auth/login`;
}
