import { Route, Routes } from 'react-router-dom';

import { LogOut, User } from 'lucide-react';
import { Button } from './components/ui/Button';
import { useAuth } from './hooks/useAuth';
import Dashboard from './screens/Dashboard';
import EntityList from './screens/EntityList';
import LoginPage from './screens/LoginPage';
import ProtocolDetail from './screens/ProtocolDetail';
import ProtocolList from './screens/ProtocolList';
import ReviewPage from './screens/ReviewPage';
import ReviewQueue from './screens/ReviewQueue';
import SearchPage from './screens/SearchPage';

function App() {
    const { isAuthenticated, user, logout } = useAuth();

    return (
        <div className="min-h-screen bg-background">
            {/* Navigation header when authenticated */}
            {isAuthenticated && (
                <header className="border-b bg-card">
                    <div className="container mx-auto px-6 py-3 flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <h1 className="text-lg font-semibold">HITL System</h1>
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
                <Route path="/" element={<Dashboard />} />
                <Route path="/protocols" element={<ProtocolList />} />
                <Route path="/protocols/:id" element={<ProtocolDetail />} />
                <Route path="/reviews" element={<ReviewQueue />} />
                <Route path="/reviews/:batchId" element={<ReviewPage />} />
                <Route path="/entities/:batchId" element={<EntityList />} />
                <Route path="/search" element={<SearchPage />} />
            </Routes>
        </div>
    );
}

export default App;
