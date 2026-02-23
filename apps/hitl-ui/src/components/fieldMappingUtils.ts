/**
 * Pure utility functions for field mapping normalization and initial value
 * construction. Extracted from CriterionCard to keep the test import graph
 * minimal (no React component dependencies).
 */

import type { Criterion } from '../hooks/useReviews';
import { DEFAULT_FIELD_VALUES } from './structured-editor/constants';
import type {
    FieldMapping,
    FieldValue,
    RelationOperator,
    StructuredFieldFormValues,
    TemporalUnit,
} from './structured-editor/types';

export function formatTemporalConstraint(tc: Record<string, unknown>): string {
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

    const relationText = relation ? relationMap[relation] || relation : '';
    const parts = [relationText, duration];
    if (referencePoint) parts.push('of', referencePoint);

    return parts.filter(Boolean).join(' ');
}

export function formatNumericThreshold(threshold: Record<string, unknown>): string {
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

export function extractThresholdsList(
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

/** Map extraction comparator strings to RelationOperator. */
function mapComparator(comparator: string): RelationOperator | '' {
    const map: Record<string, RelationOperator> = {
        '>=': '>=',
        '<=': '<=',
        '>': '>',
        '<': '<',
        '==': '=',
        '=': '=',
        range: 'within',
    };
    return map[comparator] ?? '';
}

/** Parse a duration string like "6 months" into {value, unit}. */
function parseDuration(duration: string): {
    value: string;
    unit: TemporalUnit;
} {
    const match = duration.match(/^(\d+)\s*(days?|weeks?|months?|years?)$/i);
    if (match) {
        const raw = match[2].toLowerCase().replace(/s$/, '');
        const unitMap: Record<string, TemporalUnit> = {
            day: 'days',
            week: 'weeks',
            month: 'months',
            year: 'years',
        };
        return { value: match[1], unit: unitMap[raw] ?? 'days' };
    }
    return { value: duration, unit: 'days' };
}

/** Valid frontend relation operators. */
const VALID_RELATIONS = new Set<string>([
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
]);

/** Normalize a raw relation string to a valid RelationOperator or empty. */
export function normalizeRelation(raw: string): RelationOperator | '' {
    const map: Record<string, RelationOperator> = {
        has: 'contains',
        is: '=',
        not: 'not_contains',
        '==': '=',
        range: 'within',
    };
    const mapped = map[raw] ?? raw;
    return VALID_RELATIONS.has(mapped) ? (mapped as RelationOperator) : '';
}

/** Normalize a field mapping's value to a typed FieldValue. */
export function normalizeFieldValue(fm: Record<string, unknown>): FieldValue {
    const rawVal = fm.value;

    // New typed format: value is an object with a 'type' key
    if (rawVal && typeof rawVal === 'object' && !Array.isArray(rawVal)) {
        const obj = rawVal as Record<string, unknown>;
        if (obj.type === 'range') {
            return {
                type: 'range',
                min: String(obj.min ?? ''),
                max: String(obj.max ?? ''),
                unit: String(obj.unit ?? ''),
            };
        }
        if (obj.type === 'temporal') {
            return {
                type: 'temporal',
                duration: String(obj.duration ?? ''),
                unit: (obj.unit as TemporalUnit) ?? 'days',
            };
        }
        if (obj.type === 'standard') {
            return {
                type: 'standard',
                value: String(obj.value ?? ''),
                unit: String(obj.unit ?? ''),
            };
        }
    }

    // Legacy flat format: value is a string or number
    if (typeof rawVal === 'string' || typeof rawVal === 'number') {
        return {
            type: 'standard',
            value: String(rawVal),
            unit: String(fm.unit ?? ''),
        };
    }

    return { type: 'standard', value: '', unit: '' };
}

/**
 * Build initial form values for the structured editor from a criterion's
 * AI-extracted data (numeric_thresholds, temporal_constraint, conditions).
 */
export function buildInitialValues(criterion: Criterion): StructuredFieldFormValues {
    // Priority 1: existing field_mappings from a previous structured edit
    const cond = criterion.conditions as Record<string, unknown> | null;
    if (cond && 'field_mappings' in cond && Array.isArray(cond.field_mappings)) {
        const fms = cond.field_mappings as Array<Record<string, unknown>>;
        const mappings: FieldMapping[] = fms.map((fm) => {
            const rel = (fm.relation as string) ?? '';
            const value = normalizeFieldValue(fm);
            return {
                entity: String(fm.entity ?? ''),
                entity_code:
                    (fm.entity_code ?? fm.entity_concept_id)
                        ? String(fm.entity_code ?? fm.entity_concept_id)
                        : undefined,
                entity_system:
                    (fm.entity_system ?? fm.entity_concept_system)
                        ? String(fm.entity_system ?? fm.entity_concept_system)
                        : undefined,
                omop_concept_id: fm.omop_concept_id ? String(fm.omop_concept_id) : undefined,
                relation: normalizeRelation(rel),
                value,
            };
        });
        if (mappings.length > 0) return { mappings };
    }

    // Priority 2: infer from AI-extracted data (entities + thresholds + temporal)
    const mappings: FieldMapping[] = [];

    const entities = criterion.entities ?? [];
    const thresholds = extractThresholdsList(criterion.numeric_thresholds);

    const entityLabel = (e: { preferred_term: string | null; text: string }) =>
        e.preferred_term || e.text;

    const measurableEntities = entities.filter(
        (e) =>
            e.entity_type === 'Lab_Value' ||
            e.entity_type === 'Biomarker' ||
            e.entity_type === 'Demographic'
    );

    const usedEntityIndices = new Set<number>();

    for (let i = 0; i < thresholds.length; i++) {
        const t = thresholds[i];
        const comparator = (t.comparator as string) ?? '';
        const val = t.value as number | null;
        const unit = (t.unit as string) ?? '';
        const upperVal = t.upper_value as number | null;

        if (val === null || val === undefined) continue;

        // Find the next unused measurable entity
        let matchedEntity: (typeof measurableEntities)[number] | undefined;
        for (let j = 0; j < measurableEntities.length; j++) {
            if (!usedEntityIndices.has(j)) {
                matchedEntity = measurableEntities[j];
                usedEntityIndices.add(j);
                break;
            }
        }
        const entity = matchedEntity ? entityLabel(matchedEntity) : '';
        const entityCode = matchedEntity?.snomed_code ?? matchedEntity?.umls_cui ?? undefined;
        const entitySystem = matchedEntity?.snomed_code
            ? 'snomed'
            : matchedEntity?.umls_cui
              ? 'umls'
              : undefined;

        if (comparator === 'range' && upperVal != null) {
            mappings.push({
                entity,
                entity_code: entityCode,
                entity_system: entitySystem,
                relation: 'within' as RelationOperator,
                value: { type: 'range', min: String(val), max: String(upperVal), unit },
            });
        } else {
            const relation = mapComparator(comparator);
            mappings.push({
                entity,
                entity_code: entityCode,
                entity_system: entitySystem,
                relation,
                value: { type: 'standard', value: String(val), unit },
            });
        }
    }

    // Add remaining unmatched measurable entities with empty relation/value
    for (let j = 0; j < measurableEntities.length; j++) {
        if (!usedEntityIndices.has(j)) {
            const e = measurableEntities[j];
            const code = e.snomed_code ?? e.umls_cui ?? undefined;
            const system = e.snomed_code ? 'snomed' : e.umls_cui ? 'umls' : undefined;
            mappings.push({
                entity: entityLabel(e),
                entity_code: code,
                entity_system: system,
                relation: '',
                value: { type: 'standard', value: '', unit: '' },
            });
        }
    }

    const unmatchedEntities = entities.filter(
        (e) =>
            e.entity_type === 'Condition' ||
            e.entity_type === 'Medication' ||
            e.entity_type === 'Procedure'
    );
    for (const e of unmatchedEntities) {
        const code = e.snomed_code ?? e.umls_cui ?? undefined;
        const system = e.snomed_code ? 'snomed' : e.umls_cui ? 'umls' : undefined;
        mappings.push({
            entity: entityLabel(e),
            entity_code: code,
            entity_system: system,
            relation: '',
            value: { type: 'standard', value: '', unit: '' },
        });
    }

    if (criterion.temporal_constraint) {
        const tc = criterion.temporal_constraint;
        const duration = tc.duration as string | undefined;
        const referencePoint = tc.reference_point as string | undefined;

        if (duration) {
            const parsed = parseDuration(duration);
            mappings.push({
                entity: referencePoint ?? '',
                relation: 'not_in_last' as RelationOperator,
                value: { type: 'temporal', duration: parsed.value, unit: parsed.unit },
            });
        }
    }

    if (mappings.length === 0) return DEFAULT_FIELD_VALUES;
    return { mappings };
}
