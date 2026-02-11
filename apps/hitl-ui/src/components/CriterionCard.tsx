import { CheckCircle, Loader2, Pencil, XCircle } from 'lucide-react';
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
