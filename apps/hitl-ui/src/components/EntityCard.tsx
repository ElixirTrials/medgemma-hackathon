import {
    CheckCircle,
    ChevronDown,
    ChevronUp,
    ExternalLink,
    Loader2,
    Pencil,
    XCircle,
} from 'lucide-react';
import { useState } from 'react';

import type { EntityActionRequest, EntityResponse } from '../hooks/useEntities';
import { cn } from '../lib/utils';
import EntityModifyDialog from './EntityModifyDialog';
import { ErrorBadge, TerminologyBadge } from './TerminologyBadge';
import { Button } from './ui/Button';

interface EntityCardProps {
    entity: EntityResponse;
    onAction: (entityId: string, action: EntityActionRequest) => void;
    isSubmitting: boolean;
}

export function EntityTypeBadge({ type }: { type: string }) {
    const typeConfig: Record<string, { label: string; colorClass: string }> = {
        Condition: { label: 'Condition', colorClass: 'bg-blue-100 text-blue-800' },
        Medication: { label: 'Medication', colorClass: 'bg-purple-100 text-purple-800' },
        Procedure: { label: 'Procedure', colorClass: 'bg-green-100 text-green-800' },
        Lab_Value: { label: 'Lab Value', colorClass: 'bg-orange-100 text-orange-800' },
        Demographic: { label: 'Demographic', colorClass: 'bg-gray-100 text-gray-800' },
        Biomarker: { label: 'Biomarker', colorClass: 'bg-teal-100 text-teal-800' },
    };

    const config = typeConfig[type] || { label: type, colorClass: 'bg-gray-100 text-gray-800' };

    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
                config.colorClass
            )}
        >
            {config.label}
        </span>
    );
}

export function GroundingConfidenceBadge({ confidence }: { confidence: number | null }) {
    if (confidence === null) {
        return (
            <span className="inline-flex items-center rounded-full bg-gray-100 text-gray-800 px-2.5 py-0.5 text-xs font-medium">
                No confidence
            </span>
        );
    }

    const percentage = Math.round(confidence * 100);

    let label: string;
    let colorClass: string;

    if (confidence >= 0.85) {
        label = 'High';
        colorClass = 'bg-green-100 text-green-800';
    } else if (confidence >= 0.7) {
        label = 'Medium';
        colorClass = 'bg-yellow-100 text-yellow-800';
    } else {
        label = 'Low';
        colorClass = 'bg-red-100 text-red-800';
    }

    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
                colorClass
            )}
            title={`Grounding confidence: ${percentage}%`}
        >
            {label} ({percentage}%)
        </span>
    );
}

export function ReviewStatusBadge({ status }: { status: string | null }) {
    const statusConfig: Record<string, { label: string; colorClass: string }> = {
        approved: { label: 'Approved', colorClass: 'bg-green-100 text-green-800' },
        rejected: { label: 'Rejected', colorClass: 'bg-red-100 text-red-800' },
        modified: { label: 'Modified', colorClass: 'bg-yellow-100 text-yellow-800' },
    };

    const config = status ? statusConfig[status] : null;
    const label = config?.label ?? 'Pending';
    const colorClass = config?.colorClass ?? 'bg-gray-100 text-gray-800';

    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
                colorClass
            )}
        >
            {label}
        </span>
    );
}

/** Determine which systems are relevant for a given entity type. */
export function getRelevantSystems(entityType: string): string[] {
    switch (entityType) {
        case 'Medication':
            return ['rxnorm', 'umls'];
        case 'Condition':
            return ['icd10', 'snomed', 'umls'];
        case 'Lab_Value':
            return ['loinc', 'umls'];
        case 'Biomarker':
            return ['hpo', 'umls'];
        default:
            return ['snomed', 'umls'];
    }
}

