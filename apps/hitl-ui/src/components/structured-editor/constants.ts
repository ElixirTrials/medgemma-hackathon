// Relation configuration and constants

import type {
    FieldValue,
    RelationCategory,
    RelationOperator,
    StructuredFieldFormValues,
    TemporalUnit,
} from './types';

export const RELATIONS: Array<{
    operator: RelationOperator;
    label: string;
    category: RelationCategory;
}> = [
    { operator: '=', label: 'equals (=)', category: 'standard' },
    { operator: '!=', label: 'not equals (!=)', category: 'standard' },
    { operator: '>', label: 'greater than (>)', category: 'standard' },
    { operator: '>=', label: 'greater or equal (>=)', category: 'standard' },
    { operator: '<', label: 'less than (<)', category: 'standard' },
    { operator: '<=', label: 'less or equal (<=)', category: 'standard' },
    { operator: 'within', label: 'within (range)', category: 'range' },
    { operator: 'not_in_last', label: 'not in last (temporal)', category: 'temporal' },
    { operator: 'contains', label: 'contains', category: 'standard' },
    { operator: 'not_contains', label: 'does not contain', category: 'standard' },
];

export const RELATION_CATEGORY_MAP: Record<RelationOperator, RelationCategory> = RELATIONS.reduce(
    (acc, rel) => {
        acc[rel.operator] = rel.category;
        return acc;
    },
    {} as Record<RelationOperator, RelationCategory>
);

export const TEMPORAL_UNITS: Array<{ value: TemporalUnit; label: string }> = [
    { value: 'days', label: 'Days' },
    { value: 'weeks', label: 'Weeks' },
    { value: 'months', label: 'Months' },
    { value: 'years', label: 'Years' },
];

export const DEFAULT_FIELD_VALUES: StructuredFieldFormValues = {
    entity: '',
    relation: '' as const,
    value: { type: 'standard', value: '', unit: '' },
};

export function getDefaultValueForCategory(category: RelationCategory): FieldValue {
    switch (category) {
        case 'standard':
            return { type: 'standard', value: '', unit: '' };
        case 'range':
            return { type: 'range', min: '', max: '', unit: '' };
        case 'temporal':
            return { type: 'temporal', duration: '', unit: 'days' };
    }
}
