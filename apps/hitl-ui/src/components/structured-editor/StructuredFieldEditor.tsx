// Main structured field editor component with multiple entity/relation/value mappings

import { Loader2, Plus, Trash2 } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { Controller, useFieldArray, useForm } from 'react-hook-form';

import { Button } from '../ui/Button';
import { RelationSelect } from './RelationSelect';
import { ValueInput } from './ValueInput';
import {
    DEFAULT_FIELD_VALUES,
    DEFAULT_MAPPING,
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
    const { control, handleSubmit, watch, setValue } = useForm<StructuredFieldFormValues>({
        defaultValues: initialValues ?? DEFAULT_FIELD_VALUES,
    });

    const { fields, append, remove } = useFieldArray({
        control,
        name: 'mappings',
    });

    // Watch all mappings for validation
    const allMappings = watch('mappings');

    // Track previous relations for each mapping to detect changes
    const previousRelationsRef = useRef<Array<RelationOperator | ''>>([]);

    // State cleanup on relation change - prevent state leak between categories
    useEffect(() => {
        allMappings.forEach((mapping, index) => {
            const currentRelation = mapping.relation;
            const previousRelation = previousRelationsRef.current[index] ?? '';

            // Skip on initial mount (previousRelation is empty string initially)
            if (previousRelation === '' && currentRelation === '') {
                return;
            }

            // If relation actually changed
            if (previousRelation !== currentRelation && currentRelation !== '') {
                const newCategory = RELATION_CATEGORY_MAP[currentRelation as RelationOperator];
                const currentCategory = mapping.value.type;

                // If category changed, reset value to default for new category
                if (newCategory !== currentCategory) {
                    setValue(
                        `mappings.${index}.value`,
                        getDefaultValueForCategory(newCategory)
                    );
                }
            }

            // Update ref for next change detection
            previousRelationsRef.current[index] = currentRelation;
        });
    }, [allMappings, setValue]);

    // Check if we can add a new mapping (last mapping must have entity filled)
    const canAddMapping = () => {
        if (fields.length === 0) return true;
        const lastMapping = allMappings[allMappings.length - 1];
        return lastMapping && lastMapping.entity.trim() !== '';
    };

    const handleAddMapping = () => {
        if (canAddMapping()) {
            append(DEFAULT_MAPPING);
        }
    };

    return (
        <div className="space-y-4">
            {/* Mapping cards */}
            {fields.map((field, index) => {
                const mapping = allMappings[index];
                const relationCategory =
                    mapping?.relation !== ''
                        ? RELATION_CATEGORY_MAP[mapping.relation as RelationOperator]
                        : null;

                return (
                    <div
                        key={field.id}
                        className="border rounded-lg p-3 mb-3 relative"
                    >
                        {/* Mapping label and remove button */}
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-sm font-medium text-muted-foreground">
                                Mapping {index + 1}
                            </span>
                            <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                onClick={() => remove(index)}
                                disabled={fields.length === 1 || isSubmitting}
                                className="h-6 w-6 p-0"
                            >
                                <Trash2 className="h-4 w-4 text-red-600" />
                            </Button>
                        </div>

                        {/* Entity field */}
                        <div className="mb-3">
                            <label
                                htmlFor={`entity-${criterionId}-${index}`}
                                className="block text-sm font-medium text-muted-foreground mb-1"
                            >
                                Entity
                            </label>
                            <Controller
                                name={`mappings.${index}.entity`}
                                control={control}
                                render={({ field }) => (
                                    <input
                                        id={`entity-${criterionId}-${index}`}
                                        type="text"
                                        placeholder="e.g., Age, HbA1c, Acetaminophen"
                                        {...field}
                                        disabled={isSubmitting}
                                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 disabled:cursor-not-allowed"
                                    />
                                )}
                            />
                        </div>

                        {/* Relation field */}
                        <div className="mb-3">
                            <label
                                htmlFor={`relation-${criterionId}-${index}`}
                                className="block text-sm font-medium text-muted-foreground mb-1"
                            >
                                Relation
                            </label>
                            <Controller
                                name={`mappings.${index}.relation`}
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
                                    name={`mappings.${index}.value`}
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
                    </div>
                );
            })}

            {/* Add Mapping button */}
            <div className="mb-3">
                <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={handleAddMapping}
                    disabled={!canAddMapping() || isSubmitting}
                    className="w-full"
                >
                    <Plus className="h-4 w-4 mr-1" />
                    Add Mapping
                </Button>
                {!canAddMapping() && fields.length > 0 && (
                    <p className="text-xs text-muted-foreground mt-1">
                        Complete the current mapping before adding another
                    </p>
                )}
            </div>

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
