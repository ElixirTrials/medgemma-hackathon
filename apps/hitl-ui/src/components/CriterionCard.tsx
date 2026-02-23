import { CheckCircle, Clock, Hash, Loader2, Pencil, Wand2, XCircle } from 'lucide-react';
import { useState } from 'react';

import type { Criterion, ReviewActionRequest } from '../hooks/useReviews';
import { cn } from '../lib/utils';
import { CriterionAuditHistory } from './CriterionAuditHistory';
import CriterionModifyDialog from './CriterionModifyDialog';
import { CriterionRerunPanel } from './CriterionRerunPanel';
import FieldMappingBadges from './FieldMappingBadges';
import RejectDialog from './RejectDialog';
import {
    buildInitialValues,
    extractThresholdsList,
    formatNumericThreshold,
    formatTemporalConstraint,
    normalizeFieldValue,
    normalizeRelation,
} from './fieldMappingUtils';
import { Button } from './ui/Button';

// Re-export utility functions so existing imports from CriterionCard continue to work
export {
    buildInitialValues,
    extractThresholdsList,
    formatNumericThreshold,
    formatTemporalConstraint,
    normalizeFieldValue,
    normalizeRelation,
};

interface CriterionCardProps {
    criterion: Criterion;
    onAction: (criterionId: string, action: ReviewActionRequest) => void;
    isSubmitting: boolean;
    onCriterionClick?: (criterion: Criterion) => void;
    isActive?: boolean;
    pdfUrl?: string;
}

export function ConfidenceBadge({ confidence }: { confidence: number }) {
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
        >
            {label} ({percentage}%)
        </span>
    );
}

export function CriterionReviewStatusBadge({ status }: { status: string | null }) {
    const statusConfig: Record<string, { label: string; colorClass: string }> = {
        approved: { label: 'Approved', colorClass: 'bg-green-100 text-green-800' },
        rejected: { label: 'Rejected', colorClass: 'bg-red-100 text-red-800' },
        modified: { label: 'Modified', colorClass: 'bg-blue-100 text-blue-800' },
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

export function CriteriaTypeBadge({ type }: { type: string }) {
    const colorClass =
        type === 'inclusion' ? 'bg-blue-100 text-blue-800' : 'bg-orange-100 text-orange-800';

    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize',
                colorClass
            )}
        >
            {type}
        </span>
    );
}

