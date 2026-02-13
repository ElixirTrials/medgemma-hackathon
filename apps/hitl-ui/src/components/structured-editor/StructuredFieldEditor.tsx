// Main structured field editor component with entity/relation/value triplet

import { Loader2 } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { Controller, useForm } from 'react-hook-form';

import { Button } from '../ui/Button';
import { RelationSelect } from './RelationSelect';
import { ValueInput } from './ValueInput';
import {
    DEFAULT_FIELD_VALUES,
    RELATION_CATEGORY_MAP,
    getDefaultValueForCategory,
} from './constants';
import type {
    RelationOperator,
    StructuredFieldEditorProps,
    StructuredFieldFormValues,
} from './types';

export function StructuredFieldEditor({
    criterionId,
    initialValues,
    onSave,
    onCancel,
    isSubmitting = false,
}: StructuredFieldEditorProps) {
    const { control, handleSubmit, watch, setValue, register } = useForm<StructuredFieldFormValues>(
        {
            defaultValues: initialValues ?? DEFAULT_FIELD_VALUES,
        }
    );

    // Watch the relation field to detect changes
    const currentRelation = watch('relation');
    const currentValue = watch('value');
    const previousRelationRef = useRef<RelationOperator | ''>('');

    // State cleanup on relation change - prevent state leak between categories
    useEffect(() => {
        // Skip on initial mount (previousRelation is empty string initially)
        if (previousRelationRef.current === '' && currentRelation === '') {
            return;
        }

        // If relation actually changed
        if (previousRelationRef.current !== currentRelation && currentRelation !== '') {
            const newCategory = RELATION_CATEGORY_MAP[currentRelation as RelationOperator];
            const currentCategory = currentValue.type;

            // If category changed, reset value to default for new category
            if (newCategory !== currentCategory) {
                setValue('value', getDefaultValueForCategory(newCategory));
            }
        }

        // Update ref for next change detection
        previousRelationRef.current = currentRelation;
    }, [currentRelation, currentValue.type, setValue]);

    // Determine which value input to show based on relation category
    const relationCategory =
        currentRelation !== '' ? RELATION_CATEGORY_MAP[currentRelation as RelationOperator] : null;

    return (
        <div className="space-y-4">
            {/* Entity field */}
            <div>
                <label
                    htmlFor={`entity-${criterionId}`}
                    className="block text-sm font-medium text-muted-foreground mb-1"
                >
                    Entity
                </label>
                <input
                    id={`entity-${criterionId}`}
                    type="text"
                    placeholder="e.g., Age, HbA1c, Acetaminophen"
                    {...register('entity')}
                    disabled={isSubmitting}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 disabled:cursor-not-allowed"
                />
            </div>

            {/* Relation field */}
            <div>
                <label
                    htmlFor={`relation-${criterionId}`}
                    className="block text-sm font-medium text-muted-foreground mb-1"
                >
                    Relation
                </label>
                <Controller
                    name="relation"
                    control={control}
                    render={({ field }) => (
                        <RelationSelect
                            value={field.value}
                            onChange={field.onChange}
                            disabled={isSubmitting}
                        />
                    )}
                />
            </div>

            {/* Value field - conditionally rendered based on relation category */}
            {relationCategory && (
                <div>
                    <Controller
                        name="value"
                        control={control}
                        render={({ field }) => (
                            <ValueInput
                                category={relationCategory}
                                value={field.value}
                                onChange={field.onChange}
                                disabled={isSubmitting}
                            />
                        )}
                    />
                </div>
            )}

            {/* Action buttons */}
            <div className="flex items-center gap-2 pt-2">
                <Button size="sm" onClick={handleSubmit(onSave)} disabled={isSubmitting}>
                    {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
                    Save
                </Button>
                <Button size="sm" variant="outline" onClick={onCancel} disabled={isSubmitting}>
                    Cancel
                </Button>
            </div>
        </div>
    );
}

// Export as both default and named export for flexible importing
export default StructuredFieldEditor;
