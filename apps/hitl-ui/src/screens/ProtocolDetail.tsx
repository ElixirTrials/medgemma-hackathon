import { AlertTriangle, ArrowLeft, Check, ClipboardList, Copy, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { Button } from '../components/ui/Button';
import { useProtocol, useRetryProtocol } from '../hooks/useProtocols';
import { useBatchesByProtocol } from '../hooks/useReviews';
import { cn } from '../lib/utils';

const STATUS_COLORS: Record<string, string> = {
    uploaded: 'bg-blue-100 text-blue-800',
    extracting: 'bg-yellow-100 text-yellow-800',
    extraction_failed: 'bg-red-100 text-red-800',
    grounding: 'bg-cyan-100 text-cyan-800',
    grounding_failed: 'bg-orange-100 text-orange-800',
    pending_review: 'bg-indigo-100 text-indigo-800',
    complete: 'bg-green-100 text-green-800',
    dead_letter: 'bg-red-200 text-red-900',
    archived: 'bg-gray-100 text-gray-500',
    extracted: 'bg-green-100 text-green-800',
    reviewed: 'bg-purple-100 text-purple-800',
};

const STATUS_LABELS: Record<string, string> = {
    uploaded: 'Uploaded',
    extracting: 'Extracting',
    extraction_failed: 'Extraction Failed',
    grounding: 'Grounding',
    grounding_failed: 'Grounding Failed',
    pending_review: 'Pending Review',
    complete: 'Complete',
    dead_letter: 'Dead Letter',
    archived: 'Archived',
    extracted: 'Extracted',
    reviewed: 'Reviewed',
};

function StatusBadge({ status }: { status: string }) {
    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
                STATUS_COLORS[status] ?? 'bg-gray-100 text-gray-800'
            )}
        >
            {STATUS_LABELS[status] ?? status}
        </span>
    );
}

function RetryButton({ protocolId }: { protocolId: string }) {
    const retryMutation = useRetryProtocol();

    return (
        <Button
            variant="outline"
            size="sm"
            onClick={(e) => {
                e.stopPropagation();
                retryMutation.mutate(protocolId);
            }}
            disabled={retryMutation.isPending}
            className="border-red-300 text-red-700 hover:bg-red-100"
        >
            {retryMutation.isPending ? (
                <>
                    <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                    Retrying...
                </>
            ) : (
                'Retry Extraction'
            )}
        </Button>
    );
}

function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // Clipboard API may not be available
        }
    };

    return (
        <button
            type="button"
            onClick={handleCopy}
            className="inline-flex items-center text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Copy to clipboard"
        >
            {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
        </button>
    );
}

interface InfoItemProps {
    label: string;
    children: React.ReactNode;
}

function InfoItem({ label, children }: InfoItemProps) {
    return (
        <div className="space-y-1">
            <dt className="text-sm font-medium text-muted-foreground">{label}</dt>
            <dd className="text-sm text-foreground">{children}</dd>
        </div>
    );
}

function QualityBar({ score }: { score: number }) {
    const percentage = Math.round(score * 100);
    let barColor = 'bg-red-500';
    let textColor = 'text-red-600';
    if (score > 0.7) {
        barColor = 'bg-green-500';
        textColor = 'text-green-600';
    } else if (score >= 0.3) {
        barColor = 'bg-yellow-500';
        textColor = 'text-yellow-600';
    }

    return (
        <div className="flex items-center gap-3">
            <div className="h-2.5 w-32 rounded-full bg-muted overflow-hidden">
                <div
                    className={cn('h-full rounded-full transition-all', barColor)}
                    style={{ width: `${percentage}%` }}
                />
            </div>
            <span className={cn('text-sm font-semibold', textColor)}>{percentage}%</span>
        </div>
    );
}

