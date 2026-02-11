import { Search as SearchIcon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { Button } from '../components/ui/Button';
import { DashboardCard } from '../features/dashboard/DashboardCard';
import { useHealthCheck } from '../hooks/useApi';
import { useBatchList } from '../hooks/useReviews';
import { useAppStore } from '../stores/useAppStore';

export default function Dashboard() {
    const { data: health, isLoading, error } = useHealthCheck();
    const { data: pendingBatches } = useBatchList(1, 1, 'pending_review');
    const { sidebarOpen, toggleSidebar } = useAppStore();
    const navigate = useNavigate();

    const pendingCount = pendingBatches?.total ?? 0;

    return (
        <div className="container mx-auto p-6">
            <header className="mb-8">
                <div className="flex items-center justify-between">
                    <h1 className="text-3xl font-bold text-foreground">
                        Human in the Loop Dashboard
                    </h1>
                    <Button onClick={toggleSidebar} variant="outline">
                        {sidebarOpen ? 'Close Sidebar' : 'Open Sidebar'}
                    </Button>
                </div>
                <p className="mt-2 text-muted-foreground">
                    Review and approve AI-generated content
                </p>
            </header>

            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                <DashboardCard
                    title="System Status"
                    description="Current health of the backend services"
                >
                    {isLoading && <p className="text-muted-foreground">Checking health...</p>}
                    {error && (
                        <p className="text-destructive">Error: Unable to connect to backend</p>
                    )}
                    {health && (
                        <div className="flex items-center gap-2">
                            <span
                                className={`h-3 w-3 rounded-full ${
                                    health.status === 'healthy' ? 'bg-green-500' : 'bg-red-500'
                                }`}
                            />
                            <span className="font-medium capitalize">{health.status}</span>
                        </div>
                    )}
                </DashboardCard>

                <DashboardCard title="Pending Reviews" description="Items awaiting human approval">
                    <p className="text-2xl font-bold">{pendingCount}</p>
                    <p className="text-sm text-muted-foreground mb-3">
                        {pendingCount === 0
                            ? 'No pending items'
                            : `${pendingCount} batch${pendingCount === 1 ? '' : 'es'} awaiting review`}
                    </p>
                    <Button
                        onClick={() => navigate('/reviews')}
                        variant="outline"
                        className="w-full"
                    >
                        Review Criteria
                    </Button>
                </DashboardCard>

                <DashboardCard title="Protocols" description="Manage clinical trial protocols">
                    <Button
                        onClick={() => navigate('/protocols')}
                        variant="outline"
                        className="w-full"
                    >
                        View Protocols
                    </Button>
                </DashboardCard>

                <DashboardCard title="Search" description="Search across all criteria">
                    <Button
                        onClick={() => navigate('/search')}
                        variant="outline"
                        className="w-full"
                    >
                        <SearchIcon className="h-4 w-4 mr-2" />
                        Search Criteria
                    </Button>
                </DashboardCard>

                <DashboardCard
                    title="Recent Activity"
                    description="Latest approvals and rejections"
                >
                    <p className="text-muted-foreground">No recent activity</p>
                </DashboardCard>
            </div>
        </div>
    );
}
