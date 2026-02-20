import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Button } from '../components/ui/Button';
import { useAuth } from '../hooks/useAuth';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function LoginPage() {
    const { isAuthenticated, login, setAuth } = useAuth();
    const navigate = useNavigate();
    const [devLoading, setDevLoading] = useState(false);
    const [devError, setDevError] = useState<string | null>(null);

    useEffect(() => {
        if (isAuthenticated) {
            navigate('/');
        }
    }, [isAuthenticated, navigate]);

    const handleDevLogin = async () => {
        setDevLoading(true);
        setDevError(null);
        try {
            const res = await fetch(`${API_BASE_URL}/auth/dev-login`, { method: 'POST' });
            if (!res.ok) {
                throw new Error(
                    res.status === 404 ? 'Dev login not enabled on server' : `Error ${res.status}`
                );
            }
            const data = await res.json();
            setAuth(data.access_token, data.user);
        } catch (e) {
            setDevError(e instanceof Error ? e.message : 'Dev login failed');
        } finally {
            setDevLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-background">
            <div className="max-w-md w-full space-y-8 p-8">
                <div className="text-center">
                    <h1 className="text-4xl font-bold text-foreground mb-2">
                        Clinical Trial HITL System
                    </h1>
                    <p className="text-muted-foreground">
                        Review AI-extracted eligibility criteria and entity mappings
                    </p>
                </div>

                <div className="rounded-lg border bg-card p-8 shadow-sm space-y-6">
                    <div>
                        <h2 className="text-xl font-semibold text-foreground mb-2">Sign In</h2>
                        <p className="text-sm text-muted-foreground">
                            Use your Google account to access the review system
                        </p>
                    </div>

                    <Button onClick={login} className="w-full" size="lg">
                        <svg
                            className="w-5 h-5 mr-2"
                            viewBox="0 0 24 24"
                            role="img"
                            aria-label="Google logo"
                        >
                            <path
                                fill="currentColor"
                                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                            />
                            <path
                                fill="currentColor"
                                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                            />
                            <path
                                fill="currentColor"
                                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                            />
                            <path
                                fill="currentColor"
                                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                            />
                        </svg>
                        Sign in with Google
                    </Button>

                    <div className="pt-4 border-t space-y-3">
                        <Button
                            onClick={handleDevLogin}
                            variant="outline"
                            className="w-full"
                            size="lg"
                            disabled={devLoading}
                        >
                            {devLoading ? 'Signing in...' : 'Dev Login (local only)'}
                        </Button>
                        {devError && <p className="text-sm text-red-500 text-center">{devError}</p>}
                    </div>

                    <div className="pt-2 text-center">
                        <p className="text-xs text-muted-foreground">
                            By signing in, you agree to review and approve AI-generated content
                            according to the project guidelines.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
