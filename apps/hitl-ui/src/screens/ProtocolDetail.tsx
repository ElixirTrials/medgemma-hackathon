import { AlertTriangle, ArrowLeft, Check, Copy, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { Button } from '../components/ui/Button';
import { useProtocol } from '../hooks/useProtocols';
import { cn } from '../lib/utils';

const STATUS_COLORS: Record<string, string> = {
    uploaded: 'bg-blue-100 text-blue-800',
    extracting: 'bg-yellow-100 text-yellow-800',
    extracted: 'bg-green-100 text-green-800',
    reviewed: 'bg-purple-100 text-purple-800',
};

function StatusBadge({ status }: { status: string }) {
    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize',
                STATUS_COLORS[status] ?? 'bg-gray-100 text-gray-800'
            )}
        >
            {status}
        </span>
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
    const { data: protocol, isLoading, error } = useProtocol(id ?? '');

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
                        <span className="capitalize">{encodingType ?? 'Not available'}</span>
                    </InfoItem>

                    <InfoItem label="Text Extractability">
                        {textExtractability !== undefined
                            ? `${Math.round(textExtractability * 100)}%`
                            : 'Not available'}
                    </InfoItem>
                </dl>
            </div>

            {/* Actions */}
            <div className="mt-6">
                <Button variant="outline" asChild>
                    <Link to="/protocols">Back to List</Link>
                </Button>
            </div>
        </div>
    );
}
