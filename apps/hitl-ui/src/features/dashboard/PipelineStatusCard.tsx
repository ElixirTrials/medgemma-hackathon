import { AlertCircle, Loader2 } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

import { usePipelineSummary } from '../../hooks/useReviews';

function formatStatus(status: string): string {
    return status.replace(/_/g, ' ');
}

export function PipelineStatusCard() {
    const { data, isLoading, error } = usePipelineSummary();
    const navigate = useNavigate();

    if (isLoading) {
        return (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading pipeline status...
            </div>
        );
    }

    if (error) {
        return <p className="text-sm text-muted-foreground">Could not load pipeline status.</p>;
    }

    if (!data) {
        return null;
    }

    const { criteria_extracted, protocols_in_grounding, error_count, error_protocols } = data;

    return (
        <div className="space-y-4">
            <p className="text-sm text-foreground">
                <span className="font-medium">{criteria_extracted}</span> criteria extracted
            </p>
            <p className="text-sm text-foreground">
                <span className="font-medium">{protocols_in_grounding}</span> protocol
                {protocols_in_grounding === 1 ? '' : 's'} currently in grounding
            </p>
            <div>
                {error_count > 0 ? (
                    <>
                        <p className="text-sm text-foreground mb-2">
                            <span className="font-medium text-destructive">{error_count}</span>{' '}
                            protocol{error_count === 1 ? '' : 's'} with errors
                        </p>
                        {error_protocols.length > 0 && (
                            <ul className="space-y-1 mb-2">
                                {error_protocols.map((p) => (
                                    <li key={p.id}>
                                        <Link
                                            to={`/protocols/${p.id}`}
                                            className="text-sm text-primary hover:underline flex items-center gap-1"
                                        >
                                            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                                            <span className="truncate" title={p.title}>
                                                {p.title}
                                            </span>
                                            <span className="text-muted-foreground text-xs shrink-0">
                                                ({formatStatus(p.status)})
                                            </span>
                                        </Link>
                                    </li>
                                ))}
                            </ul>
                        )}
                        <button
                            type="button"
                            onClick={() => navigate('/protocols')}
                            className="text-sm text-primary hover:underline"
                        >
                            View all protocols
                        </button>
                    </>
                ) : (
                    <p className="text-sm text-muted-foreground">No errors</p>
                )}
            </div>
        </div>
    );
}
