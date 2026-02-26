import { Link, Navigate, Route, Routes } from 'react-router-dom';
import { Toaster } from 'sonner';

import { LogOut, User } from 'lucide-react';
import type { ReactNode } from 'react';
import { SessionExpiredModal } from './components/SessionExpiredModal';
import { Button } from './components/ui/Button';
import { useAuth } from './hooks/useAuth';
import CriteriaSpreadsheet from './screens/CriteriaSpreadsheet';
import Dashboard from './screens/Dashboard';
import EntityList from './screens/EntityList';
import LoginPage from './screens/LoginPage';
import ProtocolDetail from './screens/ProtocolDetail';
import ProtocolList from './screens/ProtocolList';
import ReviewPage from './screens/ReviewPage';
import ReviewQueue from './screens/ReviewQueue';
import SearchPage from './screens/SearchPage';

function RequireAuth({ children }: { children: ReactNode }) {
    const { isAuthenticated, isSessionExpired } = useAuth();
    // If session expired, keep showing children behind the modal overlay
    if (!isAuthenticated && !isSessionExpired) {
        return <Navigate to="/login" replace />;
    }
    return <>{children}</>;
}

function App() {
    const { isAuthenticated, user, logout } = useAuth();

    return (
        <div className="min-h-screen bg-background">
            {/* Navigation header when authenticated */}
            {isAuthenticated && (
                <header className="border-b bg-card">
                    <div className="container mx-auto px-6 py-3 flex items-center justify-between">
                        <div className="flex items-center gap-6">
                            <h1 className="text-lg font-semibold">GemmaCrit</h1>
                            <nav className="flex items-center gap-4 text-sm">
                                <Link
                                    to="/"
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    Dashboard
                                </Link>
                                <Link
                                    to="/protocols"
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    Protocols
                                </Link>
                                <Link
                                    to="/reviews"
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    Reviews
                                </Link>
                                <Link
                                    to="/criteria"
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    Criteria
                                </Link>
                                <Link
                                    to="/search"
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    Search
                                </Link>
                            </nav>
                        </div>
                        <div className="flex items-center gap-4">
                            {user && (
                                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                    <User className="h-4 w-4" />
                                    <span>{user.name || user.email}</span>
                                </div>
                            )}
                            <Button variant="outline" size="sm" onClick={logout}>
                                <LogOut className="h-4 w-4 mr-1" />
                                Logout
                            </Button>
                        </div>
                    </div>
                </header>
            )}

            <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/auth/login" element={<Navigate to="/login" replace />} />
                <Route path="/auth/callback" element={<Navigate to="/login" replace />} />
                <Route
                    path="/"
                    element={
                        <RequireAuth>
                            <Dashboard />
                        </RequireAuth>
                    }
                />
                <Route
                    path="/protocols"
                    element={
                        <RequireAuth>
                            <ProtocolList />
                        </RequireAuth>
                    }
                />
                <Route
                    path="/protocols/:id"
                    element={
                        <RequireAuth>
                            <ProtocolDetail />
                        </RequireAuth>
                    }
                />
                <Route
                    path="/reviews"
                    element={
                        <RequireAuth>
                            <ReviewQueue />
                        </RequireAuth>
                    }
                />
                <Route
                    path="/reviews/:batchId"
                    element={
                        <RequireAuth>
                            <ReviewPage />
                        </RequireAuth>
                    }
                />
                <Route
                    path="/entities/:batchId"
                    element={
                        <RequireAuth>
                            <EntityList />
                        </RequireAuth>
                    }
                />
                <Route
                    path="/criteria"
                    element={
                        <RequireAuth>
                            <CriteriaSpreadsheet />
                        </RequireAuth>
                    }
                />
                <Route
                    path="/search"
                    element={
                        <RequireAuth>
                            <SearchPage />
                        </RequireAuth>
                    }
                />
            </Routes>

            <SessionExpiredModal />
            <Toaster richColors position="top-right" />
        </div>
    );
}

export default App;
