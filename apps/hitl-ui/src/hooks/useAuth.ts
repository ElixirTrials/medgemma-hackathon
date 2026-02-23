import { getAuthHeaders, initiateLogin, useAuthStore } from '../stores/authStore';

export function useAuth() {
    const { token, user, isSessionExpired, setAuth, logout, isAuthenticated } = useAuthStore();

    return {
        token,
        user,
        isAuthenticated: isAuthenticated(),
        isSessionExpired,
        login: initiateLogin,
        logout,
        setAuth,
    };
}

export { getAuthHeaders };