export default function ProtocolDetail() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const { data: protocol, isLoading, error } = useProtocol(id ?? '');
    const { data: batchData } = useBatchesByProtocol(id ?? '');

    if (isLoading) {
        return (
            <div className="container mx-auto p-6 flex items-center justify-center py-16">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (error || !protocol) {
        return (
            <div className="container mx-auto p-6">
                <Link
                    to="/protocols"
                    className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-6"
                >
                    <ArrowLeft className="h-4 w-4 mr-1" />
                    Back to Protocols
                </Link>
                <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6 text-center">
                    <p className="text-destructive">Protocol not found</p>
                </div>
            </div>
        );
    }

    // Extract quality metadata safely
    const qualityMeta = (protocol.metadata_?.quality ?? {}) as Record<string, unknown>;
    const encodingType = qualityMeta.encoding_type as string | undefined;
    const textExtractability = qualityMeta.text_extractability as number | undefined;
    const isLowQuality = qualityMeta.is_low_quality as boolean | undefined;

    const truncatedUri =
        protocol.file_uri.length > 50
            ? `${protocol.file_uri.slice(0, 25)}...${protocol.file_uri.slice(-22)}`
            : protocol.file_uri;

    return (
        <div className="container mx-auto p-6">
            {/* Back link */}
            <Link
                to="/protocols"
                className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-6"
            >
                <ArrowLeft className="h-4 w-4 mr-1" />
                Back to Protocols
            </Link>

            {/* Title and status */}
            <div className="flex items-start justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-bold text-foreground mb-2">{protocol.title}</h1>
                    <StatusBadge status={protocol.status} />
                </div>
            </div>

            {/* Error Information */}
            {(protocol.status === 'extraction_failed' ||
                protocol.status === 'grounding_failed' ||
                protocol.status === 'dead_letter') && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-4 mb-6">
                    <div className="flex items-start justify-between">
                        <div>
                            <h3 className="text-sm font-semibold text-red-800">
                                {protocol.status === 'dead_letter'
                                    ? 'Processing Failed (Retries Exhausted)'
                                    : protocol.status === 'extraction_failed'
                                      ? 'Extraction Failed'
                                      : 'Grounding Failed'}
                            </h3>
                            <p className="mt-1 text-sm text-red-700">
                                {protocol.error_reason ??
                                    'An unknown error occurred during processing.'}
                            </p>
                            {protocol.status === 'dead_letter' && (
                                <p className="mt-1 text-xs text-red-600">
                                    This protocol will be archived after 7 days.
                                </p>
                            )}
                        </div>
                        <RetryButton protocolId={protocol.id} />
                    </div>
                </div>
            )}

            {/* Processing in progress banner */}
            {(protocol.status === 'uploaded' || protocol.status === 'extracting') && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 mb-6">
                    <p className="text-sm text-blue-700">
                        Processing in progress. This typically takes 2-5 minutes.
                    </p>
                </div>
            )}

            {/* Low quality warning */}
            {isLowQuality && (
                <div className="mb-6 flex items-start gap-3 rounded-lg border border-yellow-300 bg-yellow-50 p-4">
                    <AlertTriangle className="h-5 w-5 text-yellow-600 mt-0.5 shrink-0" />
                    <p className="text-sm text-yellow-800">
                        This PDF has low quality. Extraction results may be unreliable.
                    </p>
                </div>
            )}

            {/* Info grid */}
            <div className="rounded-lg border bg-card p-6 shadow-sm">
                <dl className="grid gap-6 md:grid-cols-2">
                    <InfoItem label="File URI">
                        <div className="flex items-center gap-2">
                            <span className="font-mono text-xs truncate" title={protocol.file_uri}>
                                {truncatedUri}
                            </span>
                            <CopyButton text={protocol.file_uri} />
                        </div>
                    </InfoItem>

                    <InfoItem label="Upload Date">
                        {new Date(protocol.created_at).toLocaleString()}
                    </InfoItem>

                    <InfoItem label="Page Count">{protocol.page_count ?? 'Not available'}</InfoItem>

                    <InfoItem label="Quality Score">
                        {protocol.quality_score !== null ? (
                            <QualityBar score={protocol.quality_score} />
                        ) : (
                            'Not available'
                        )}
                    </InfoItem>

                    <InfoItem label="Encoding Type">
                        {encodingType ? (
                            <span className="capitalize">{encodingType}</span>
                        ) : (
                            'Not available'
                        )}
                    </InfoItem>

                    <InfoItem label="Text Extractability">
                        {textExtractability !== undefined
                            ? `${Math.round(textExtractability * 100)}%`
                            : 'Not available'}
                    </InfoItem>
                </dl>
            </div>

            {/* Actions */}
            <div className="mt-6 flex items-center gap-3">
                <Button variant="outline" asChild>
                    <Link to="/protocols">Back to List</Link>
                </Button>
                {batchData?.items?.[0] && (
                    <Button
                        onClick={() => navigate(`/reviews/${batchData.items[0].id}`)}
                    >
                        <ClipboardList className="h-4 w-4 mr-2" />
                        Review Criteria ({batchData.items[0].criteria_count})
                    </Button>
                )}
            </div>
        </div>
    );
}
