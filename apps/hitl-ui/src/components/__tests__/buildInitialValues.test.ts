/**
 * Tests for buildInitialValues, normalizeFieldValue, and normalizeRelation
 * extracted in fieldMappingUtils.ts.
 *
 * Covers new typed format, legacy flat format, relation normalization,
 * key fallbacks, omop_concept_id passthrough, and Priority 2 fallback.
 */

import { describe, expect, it } from 'vitest';

import type { Criterion } from '../../hooks/useReviews';
import {
    buildInitialValues,
    extractThresholdsList,
    formatNumericThreshold,
    formatTemporalConstraint,
    normalizeFieldValue,
    normalizeRelation,
} from '../fieldMappingUtils';

// Minimal criterion factory for testing
function makeCriterion(overrides: Partial<Criterion> = {}): Criterion {
    return {
        id: 'test-1',
        batch_id: 'batch-1',
        criteria_type: 'inclusion',
        category: null,
        text: 'Test criterion',
        temporal_constraint: null,
        conditions: null,
        numeric_thresholds: null,
        assertion_status: null,
        confidence: 0.9,
        source_section: null,
        page_number: null,
        review_status: null,
        entities: [],
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        ...overrides,
    };
}

// --- normalizeRelation tests ---

describe('normalizeRelation', () => {
    it('maps "has" to "contains"', () => {
        expect(normalizeRelation('has')).toBe('contains');
    });

    it('maps "is" to "="', () => {
        expect(normalizeRelation('is')).toBe('=');
    });

    it('maps "not" to "not_contains"', () => {
        expect(normalizeRelation('not')).toBe('not_contains');
    });

    it('maps "==" to "="', () => {
        expect(normalizeRelation('==')).toBe('=');
    });

    it('maps "range" to "within"', () => {
        expect(normalizeRelation('range')).toBe('within');
    });

    it('passes through valid operators unchanged', () => {
        const validOps = [
            '=',
            '!=',
            '>',
            '>=',
            '<',
            '<=',
            'within',
            'not_in_last',
            'contains',
            'not_contains',
        ];
        for (const op of validOps) {
            expect(normalizeRelation(op)).toBe(op);
        }
    });

    it('returns empty string for unknown operators', () => {
        expect(normalizeRelation('unknown_op')).toBe('');
    });

    it('returns empty string for empty string', () => {
        expect(normalizeRelation('')).toBe('');
    });
});

// --- normalizeFieldValue tests ---

describe('normalizeFieldValue', () => {
    it('parses new typed standard format', () => {
        const fm = {
            value: { type: 'standard', value: '7', unit: '%' },
        };
        expect(normalizeFieldValue(fm)).toEqual({
            type: 'standard',
            value: '7',
            unit: '%',
        });
    });

    it('parses new typed range format', () => {
        const fm = {
            value: { type: 'range', min: '18', max: '65', unit: 'years' },
        };
        expect(normalizeFieldValue(fm)).toEqual({
            type: 'range',
            min: '18',
            max: '65',
            unit: 'years',
        });
    });

    it('parses new typed temporal format', () => {
        const fm = {
            value: { type: 'temporal', duration: '6', unit: 'months' },
        };
        expect(normalizeFieldValue(fm)).toEqual({
            type: 'temporal',
            duration: '6',
            unit: 'months',
        });
    });

    it('wraps legacy flat string value', () => {
        const fm = { value: '7', unit: '%' };
        expect(normalizeFieldValue(fm)).toEqual({
            type: 'standard',
            value: '7',
            unit: '%',
        });
    });

    it('wraps legacy flat number value', () => {
        const fm = { value: 42, unit: 'mg/dL' };
        expect(normalizeFieldValue(fm)).toEqual({
            type: 'standard',
            value: '42',
            unit: 'mg/dL',
        });
    });

    it('wraps legacy flat value with no unit', () => {
        const fm = { value: 'positive' };
        expect(normalizeFieldValue(fm)).toEqual({
            type: 'standard',
            value: 'positive',
            unit: '',
        });
    });

    it('returns default for missing value', () => {
        const fm = {};
        expect(normalizeFieldValue(fm)).toEqual({
            type: 'standard',
            value: '',
            unit: '',
        });
    });

    it('returns default for null value', () => {
        const fm = { value: null };
        expect(normalizeFieldValue(fm)).toEqual({
            type: 'standard',
            value: '',
            unit: '',
        });
    });
});