export default function EntityCard({ entity, onAction, isSubmitting }: EntityCardProps) {
    const [modifyDialogOpen, setModifyDialogOpen] = useState(false);
    const [contextOpen, setContextOpen] = useState(false);

    const isLowConfidence = (entity.grounding_confidence ?? 0) < 0.7;

    // Check if entity has any codes
    const hasCodes =
        entity.umls_cui ||
        entity.snomed_code ||
        entity.rxnorm_code ||
        entity.icd10_code ||
        entity.loinc_code ||
        entity.hpo_code;

    function handleApprove() {
        onAction(entity.id, {
            action: 'approve',
            reviewer_id: 'current-user',
        });
    }

    function handleReject() {
        onAction(entity.id, {
            action: 'reject',
            reviewer_id: 'current-user',
        });
    }

    const contextText = entity.context_window?.text as string | undefined;

    return (
        <div
            className={cn(
                'rounded-lg border bg-card p-4 shadow-sm',
                isLowConfidence && 'border-l-4 border-l-red-300'
            )}
        >
            {/* Header row */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
                <EntityTypeBadge type={entity.entity_type} />
                <GroundingConfidenceBadge confidence={entity.grounding_confidence} />
                <ReviewStatusBadge status={entity.review_status} />
                {entity.grounding_method && (
                    <span
                        className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-600"
                        title={`Grounding method: ${entity.grounding_method}`}
                    >
                        {entity.grounding_method}
                    </span>
                )}
            </div>

            {/* Entity text */}
            <p className="text-sm font-medium text-foreground mb-3">{entity.text}</p>

            {/* Multi-code badge section */}
            <div className="flex flex-wrap gap-1.5 mb-3">
                {entity.rxnorm_code && (
                    <TerminologyBadge system="rxnorm" code={entity.rxnorm_code} />
                )}
                {entity.icd10_code && <TerminologyBadge system="icd10" code={entity.icd10_code} />}
                {entity.snomed_code && (
                    <TerminologyBadge
                        system="snomed"
                        code={entity.snomed_code}
                        display={entity.preferred_term ?? undefined}
                    />
                )}
                {entity.loinc_code && <TerminologyBadge system="loinc" code={entity.loinc_code} />}
                {entity.hpo_code && <TerminologyBadge system="hpo" code={entity.hpo_code} />}
                {entity.umls_cui && (
                    <a
                        href={`https://uts.nlm.nih.gov/cts/umls/concept/${entity.umls_cui}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 rounded-full border border-indigo-300 bg-indigo-100 px-2.5 py-0.5 text-xs font-medium text-indigo-800 hover:bg-indigo-200 transition-colors"
                    >
                        CUI: {entity.umls_cui}
                        <ExternalLink className="h-3 w-3" />
                    </a>
                )}
                {entity.grounding_error && <ErrorBadge errorReason={entity.grounding_error} />}
                {!hasCodes && !entity.grounding_error && (
                    <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-500">
                        Not grounded
                    </span>
                )}
            </div>

            {/* Context window (collapsible) */}
            {contextText && (
                <div className="border-t pt-3 mb-3">
                    <button
                        type="button"
                        className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                        onClick={() => setContextOpen(!contextOpen)}
                    >
                        {contextOpen ? (
                            <ChevronUp className="h-4 w-4" />
                        ) : (
                            <ChevronDown className="h-4 w-4" />
                        )}
                        Context
                    </button>
                    {contextOpen && (
                        <p className="mt-2 text-xs text-muted-foreground bg-muted/30 rounded-md p-2">
                            {contextText}
                        </p>
                    )}
                </div>
            )}

            {/* Action buttons */}
            <div className="flex items-center gap-2 pt-2 border-t">
                <Button
                    size="sm"
                    variant="outline"
                    className="text-green-700 border-green-300 hover:bg-green-50"
                    onClick={handleApprove}
                    disabled={isSubmitting || entity.review_status === 'approved'}
                >
                    {isSubmitting ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    ) : (
                        <CheckCircle className="h-4 w-4 mr-1" />
                    )}
                    Approve
                </Button>
                <Button
                    size="sm"
                    variant="outline"
                    className="text-red-700 border-red-300 hover:bg-red-50"
                    onClick={handleReject}
                    disabled={isSubmitting || entity.review_status === 'rejected'}
                >
                    {isSubmitting ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    ) : (
                        <XCircle className="h-4 w-4 mr-1" />
                    )}
                    Reject
                </Button>
                <Button
                    size="sm"
                    variant="outline"
                    className="text-blue-700 border-blue-300 hover:bg-blue-50"
                    onClick={() => setModifyDialogOpen(true)}
                    disabled={isSubmitting}
                >
                    <Pencil className="h-4 w-4 mr-1" />
                    Modify
                </Button>
            </div>

            <EntityModifyDialog
                open={modifyDialogOpen}
                onOpenChange={setModifyDialogOpen}
                entity={entity}
                onSave={(payload) => {
                    onAction(entity.id, {
                        action: 'modify',
                        reviewer_id: 'current-user',
                        ...payload,
                    });
                }}
                isSubmitting={isSubmitting}
            />
        </div>
    );
}
