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
import { Button } from './ui/Button';

interface EntityCardProps {
    entity: EntityResponse;
    onAction: (entityId: string, action: EntityActionRequest) => void;
    isSubmitting: boolean;
}

function EntityTypeBadge({ type }: { type: string }) {
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

function GroundingConfidenceBadge({ confidence }: { confidence: number | null }) {
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

function ReviewStatusBadge({ status }: { status: string | null }) {
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

export default function EntityCard({ entity, onAction, isSubmitting }: EntityCardProps) {
    const [isEditing, setIsEditing] = useState(false);
    const [contextOpen, setContextOpen] = useState(false);
    const [editCui, setEditCui] = useState(entity.umls_cui ?? '');
    const [editSnomed, setEditSnomed] = useState(entity.snomed_code ?? '');
    const [editPreferredTerm, setEditPreferredTerm] = useState(entity.preferred_term ?? '');

    const isLowConfidence = (entity.grounding_confidence ?? 0) < 0.7;

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

    function handleModifySave() {
        onAction(entity.id, {
            action: 'modify',
            reviewer_id: 'current-user',
            modified_umls_cui: editCui || undefined,
            modified_snomed_code: editSnomed || undefined,
            modified_preferred_term: editPreferredTerm || undefined,
        });
        setIsEditing(false);
    }

    function handleModifyCancel() {
        setEditCui(entity.umls_cui ?? '');
        setEditSnomed(entity.snomed_code ?? '');
        setEditPreferredTerm(entity.preferred_term ?? '');
        setIsEditing(false);
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

            {/* SNOMED Badge */}
            {entity.snomed_code && entity.preferred_term && (
                <div className="mb-2">
                    <span className="inline-flex items-center rounded-full bg-blue-100 px-3 py-1 text-sm font-medium text-blue-800">
                        SNOMED: {entity.snomed_code} - {entity.preferred_term}
                    </span>
                </div>
            )}

            {/* UMLS Badge with link */}
            {entity.umls_cui && (
                <div className="mb-3">
                    <a
                        href={`https://uts.nlm.nih.gov/cts/umls/concept/${entity.umls_cui}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-3 py-1 text-sm font-medium text-indigo-800 hover:bg-indigo-200 transition-colors"
                    >
                        CUI: {entity.umls_cui}
                        <ExternalLink className="h-3 w-3" />
                    </a>
                </div>
            )}

            {/* Modify mode */}
            {isEditing && (
                <div className="space-y-3 mb-3 border-t pt-3">
                    <div>
                        <label
                            htmlFor={`edit-cui-${entity.id}`}
                            className="block text-sm font-medium text-muted-foreground mb-1"
                        >
                            UMLS CUI
                        </label>
                        <input
                            id={`edit-cui-${entity.id}`}
                            type="text"
                            value={editCui}
                            onChange={(e) => setEditCui(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        />
                    </div>
                    <div>
                        <label
                            htmlFor={`edit-snomed-${entity.id}`}
                            className="block text-sm font-medium text-muted-foreground mb-1"
                        >
                            SNOMED Code
                        </label>
                        <input
                            id={`edit-snomed-${entity.id}`}
                            type="text"
                            value={editSnomed}
                            onChange={(e) => setEditSnomed(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        />
                    </div>
                    <div>
                        <label
                            htmlFor={`edit-term-${entity.id}`}
                            className="block text-sm font-medium text-muted-foreground mb-1"
                        >
                            Preferred Term
                        </label>
                        <input
                            id={`edit-term-${entity.id}`}
                            type="text"
                            value={editPreferredTerm}
                            onChange={(e) => setEditPreferredTerm(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        />
                    </div>
                    <div className="flex items-center gap-2">
                        <Button size="sm" onClick={handleModifySave} disabled={isSubmitting}>
                            {isSubmitting ? (
                                <Loader2 className="h-4 w-4 animate-spin mr-1" />
                            ) : null}
                            Save
                        </Button>
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={handleModifyCancel}
                            disabled={isSubmitting}
                        >
                            Cancel
                        </Button>
                    </div>
                </div>
            )}

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
            {!isEditing && (
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
                        onClick={() => setIsEditing(true)}
                        disabled={isSubmitting}
                    >
                        <Pencil className="h-4 w-4 mr-1" />
                        Modify
                    </Button>
                </div>
            )}
        </div>
    );
}
