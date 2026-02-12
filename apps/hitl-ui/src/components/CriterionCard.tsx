import { CheckCircle, Clock, Hash, Loader2, Pencil, XCircle } from 'lucide-react';
import { useState } from 'react';

import type { Criterion, ReviewActionRequest } from '../hooks/useReviews';
import { cn } from '../lib/utils';
import { Button } from './ui/Button';

interface CriterionCardProps {
    criterion: Criterion;
    onAction: (criterionId: string, action: ReviewActionRequest) => void;
    isSubmitting: boolean;
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
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

function ReviewStatusBadge({ status }: { status: string | null }) {
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

function CriteriaTypeBadge({ type }: { type: string }) {
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

function formatTemporalConstraint(tc: Record<string, unknown>): string {
    const duration = 'duration' in tc ? (tc.duration as string) : null;
    const relation = 'relation' in tc ? (tc.relation as string) : null;
    const referencePoint = 'reference_point' in tc ? (tc.reference_point as string) : null;

    if (!duration) return '';

    const relationMap: Record<string, string> = {
        within: 'Within',
        before: 'Before',
        after: 'After',
        at_least: 'At least',
    };

    const relationText = relation ? (relationMap[relation] || relation) : '';
    const parts = [relationText, duration];
    if (referencePoint) parts.push('of', referencePoint);

    return parts.filter(Boolean).join(' ');
}

function formatNumericThreshold(threshold: Record<string, unknown>): string {
    const value = 'value' in threshold ? threshold.value : null;
    const unit = 'unit' in threshold ? (threshold.unit as string) : '';
    const comparator = 'comparator' in threshold ? (threshold.comparator as string) : '';
    const upperValue = 'upper_value' in threshold ? threshold.upper_value : null;

    if (value === null) return '';

    if (comparator === 'range' && upperValue !== null) {
        return `${value}-${upperValue} ${unit}`.trim();
    }

    return `${comparator}${value} ${unit}`.trim();
}

function extractThresholdsList(
    nt: Record<string, unknown> | null
): Array<Record<string, unknown>> {
    if (!nt) return [];

    // Shape 1: {"thresholds": [...]} wrapper object
    if ('thresholds' in nt && Array.isArray(nt.thresholds)) {
        return nt.thresholds as Array<Record<string, unknown>>;
    }

    // Shape 2: raw array stored directly
    if (Array.isArray(nt)) {
        return nt as Array<Record<string, unknown>>;
    }

    // Shape 3: single threshold object without wrapper
    if ('value' in nt && 'comparator' in nt) {
        return [nt];
    }

    return [];
}

export default function CriterionCard({ criterion, onAction, isSubmitting }: CriterionCardProps) {
    const [isEditing, setIsEditing] = useState(false);
    const [editText, setEditText] = useState(criterion.text);
    const [editType, setEditType] = useState(criterion.criteria_type);
    const [editCategory, setEditCategory] = useState(criterion.category ?? '');

    const isLowConfidence = criterion.confidence < 0.7;

    function handleApprove() {
        onAction(criterion.id, {
            action: 'approve',
            reviewer_id: 'current-user',
        });
    }

    function handleReject() {
        onAction(criterion.id, {
            action: 'reject',
            reviewer_id: 'current-user',
        });
    }

    function handleModifySave() {
        onAction(criterion.id, {
            action: 'modify',
            reviewer_id: 'current-user',
            modified_text: editText,
            modified_type: editType,
            modified_category: editCategory || undefined,
        });
        setIsEditing(false);
    }

    function handleModifyCancel() {
        setEditText(criterion.text);
        setEditType(criterion.criteria_type);
        setEditCategory(criterion.category ?? '');
        setIsEditing(false);
    }

    return (
        <div
            className={cn(
                'rounded-lg border bg-card p-4 shadow-sm',
                isLowConfidence && 'border-l-4 border-l-red-300'
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
                <ReviewStatusBadge status={criterion.review_status} />
            </div>

            {/* Body */}
            {isEditing ? (
                <div className="space-y-3 mb-3">
                    <div>
                        <label
                            htmlFor={`edit-text-${criterion.id}`}
                            className="block text-sm font-medium text-muted-foreground mb-1"
                        >
                            Text
                        </label>
                        <textarea
                            id={`edit-text-${criterion.id}`}
                            value={editText}
                            onChange={(e) => setEditText(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            rows={3}
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label
                                htmlFor={`edit-type-${criterion.id}`}
                                className="block text-sm font-medium text-muted-foreground mb-1"
                            >
                                Type
                            </label>
                            <select
                                id={`edit-type-${criterion.id}`}
                                value={editType}
                                onChange={(e) => setEditType(e.target.value)}
                                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            >
                                <option value="inclusion">Inclusion</option>
                                <option value="exclusion">Exclusion</option>
                            </select>
                        </div>
                        <div>
                            <label
                                htmlFor={`edit-category-${criterion.id}`}
                                className="block text-sm font-medium text-muted-foreground mb-1"
                            >
                                Category
                            </label>
                            <input
                                id={`edit-category-${criterion.id}`}
                                type="text"
                                value={editCategory}
                                onChange={(e) => setEditCategory(e.target.value)}
                                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            />
                        </div>
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
            ) : (
                <p className="text-sm text-foreground mb-3">{criterion.text}</p>
            )}

            {/* Assertion status tag */}
            {criterion.assertion_status && criterion.assertion_status !== 'PRESENT' && (
                <div className="mb-3">
                    <span className="inline-flex items-center rounded-full bg-purple-100 px-2.5 py-0.5 text-xs font-medium text-purple-800">
                        {criterion.assertion_status}
                    </span>
                </div>
            )}

            {/* Temporal constraint */}
            {criterion.temporal_constraint && formatTemporalConstraint(criterion.temporal_constraint) && (
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
                    {extractThresholdsList(criterion.numeric_thresholds).map((threshold, idx) => {
                        const text = formatNumericThreshold(threshold);
                        return text ? (
                            <span
                                key={idx}
                                className="inline-flex items-center rounded-full bg-teal-100 px-2.5 py-0.5 text-xs font-medium text-teal-800"
                            >
                                {text}
                            </span>
                        ) : null;
                    })}
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
