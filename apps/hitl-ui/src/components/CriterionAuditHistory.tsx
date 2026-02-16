import { useState } from 'react';
import * as Collapsible from '@radix-ui/react-collapsible';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { useAuditLog } from '../hooks/useReviews';

interface CriterionAuditHistoryProps {
    criterionId: string;
}

export function CriterionAuditHistory({ criterionId }: CriterionAuditHistoryProps) {
    const [open, setOpen] = useState(false);
    const { data: auditData, isLoading } = useAuditLog(
        1,
        20,
        'criteria',
        criterionId
    );

    const entryCount = auditData?.total ?? 0;

    return (
        <Collapsible.Root open={open} onOpenChange={setOpen} className="mt-3 border-t pt-3">
            <Collapsible.Trigger asChild>
                <button
                    className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                    aria-label={`Show audit history (${entryCount} entries)`}
                >
                    {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    <span>History ({entryCount})</span>
                </button>
            </Collapsible.Trigger>

            <Collapsible.Content className="mt-2 space-y-2">
                {isLoading ? (
                    <p className="text-sm text-muted-foreground">Loading history...</p>
                ) : entryCount === 0 ? (
                    <p className="text-sm text-muted-foreground">No audit entries yet</p>
                ) : (
                    auditData?.items.map((entry) => {
                        const details = entry.details as { action?: string; rationale?: string };
                        return (
                            <div
                                key={entry.id}
                                className="flex items-start justify-between gap-3 text-sm border-l-2 border-muted pl-3 py-1.5"
                            >
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-baseline gap-1.5">
                                        <span className="font-medium">
                                            {formatAction(details.action ?? '')}
                                        </span>
                                        <span className="text-muted-foreground text-xs">
                                            by {formatActor(entry.actor_id)}
                                        </span>
                                    </div>
                                    {details.rationale && (
                                        <p className="text-xs text-muted-foreground mt-1 italic">
                                            "{details.rationale}"
                                        </p>
                                    )}
                                </div>
                                <time className="text-xs text-muted-foreground whitespace-nowrap flex-shrink-0">
                                    {formatTimestamp(entry.created_at)}
                                </time>
                            </div>
                        );
                    })
                )}
            </Collapsible.Content>
        </Collapsible.Root>
    );
}

function formatAction(action: string): string {
    const actions: Record<string, string> = {
        approve: 'Approved',
        reject: 'Rejected',
        modify: 'Modified',
    };
    return actions[action] || action;
}

function formatActor(actorId: string | null): string {
    if (!actorId) return 'System';
    // Extract email username for cleaner display
    const match = actorId.match(/^([^@]+)/);
    return match ? match[1] : actorId;
}

function formatTimestamp(dateStr: string): string {
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}
