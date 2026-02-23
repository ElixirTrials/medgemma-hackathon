/**
 * Tests for buildInitialValues, normalizeFieldValue, and normalizeRelation
 * in CriterionCard.tsx.
 *
 * Covers new typed format, legacy flat format, relation normalization,
 * key fallbacks, omop_concept_id passthrough, and Priority 2 fallback.
 */

import { describe, expect, it, vi } from 'vitest';

// Mock react-pdf to avoid DOMMatrix dependency in jsdom
vi.mock('react-pdf', () => ({
    pdfjs: { GlobalWorkerOptions: { workerSrc: '' } },
    Document: 'div',
    Page: 'div',
}));

import {
    buildInitialValues,
    normalizeFieldValue,
    normalizeRelation,
} from '../CriterionCard';
import type { Criterion } from '../../hooks/useReviews';

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
        const validOps = ['=', '!=', '>', '>=', '<', '<=', 'within', 'not_in_last', 'contains', 'not_contains'];
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
});
