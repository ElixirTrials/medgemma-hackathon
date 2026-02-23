import * as Dialog from '@radix-ui/react-dialog';
import { useCallback, useState } from 'react';

import { API_BASE_URL } from '../lib/fetchApi';
import { useAuthStore } from '../stores/authStore';
import { Button } from './ui/Button';

export function SessionExpiredModal() {
    const isSessionExpired = useAuthStore((s) => s.isSessionExpired);
    const user = useAuthStore((s) => s.user);
    const setAuth = useAuthStore((s) => s.setAuth);
    const logout = useAuthStore((s) => s.logout);
    const [devLoading, setDevLoading] = useState(false);

    const handleDevLogin = useCallback(async () => {
        setDevLoading(true);
        try {
            const res = await fetch(`${API_BASE_URL}/auth/dev-login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            if (!res.ok) throw new Error('Dev login failed');
            const data = await res.json();
            setAuth(data.access_token, data.user);
        } catch {
            // Dev login not available — ignore
        } finally {
            setDevLoading(false);
        }
    }, [setAuth]);

    const handleGoogleLogin = useCallback(() => {
        const popup = window.open(
            `${API_BASE_URL}/auth/login?popup=1`,
            'auth-popup',
            'width=500,height=600,menubar=no,toolbar=no'
        );
        if (!popup) return;

        const handleMessage = (event: MessageEvent) => {
            // Only accept messages from our API origin
            const apiOrigin = new URL(API_BASE_URL).origin;
            if (event.origin !== apiOrigin) return;
            const { access_token, user: userData } = event.data ?? {};
            if (access_token && userData) {
                setAuth(access_token, userData);
                popup.close();
                window.removeEventListener('message', handleMessage);
            }
        };
        window.addEventListener('message', handleMessage);
    }, [setAuth]);

    return (
        <Dialog.Root open={isSessionExpired}>
            <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50" />
                <Dialog.Content
                    className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-card p-6 shadow-lg"
                    onPointerDownOutside={(e) => e.preventDefault()}
                    onEscapeKeyDown={(e) => e.preventDefault()}
                >
                    <Dialog.Title className="text-lg font-semibold">Session Expired</Dialog.Title>
                    <Dialog.Description className="mt-2 text-sm text-muted-foreground">
                        Your session has expired. Please sign in again to continue.
                        {user?.email && (
                            <span className="block mt-1 font-medium text-foreground">
                                {user.email}
                            </span>
                        )}
                    </Dialog.Description>

                    <div className="mt-6 space-y-3">
                        <Button className="w-full" onClick={handleDevLogin} disabled={devLoading}>
                            {devLoading ? 'Signing in...' : 'Dev Login'}
                        </Button>

                        <Button className="w-full" variant="outline" onClick={handleGoogleLogin}>
                            Sign in with Google
                        </Button>

                        <button
                            type="button"
                            className="w-full text-center text-sm text-muted-foreground hover:text-foreground underline"
                            onClick={logout}
                        >
                            Log out instead
                        </button>
                    </div>
                </Dialog.Content>
            </Dialog.Portal>
        </Dialog.Root>
    );
}