// --- buildInitialValues Priority 1 tests ---

describe('buildInitialValues Priority 1 (field_mappings)', () => {
    it('parses new typed format correctly', () => {
        const criterion = makeCriterion({
            conditions: {
                field_mappings: [
                    {
                        entity: 'HbA1c',
                        relation: '<',
                        value: { type: 'standard', value: '7', unit: '%' },
                        entity_code: 'C0019018',
                        entity_system: 'umls',
                    },
                ],
            },
        });

        const result = buildInitialValues(criterion);
        expect(result.mappings).toHaveLength(1);
        expect(result.mappings[0].entity).toBe('HbA1c');
        expect(result.mappings[0].relation).toBe('<');
        expect(result.mappings[0].value).toEqual({
            type: 'standard',
            value: '7',
            unit: '%',
        });
        expect(result.mappings[0].entity_code).toBe('C0019018');
        expect(result.mappings[0].entity_system).toBe('umls');
    });

    it('normalizes legacy flat value format', () => {
        const criterion = makeCriterion({
            conditions: {
                field_mappings: [
                    {
                        entity: 'HbA1c',
                        relation: '>=',
                        value: '6',
                        unit: 'months',
                    },
                ],
            },
        });

        const result = buildInitialValues(criterion);
        expect(result.mappings[0].value).toEqual({
            type: 'standard',
            value: '6',
            unit: 'months',
        });
    });

    it('normalizes legacy relation operators', () => {
        const criterion = makeCriterion({
            conditions: {
                field_mappings: [
                    {
                        entity: 'Diabetes',
                        relation: 'has',
                        value: { type: 'standard', value: 'confirmed', unit: '' },
                    },
                ],
            },
        });

        const result = buildInitialValues(criterion);
        expect(result.mappings[0].relation).toBe('contains');
    });

    it('falls back from entity_concept_id to entity_code', () => {
        const criterion = makeCriterion({
            conditions: {
                field_mappings: [
                    {
                        entity: 'HbA1c',
                        relation: '<',
                        value: { type: 'standard', value: '7', unit: '%' },
                        entity_concept_id: 'C0019018',
                        entity_concept_system: 'umls',
                    },
                ],
            },
        });

        const result = buildInitialValues(criterion);
        expect(result.mappings[0].entity_code).toBe('C0019018');
        expect(result.mappings[0].entity_system).toBe('umls');
    });

    it('passes through omop_concept_id', () => {
        const criterion = makeCriterion({
            conditions: {
                field_mappings: [
                    {
                        entity: 'HbA1c',
                        relation: '<',
                        value: { type: 'standard', value: '7', unit: '%' },
                        omop_concept_id: '3004410',
                    },
                ],
            },
        });

        const result = buildInitialValues(criterion);
        expect(result.mappings[0].omop_concept_id).toBe('3004410');
    });

    it('prefers entity_code over entity_concept_id when both present', () => {
        const criterion = makeCriterion({
            conditions: {
                field_mappings: [
                    {
                        entity: 'HbA1c',
                        relation: '<',
                        value: { type: 'standard', value: '7', unit: '%' },
                        entity_code: 'NEW_CODE',
                        entity_concept_id: 'OLD_CODE',
                    },
                ],
            },
        });

        const result = buildInitialValues(criterion);
        expect(result.mappings[0].entity_code).toBe('NEW_CODE');
    });
});

// --- buildInitialValues Priority 2 tests ---

