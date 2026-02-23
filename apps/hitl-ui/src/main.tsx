import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import App from './App';
import './index.css';
import { SessionExpiredError } from './lib/fetchApi';
import { useAuthStore } from './stores/authStore';

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
        <QueryClientProvider client={queryClient}>
            <BrowserRouter basename="/demo-app">
                <App />
            </BrowserRouter>
            <ReactQueryDevtools initialIsOpen={false} />
        </QueryClientProvider>
    </StrictMode>
);