export default function CriterionCard({
    criterion,
    onAction,
    isSubmitting,
    onCriterionClick,
    isActive,
    pdfUrl,
}: CriterionCardProps) {
    const [modifyDialogOpen, setModifyDialogOpen] = useState(false);
    const [rejectDialogOpen, setRejectDialogOpen] = useState(false);

    function handleApprove() {
        onAction(criterion.id, {
            action: 'approve',
            reviewer_id: 'current-user',
        });
    }

    function handleReject() {
        setRejectDialogOpen(true);
    }

    function handleRejectConfirm(data: { reasons: string[]; comment?: string }) {
        onAction(criterion.id, {
            action: 'reject',
            reviewer_id: 'current-user',
            reject_reasons: data.reasons,
            comment: data.comment,
        });
    }

    return (
        <div
            className={cn(
                'rounded-lg border bg-card p-4 shadow-sm border-l-4',
                criterion.review_status === 'approved' && 'border-l-green-500',
                criterion.review_status === 'rejected' && 'border-l-red-500',
                criterion.review_status === 'modified' && 'border-l-blue-500',
                !criterion.review_status && 'border-l-yellow-400'
            )}
        >
            {/* Header row */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
                <CriteriaTypeBadge type={criterion.criteria_type} />
                {criterion.category && (
                    <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-700">
                        {criterion.category}
                    </span>
                )}
                <ConfidenceBadge confidence={criterion.confidence} />
                <CriterionReviewStatusBadge status={criterion.review_status} />
                {criterion.page_number != null && (
                    <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 ml-auto">
                        p.{criterion.page_number}
                    </span>
                )}
            </div>

            {/* Body - criterion text (read-only, clickable for PDF navigation) */}
            <p
                className={cn(
                    'text-sm text-foreground mb-3',
                    criterion.page_number != null &&
                        'cursor-pointer hover:bg-accent/50 rounded px-1 -mx-1 transition-colors',
                    isActive && 'bg-accent/30 rounded px-1 -mx-1'
                )}
                onClick={() => {
                    if (criterion.page_number != null && onCriterionClick) {
                        onCriterionClick(criterion);
                    }
                }}
                onKeyDown={(e) => {
                    if (
                        (e.key === 'Enter' || e.key === ' ') &&
                        criterion.page_number != null &&
                        onCriterionClick
                    ) {
                        onCriterionClick(criterion);
                    }
                }}
                role={criterion.page_number != null ? 'button' : undefined}
                tabIndex={criterion.page_number != null ? 0 : undefined}
                title={
                    criterion.page_number != null
                        ? `Click to view source (page ${criterion.page_number})`
                        : undefined
                }
            >
                {criterion.text}
            </p>

            {/* Field mapping badges */}
            <FieldMappingBadges
                criterion={criterion}
                onEditClick={() => setModifyDialogOpen(true)}
            />

            {/* Assertion status tag */}
            {criterion.assertion_status && criterion.assertion_status !== 'PRESENT' && (
                <div className="mb-3">
                    <span className="inline-flex items-center rounded-full bg-purple-100 px-2.5 py-0.5 text-xs font-medium text-purple-800">
                        {criterion.assertion_status}
                    </span>
                </div>
            )}

            {/* Temporal constraint */}
            {criterion.temporal_constraint &&
                formatTemporalConstraint(criterion.temporal_constraint) && (
                    <div className="mb-3 flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5 text-indigo-600" />
                        <span className="inline-flex items-center rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-medium text-indigo-800">
                            {formatTemporalConstraint(criterion.temporal_constraint)}
                        </span>
                    </div>
                )}

            {/* Numeric thresholds */}
            {extractThresholdsList(criterion.numeric_thresholds).length > 0 && (
                <div className="mb-3 flex flex-wrap items-center gap-1.5">
                    <Hash className="h-3.5 w-3.5 text-teal-600" />
                    {extractThresholdsList(criterion.numeric_thresholds).map((threshold) => {
                        const text = formatNumericThreshold(threshold);
                        return text ? (
                            <span
                                key={text}
                                className="inline-flex items-center rounded-full bg-teal-100 px-2.5 py-0.5 text-xs font-medium text-teal-800"
                            >
                                {text}
                            </span>
                        ) : null;
                    })}
                </div>
            )}

            {/* Action buttons */}
            <div className="flex items-center gap-2 pt-2 border-t">
                <Button
                    size="sm"
                    variant="outline"
                    className="text-green-700 border-green-300 hover:bg-green-50"
                    onClick={handleApprove}
                    disabled={isSubmitting || criterion.review_status === 'approved'}
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
                    disabled={isSubmitting || criterion.review_status === 'rejected'}
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
                <CriterionRerunPanel
                    criterionId={criterion.id}
                    criterionText={criterion.text}
                    currentExtraction={{
                        criteria_type: criterion.criteria_type,
                        category: criterion.category,
                        temporal_constraint: criterion.temporal_constraint,
                        conditions: criterion.conditions,
                        numeric_thresholds: criterion.numeric_thresholds,
                        text: criterion.text,
                    }}
                    onAccept={(revised) => {
                        onAction(criterion.id, {
                            action: 'modify',
                            reviewer_id: 'current-user',
                            modified_text: revised.text as string | undefined,
                            modified_type: revised.criteria_type as string | undefined,
                            modified_category: revised.category as string | undefined,
                            modified_structured_fields: revised,
                            comment: 'AI-assisted correction with reviewer feedback',
                        });
                    }}
                    trigger={
                        <Button
                            size="sm"
                            variant="outline"
                            className="text-purple-700 border-purple-300 hover:bg-purple-50"
                            disabled={isSubmitting}
                        >
                            <Wand2 className="h-4 w-4 mr-1" />
                            Correct with AI
                        </Button>
                    }
                />
            </div>

            {/* Audit history section */}
            <CriterionAuditHistory criterionId={criterion.id} />

            <RejectDialog
                open={rejectDialogOpen}
                onOpenChange={setRejectDialogOpen}
                onConfirm={handleRejectConfirm}
            />

            <CriterionModifyDialog
                open={modifyDialogOpen}
                onOpenChange={setModifyDialogOpen}
                criterion={criterion}
                onAction={(action) => onAction(criterion.id, action)}
                isSubmitting={isSubmitting}
                pdfUrl={pdfUrl}
            />
        </div>
    );
}
