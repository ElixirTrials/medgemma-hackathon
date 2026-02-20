import { getAuthHeaders, initiateLogin, useAuthStore } from '../stores/authStore';

export function useAuth() {
    const { token, user, setAuth, logout, isAuthenticated } = useAuthStore();

    return {
        token,
        user,
        isAuthenticated: isAuthenticated(),
        login: initiateLogin,
        logout,
        setAuth,
    };
}

export { getAuthHeaders };
