import * as Dialog from '@radix-ui/react-dialog';
import { Controller, useForm } from 'react-hook-form';

import { Button } from './ui/Button';

const REJECT_REASONS = [
    { value: 'not_criteria', label: 'Not a criteria' },
    { value: 'incorrect_grounding', label: 'Incorrect entity grounding' },
    { value: 'poor_splitting', label: 'Poor splitting into composites' },
    { value: 'duplicate', label: 'Duplicate of another criterion' },
    { value: 'other', label: 'Other' },
];

interface RejectDialogFormValues {
    reasons: string[];
    comment: string;
}

interface RejectDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onConfirm: (data: { reasons: string[]; comment?: string }) => void;
}

export default function RejectDialog({ open, onOpenChange, onConfirm }: RejectDialogProps) {
    const { control, handleSubmit, reset } = useForm<RejectDialogFormValues>({
        defaultValues: {
            reasons: [],
            comment: '',
        },
    });

    function handleCancel() {
        reset();
        onOpenChange(false);
    }

    function onSubmit(data: RejectDialogFormValues) {
        onConfirm({
            reasons: data.reasons,
            comment: data.comment || undefined,
        });
        reset();
        onOpenChange(false);
    }

    return (
        <Dialog.Root open={open} onOpenChange={onOpenChange}>
            <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 bg-black/50 z-50" />
                <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white dark:bg-card rounded-lg p-6 max-w-md w-full z-50 shadow-lg">
                    <Dialog.Title className="text-base font-semibold mb-4">
                        Reject Criterion
                    </Dialog.Title>

                    <form onSubmit={handleSubmit(onSubmit)}>
                        <div className="mb-4">
                            <p className="text-sm text-muted-foreground mb-3">
                                Select one or more reasons for rejection:
                            </p>
                            <Controller
                                control={control}
                                name="reasons"
                                render={({ field }) => (
                                    <div className="space-y-2">
                                        {REJECT_REASONS.map((reason) => (
                                            <label
                                                key={reason.value}
                                                className="flex items-center gap-2 cursor-pointer"
                                            >
                                                <input
                                                    type="checkbox"
                                                    value={reason.value}
                                                    checked={field.value.includes(reason.value)}
                                                    onChange={(e) => {
                                                        if (e.target.checked) {
                                                            field.onChange([
                                                                ...field.value,
                                                                reason.value,
                                                            ]);
                                                        } else {
                                                            field.onChange(
                                                                field.value.filter(
                                                                    (v) => v !== reason.value
                                                                )
                                                            );
                                                        }
                                                    }}
                                                    className="h-4 w-4 rounded border-gray-300 text-red-600 focus:ring-red-500"
                                                />
                                                <span className="text-sm">{reason.label}</span>
                                            </label>
                                        ))}
                                    </div>
                                )}
                            />
                        </div>

                        <div className="mb-5">
                            <label
                                htmlFor="reject-comment"
                                className="block text-sm font-medium text-muted-foreground mb-1"
                            >
                                Additional comment{' '}
                                <span className="text-xs text-gray-400">(optional)</span>
                            </label>
                            <Controller
                                control={control}
                                name="comment"
                                render={({ field }) => (
                                    <textarea
                                        id="reject-comment"
                                        {...field}
                                        placeholder="Provide additional context..."
                                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                        rows={3}
                                    />
                                )}
                            />
                        </div>

                        <div className="flex items-center justify-end gap-2">
                            <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                onClick={handleCancel}
                            >
                                Cancel
                            </Button>
                            <Button type="submit" size="sm" variant="destructive">
                                Reject
                            </Button>
                        </div>
                    </form>
                </Dialog.Content>
            </Dialog.Portal>
        </Dialog.Root>
    );
}
