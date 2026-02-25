/// <reference types="vite/client" />
declare const __ROUTER_BASENAME__: string;

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { Component, type ReactNode, StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import App from './App';
import './index.css';
import { SessionExpiredError } from './lib/fetchApi';
import { useAuthStore } from './stores/authStore';

const routerBasename =
    typeof __ROUTER_BASENAME__ !== 'undefined' && typeof __ROUTER_BASENAME__ === 'string'
        ? __ROUTER_BASENAME__
        : '/';

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
    state = { error: null as Error | null };

    static getDerivedStateFromError(error: Error) {
        return { error };
    }

    render() {
        if (this.state.error) {
            return (
                <div style={{ padding: 24, fontFamily: 'sans-serif', maxWidth: 600 }}>
                    <h1 style={{ color: '#b91c1c' }}>Something went wrong</h1>
                    <pre style={{ background: '#fef2f2', padding: 16, overflow: 'auto' }}>
                        {this.state.error.message}
                    </pre>
                    <p style={{ color: '#666' }}>Check the browser console for the full stack.</p>
                </div>
            );
        }
        return this.props.children;
    }
}

const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 1000 * 60 * 5, // 5 minutes
            retry: (failureCount, error) => {
                // Never retry auth errors
                if (error instanceof SessionExpiredError) return false;
                return failureCount < 1;
            },
        },
    },
});

// When session expires, cancel all in-flight queries.
// When session is restored, invalidate all queries to refetch.
useAuthStore.subscribe((state, prev) => {
    if (state.isSessionExpired && !prev.isSessionExpired) {
        queryClient.cancelQueries();
    }
    if (!state.isSessionExpired && prev.isSessionExpired) {
        queryClient.invalidateQueries();
    }
});

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Root element not found');

createRoot(rootElement).render(
    <StrictMode>
        <ErrorBoundary>
            <QueryClientProvider client={queryClient}>
                <BrowserRouter basename={routerBasename}>
                    <App />
                </BrowserRouter>
                <ReactQueryDevtools initialIsOpen={false} />
            </QueryClientProvider>
        </ErrorBoundary>
    </StrictMode>
);