describe('buildInitialValues Priority 2 (inference from entities + thresholds)', () => {
    it('matches entities to thresholds without double-assignment', () => {
        const criterion = makeCriterion({
            entities: [
                {
                    id: 'e1',
                    entity_type: 'Lab_Value',
                    text: 'HbA1c',
                    umls_cui: 'C0019018',
                    snomed_code: null,
                    preferred_term: 'HbA1c',
                    grounding_confidence: 0.9,
                },
                {
                    id: 'e2',
                    entity_type: 'Lab_Value',
                    text: 'eGFR',
                    umls_cui: null,
                    snomed_code: '80274001',
                    preferred_term: 'eGFR',
                    grounding_confidence: 0.85,
                },
            ],
            numeric_thresholds: {
                thresholds: [{ comparator: '<', value: 7, unit: '%' }],
            },
        });

        const result = buildInitialValues(criterion);
        // First threshold matches first entity
        expect(result.mappings[0].entity).toBe('HbA1c');
        expect(result.mappings[0].relation).toBe('<');
        expect(result.mappings[0].value).toEqual({
            type: 'standard',
            value: '7',
            unit: '%',
        });
        // Second entity (unmatched) should appear with empty values
        expect(result.mappings[1].entity).toBe('eGFR');
        expect(result.mappings[1].relation).toBe('');
    });

    it('adds non-measurable entities with empty relation/value', () => {
        const criterion = makeCriterion({
            entities: [
                {
                    id: 'e1',
                    entity_type: 'Condition',
                    text: 'Type 2 Diabetes',
                    umls_cui: 'C0011860',
                    snomed_code: null,
                    preferred_term: 'T2DM',
                    grounding_confidence: 0.9,
                },
            ],
        });

        const result = buildInitialValues(criterion);
        expect(result.mappings[0].entity).toBe('T2DM');
        expect(result.mappings[0].relation).toBe('');
        expect(result.mappings[0].entity_code).toBe('C0011860');
    });

    it('handles range comparator in thresholds', () => {
        const criterion = makeCriterion({
            entities: [
                {
                    id: 'e1',
                    entity_type: 'Demographic',
                    text: 'Age',
                    umls_cui: null,
                    snomed_code: '397669002',
                    preferred_term: 'Age',
                    grounding_confidence: 0.95,
                },
            ],
            numeric_thresholds: {
                thresholds: [{ comparator: 'range', value: 18, upper_value: 65, unit: 'years' }],
            },
        });

        const result = buildInitialValues(criterion);
        expect(result.mappings[0].entity).toBe('Age');
        expect(result.mappings[0].relation).toBe('within');
        expect(result.mappings[0].value).toEqual({
            type: 'range',
            min: '18',
            max: '65',
            unit: 'years',
        });
    });

    it('handles temporal constraint with duration', () => {
        const criterion = makeCriterion({
            temporal_constraint: {
                duration: '6 months',
                reference_point: 'enrollment',
            },
        });

        const result = buildInitialValues(criterion);
        expect(result.mappings[0].entity).toBe('enrollment');
        expect(result.mappings[0].relation).toBe('not_in_last');
        expect(result.mappings[0].value).toEqual({
            type: 'temporal',
            duration: '6',
            unit: 'months',
        });
    });

    it('returns DEFAULT_FIELD_VALUES when no data', () => {
        const criterion = makeCriterion();
        const result = buildInitialValues(criterion);
        expect(result.mappings).toHaveLength(1);
        expect(result.mappings[0].entity).toBe('');
    });

    it('uses entity text when preferred_term is null', () => {
        const criterion = makeCriterion({
            entities: [
                {
                    id: 'e1',
                    entity_type: 'Condition',
                    text: 'diabetes mellitus',
                    umls_cui: null,
                    snomed_code: null,
                    preferred_term: null,
                    grounding_confidence: 0.8,
                },
            ],
        });

        const result = buildInitialValues(criterion);
        expect(result.mappings[0].entity).toBe('diabetes mellitus');
    });

    it('handles Medication and Procedure entity types', () => {
        const criterion = makeCriterion({
            entities: [
                {
                    id: 'e1',
                    entity_type: 'Medication',
                    text: 'Metformin',
                    umls_cui: null,
                    snomed_code: '109081006',
                    preferred_term: 'Metformin',
                    grounding_confidence: 0.9,
                },
                {
                    id: 'e2',
                    entity_type: 'Procedure',
                    text: 'biopsy',
                    umls_cui: 'C0005558',
                    snomed_code: null,
                    preferred_term: 'Biopsy',
                    grounding_confidence: 0.85,
                },
            ],
        });

        const result = buildInitialValues(criterion);
        expect(result.mappings).toHaveLength(2);
        expect(result.mappings[0].entity).toBe('Metformin');
        expect(result.mappings[0].entity_code).toBe('109081006');
        expect(result.mappings[0].entity_system).toBe('snomed');
        expect(result.mappings[1].entity).toBe('Biopsy');
        expect(result.mappings[1].entity_code).toBe('C0005558');
        expect(result.mappings[1].entity_system).toBe('umls');
    });

    it('skips thresholds with null value', () => {
        const criterion = makeCriterion({
            entities: [
                {
                    id: 'e1',
                    entity_type: 'Lab_Value',
                    text: 'HbA1c',
                    umls_cui: 'C0019018',
                    snomed_code: null,
                    preferred_term: 'HbA1c',
                    grounding_confidence: 0.9,
                },
            ],
            numeric_thresholds: {
                thresholds: [
                    { comparator: '<', value: null, unit: '%' },
                    { comparator: '>=', value: 5, unit: '%' },
                ],
            },
        });

        const result = buildInitialValues(criterion);
        // Only the second threshold (value=5) should produce a mapping
        expect(result.mappings[0].entity).toBe('HbA1c');
        expect(result.mappings[0].value).toEqual({
            type: 'standard',
            value: '5',
            unit: '%',
        });
    });
});

