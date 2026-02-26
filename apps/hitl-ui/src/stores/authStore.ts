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
    isSessionExpired: boolean;
    setAuth: (token: string, user: User) => void;
    setSessionExpired: () => void;
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
    isSessionExpired: false,
    setAuth: (token: string, user: User) => {
        localStorage.setItem('auth_token', token);
        localStorage.setItem('auth_user', JSON.stringify(user));
        set({ token, user, isSessionExpired: false });
    },
    setSessionExpired: () => {
        // Guard against cascading calls from multiple simultaneous 401s
        if (get().isSessionExpired) return;
        set({ isSessionExpired: true });
    },
    logout: () => {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_user');
        set({ token: null, user: null, isSessionExpired: false });
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

// Login function that opens a popup for OAuth and listens for the token via postMessage.
// Returns a cleanup function; call it if the component unmounts while the popup is open.
export function initiateLogin(): { popupBlocked: boolean; cleanup: () => void } {
    const popup = window.open(
        `${API_BASE_URL}/auth/login?popup=1`,
        'auth-popup',
        'width=500,height=600,menubar=no,toolbar=no'
    );

    if (!popup) {
        return { popupBlocked: true, cleanup: () => {} };
    }

    const handleMessage = (event: MessageEvent) => {
        const apiOrigin = new URL(API_BASE_URL).origin;
        if (event.origin !== apiOrigin) return;
        const { access_token, user } = event.data ?? {};
        if (access_token && user) {
            useAuthStore.getState().setAuth(access_token, user);
            popup.close();
            window.removeEventListener('message', handleMessage);
        }
    };
    window.addEventListener('message', handleMessage);

    return {
        popupBlocked: false,
        cleanup: () => window.removeEventListener('message', handleMessage),
    };
}
