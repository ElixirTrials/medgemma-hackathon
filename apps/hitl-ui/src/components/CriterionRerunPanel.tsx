import * as Dialog from '@radix-ui/react-dialog';
import { Loader2, X } from 'lucide-react';
import { useState } from 'react';

import { useCriterionRerun } from '../hooks/useCorpus';
import { cn } from '../lib/utils';
import { Button } from './ui/Button';

interface CriterionRerunPanelProps {
    criterionId: string;
    criterionText: string;
    currentExtraction: Record<string, unknown>;
    onAccept: (revised: Record<string, unknown>) => void;
    trigger: React.ReactNode;
}

const FIELD_LABELS: Record<string, string> = {
    criteria_type: 'Type',
    category: 'Category',
    temporal_constraint: 'Temporal Constraint',
    conditions: 'Conditions',
    numeric_thresholds: 'Numeric Thresholds',
    text: 'Text',
};

const DISPLAY_FIELDS = [
    'text',
    'criteria_type',
    'category',
    'temporal_constraint',
    'conditions',
    'numeric_thresholds',
] as const;

function formatFieldValue(value: unknown): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'string') return value || '—';
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    return JSON.stringify(value, null, 2);
}

function fieldChanged(original: Record<string, unknown>, revised: Record<string, unknown>, field: string): boolean {
    return JSON.stringify(original[field]) !== JSON.stringify(revised[field]);
}

export function CriterionRerunPanel({
    criterionId,
    criterionText,
    currentExtraction,
    onAccept,
    trigger,
}: CriterionRerunPanelProps) {
    const [open, setOpen] = useState(false);
    const [feedback, setFeedback] = useState('');
    const rerunMutation = useCriterionRerun();

    const handleSubmit = () => {
        if (!feedback.trim()) return;
        rerunMutation.mutate({ criterionId, reviewer_feedback: feedback });
    };

    const handleAccept = () => {
        if (rerunMutation.data) {
            onAccept(rerunMutation.data.revised_criterion);
            setOpen(false);
            setFeedback('');
            rerunMutation.reset();
        }
    };

    const handleCancel = () => {
        setOpen(false);
        setFeedback('');
        rerunMutation.reset();
    };

    const hasResult = rerunMutation.isSuccess && !!rerunMutation.data;
    const original = hasResult ? rerunMutation.data.original_criterion : currentExtraction;
    const revised = hasResult ? rerunMutation.data.revised_criterion : null;

    return (
        <Dialog.Root open={open} onOpenChange={setOpen}>
            <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>

            <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
                <Dialog.Content className="fixed left-[50%] top-[50%] z-50 translate-x-[-50%] translate-y-[-50%] w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-lg border bg-background p-6 shadow-lg">
                    {/* Header */}
                    <div className="flex items-start justify-between mb-4">
                        <div>
                            <Dialog.Title className="text-lg font-semibold">
                                Correct with AI
                            </Dialog.Title>
                            <Dialog.Description className="text-sm text-muted-foreground mt-1">
                                Describe what's wrong with the extraction. The AI will propose a revised
                                structured criterion for your review.
                            </Dialog.Description>
                        </div>
                        <Dialog.Close asChild>
                            <button
                                type="button"
                                className="text-muted-foreground hover:text-foreground transition-colors"
                                aria-label="Close"
                            >
                                <X className="h-5 w-5" />
                            </button>
                        </Dialog.Close>
                    </div>

                    {/* Original criterion text (context) */}
                    <div className="mb-4 rounded-lg border bg-muted/30 p-3">
                        <p className="text-xs font-medium text-muted-foreground mb-1">
                            Criterion text
                        </p>
                        <p className="text-sm text-foreground">{criterionText}</p>
                    </div>

                    {/* Step 1: Feedback input — always visible */}
                    {!hasResult && (
                        <div className="space-y-3 mb-4">
                            <div>
                                <label
                                    htmlFor={`rerun-feedback-${criterionId}`}
                                    className="block text-sm font-medium text-foreground mb-1"
                                >
                                    What's wrong with the current extraction?
                                </label>
                                <textarea
                                    id={`rerun-feedback-${criterionId}`}
                                    value={feedback}
                                    onChange={(e) => setFeedback(e.target.value)}
                                    placeholder="e.g. The age threshold is missing, the category should be 'cardiovascular disease', the criteria_type is wrong..."
                                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                    rows={3}
                                    disabled={rerunMutation.isPending}
                                />
                            </div>

                            {rerunMutation.isError && (
                                <p className="text-sm text-red-600">
                                    AI could not produce a valid result. Try rephrasing your feedback.
                                </p>
                            )}

                            <Button
                                onClick={handleSubmit}
                                disabled={!feedback.trim() || rerunMutation.isPending}
                            >
                                {rerunMutation.isPending ? (
                                    <>
                                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                                        Processing...
                                    </>
                                ) : (
                                    'Submit'
                                )}
                            </Button>
                        </div>
                    )}

                    {/* Step 2: Side-by-side comparison — shown after mutation succeeds */}
                    {hasResult && revised && (
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                {/* Original column */}
                                <div className="rounded-lg border p-3 space-y-2">
                                    <p className="text-sm font-semibold text-muted-foreground">
                                        Original
                                    </p>
                                    {DISPLAY_FIELDS.map((field) => (
                                        <div key={field}>
                                            <p className="text-xs font-medium text-muted-foreground">
                                                {FIELD_LABELS[field] ?? field}
                                            </p>
                                            <p
                                                className={cn(
                                                    'text-sm',
                                                    fieldChanged(original, revised, field)
                                                        ? 'text-muted-foreground line-through'
                                                        : 'text-foreground'
                                                )}
                                            >
                                                {formatFieldValue(original[field])}
                                            </p>
                                        </div>
                                    ))}
                                </div>

                                {/* Revised column */}
                                <div className="rounded-lg border p-3 space-y-2">
                                    <p className="text-sm font-semibold text-green-700">
                                        AI Revised
                                    </p>
                                    {DISPLAY_FIELDS.map((field) => {
                                        const changed = fieldChanged(original, revised, field);
                                        return (
                                            <div key={field}>
                                                <p className="text-xs font-medium text-muted-foreground">
                                                    {FIELD_LABELS[field] ?? field}
                                                </p>
                                                <p
                                                    className={cn(
                                                        'text-sm',
                                                        changed
                                                            ? 'text-green-700 bg-green-50 rounded px-1'
                                                            : 'text-foreground'
                                                    )}
                                                >
                                                    {formatFieldValue(revised[field])}
                                                </p>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            {/* Actions */}
                            <div className="flex items-center gap-2 pt-2 border-t">
                                <Button onClick={handleAccept}>Accept Revision</Button>
                                <Button variant="outline" onClick={handleCancel}>
                                    Cancel
                                </Button>
                            </div>
                        </div>
                    )}

                    {/* Cancel button when in feedback step */}
                    {!hasResult && (
                        <div className="mt-2">
                            <Button
                                variant="outline"
                                onClick={handleCancel}
                                disabled={rerunMutation.isPending}
                            >
                                Cancel
                            </Button>
                        </div>
                    )}
                </Dialog.Content>
            </Dialog.Portal>
        </Dialog.Root>
    );
}