// --- formatTemporalConstraint tests ---

describe('formatTemporalConstraint', () => {
    it('formats a full temporal constraint', () => {
        const tc = { duration: '6 months', relation: 'within', reference_point: 'enrollment' };
        expect(formatTemporalConstraint(tc)).toBe('Within 6 months of enrollment');
    });

    it('formats without reference point', () => {
        const tc = { duration: '3 weeks', relation: 'before' };
        expect(formatTemporalConstraint(tc)).toBe('Before 3 weeks');
    });

    it('returns empty string when no duration', () => {
        const tc = { relation: 'within' };
        expect(formatTemporalConstraint(tc)).toBe('');
    });

    it('uses raw relation string if not in map', () => {
        const tc = { duration: '1 day', relation: 'concurrent' };
        expect(formatTemporalConstraint(tc)).toBe('concurrent 1 day');
    });

    it('formats with at_least relation', () => {
        const tc = { duration: '2 years', relation: 'at_least' };
        expect(formatTemporalConstraint(tc)).toBe('At least 2 years');
    });

    it('formats with after relation', () => {
        const tc = { duration: '1 week', relation: 'after', reference_point: 'surgery' };
        expect(formatTemporalConstraint(tc)).toBe('After 1 week of surgery');
    });

    it('formats with no relation', () => {
        const tc = { duration: '6 months' };
        expect(formatTemporalConstraint(tc)).toBe('6 months');
    });
});

// --- formatNumericThreshold tests ---

describe('formatNumericThreshold', () => {
    it('formats standard threshold', () => {
        expect(formatNumericThreshold({ comparator: '<', value: 7, unit: '%' })).toBe('<7 %');
    });

    it('formats range threshold', () => {
        expect(
            formatNumericThreshold({
                comparator: 'range',
                value: 18,
                upper_value: 65,
                unit: 'years',
            })
        ).toBe('18-65 years');
    });

    it('returns empty when value is null', () => {
        expect(formatNumericThreshold({ comparator: '<', value: null, unit: '%' })).toBe('');
    });

    it('formats without unit', () => {
        expect(formatNumericThreshold({ comparator: '>=', value: 30 })).toBe('>=30');
    });

    it('formats range without upper_value as standard', () => {
        expect(formatNumericThreshold({ comparator: 'range', value: 5, unit: 'mg' })).toBe(
            'range5 mg'
        );
    });
});

// --- extractThresholdsList tests ---

describe('extractThresholdsList', () => {
    it('returns empty for null', () => {
        expect(extractThresholdsList(null)).toEqual([]);
    });

    it('extracts from wrapper object', () => {
        const nt = { thresholds: [{ value: 7, comparator: '<' }] };
        expect(extractThresholdsList(nt)).toEqual([{ value: 7, comparator: '<' }]);
    });

    it('extracts from raw array', () => {
        const nt = [{ value: 7, comparator: '<' }] as unknown as Record<string, unknown>;
        expect(extractThresholdsList(nt)).toEqual([{ value: 7, comparator: '<' }]);
    });

    it('wraps single threshold object', () => {
        const nt = { value: 7, comparator: '<', unit: '%' };
        expect(extractThresholdsList(nt)).toEqual([{ value: 7, comparator: '<', unit: '%' }]);
    });

    it('returns empty for unrecognized shape', () => {
        const nt = { some_other_key: 'value' };
        expect(extractThresholdsList(nt)).toEqual([]);
    });
});
