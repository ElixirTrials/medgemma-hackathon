import { CheckCircle, Edit2, GitCommit, Loader2, XCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { type AuditLogEntry, useAuditLog } from '../../hooks/useReviews';

function formatRelativeTime(dateStr: string): string {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHr = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHr / 24);

    if (diffSec < 60) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffHr < 24) return `${diffHr}h ago`;
    if (diffDay < 30) return `${diffDay}d ago`;
    return date.toLocaleDateString();
}

function getEventIcon(eventType: string, action: string | undefined) {
    if (eventType === 'protocol_status_change') {
        return <GitCommit className="h-4 w-4 text-blue-500" />;
    }
    if (action === 'approve') {
        return <CheckCircle className="h-4 w-4 text-green-500" />;
    }
    if (action === 'reject') {
        return <XCircle className="h-4 w-4 text-red-500" />;
    }
    if (action === 'modify') {
        return <Edit2 className="h-4 w-4 text-yellow-500" />;
    }
    return <GitCommit className="h-4 w-4 text-muted-foreground" />;
}

function formatAction(entry: AuditLogEntry): string {
    if (entry.event_type === 'protocol_status_change') {
        const title = String(entry.details.protocol_title ?? '').slice(0, 40);
        const newStatus = String(entry.details.new_status ?? '').replace(/_/g, ' ');
        return `${title} → ${newStatus}`;
    }
    if (entry.event_type === 'review_action') {
        const action = String(entry.details.action ?? '');
        const afterValue = entry.details.after_value as Record<string, unknown> | undefined;
        const text = String(afterValue?.text ?? '');
        const preview = text.length > 60 ? `${text.slice(0, 60)}...` : text;
        return `${action}: "${preview}"`;
    }
    return entry.event_type;
}

export function ActivityFeed() {
    const { data, isLoading, error } = useAuditLog(1, 20);
    const navigate = useNavigate();

    if (isLoading) {
        return (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading activity...
            </div>
        );
    }

    if (error) {
        return <p className="text-sm text-muted-foreground">Could not load activity.</p>;
    }

    if (!data || data.items.length === 0) {
        return <p className="text-sm text-muted-foreground">No recent activity</p>;
    }

    return (
        <ul className="space-y-2">
            {data.items.map((entry) => {
                const action = entry.details.action as string | undefined;
                const icon = getEventIcon(entry.event_type, action);
                const description = formatAction(entry);

                const handleClick = () => {
                    if (entry.event_type === 'protocol_status_change' && entry.target_id) {
                        navigate(`/protocols/${entry.target_id}`);
                    } else {
                        navigate('/reviews');
                    }
                };

                return (
                    <li key={entry.id}>
                        <button
                            type="button"
                            className="flex w-full items-start gap-2 text-sm text-left cursor-pointer hover:bg-muted/30 rounded px-1 py-1 transition-colors"
                            onClick={handleClick}
                        >
                            <span className="shrink-0 mt-0.5">{icon}</span>
                            <div>
                                <p className="truncate">{description}</p>
                                <p className="text-xs text-muted-foreground">
                                    {formatRelativeTime(entry.created_at)}
                                </p>
                            </div>
                        </button>
                    </li>
                );
            })}
        </ul>
    );
}
