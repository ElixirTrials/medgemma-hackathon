import type { Criterion } from '../hooks/useReviews';

interface FieldMappingBadgesProps {
    criterion: Criterion;
    onEditClick?: () => void;
}

/** Mapping from legacy relation operators to frontend-standard operators. */
const RELATION_DISPLAY_MAP: Record<string, string> = {
    has: 'contains',
    is: '=',
    not: 'not_contains',
    '==': '=',
    range: 'within',
};

function normalizeRelationDisplay(rel: string): string {
    return RELATION_DISPLAY_MAP[rel] ?? rel;
}

function formatMappingValue(value: Record<string, unknown>): string {
    if (typeof value !== 'object') return '';
    if (value.type === 'range')
        return `${value.min}–${value.max}${value.unit ? ` ${value.unit}` : ''}`;
    if (value.type === 'temporal') return `${value.duration} ${value.unit}`;
    if (value.type === 'standard') return `${value.value}${value.unit ? ` ${value.unit}` : ''}`;
    return '';
}

function renderValue(value: unknown): string {
    if (value === null || value === undefined) return '';
    if (typeof value === 'string') return value;
    if (typeof value === 'number') return String(value);
    if (typeof value === 'object') return formatMappingValue(value as Record<string, unknown>);
    return '';
}

interface RawFieldMapping {
    entity: string;
    entity_code?: string;
    entity_concept_id?: string;
    entity_system?: string;
    entity_concept_system?: string;
    omop_concept_id?: string;
    relation: string;
    value: unknown;
    unit?: string;
}

export default function FieldMappingBadges({ criterion, onEditClick }: FieldMappingBadgesProps) {
    const cond = criterion.conditions as Record<string, unknown> | null;
    const fieldMappings =
        cond && 'field_mappings' in cond && Array.isArray(cond.field_mappings)
            ? (cond.field_mappings as Array<RawFieldMapping>)
            : null;

    if (!fieldMappings || fieldMappings.length === 0) return null;

    const badgeContent = (mapping: RawFieldMapping) => {
        // Legacy key fallbacks
        const entityCode = mapping.entity_code ?? mapping.entity_concept_id;
        const entitySystem = mapping.entity_system ?? mapping.entity_concept_system;
        const relation = normalizeRelationDisplay(mapping.relation);

        // Handle flat value format (string/number) alongside typed object format
        let valueText: string;
        if (typeof mapping.value === 'string' || typeof mapping.value === 'number') {
            const unit = mapping.unit ? ` ${mapping.unit}` : '';
            valueText = `${mapping.value}${unit}`;
        } else {
            valueText = renderValue(mapping.value);
        }

        return (
            <>
                <span className="font-semibold text-blue-900">{mapping.entity || '—'}</span>
                {entityCode && (
                    <span className="inline-flex items-center rounded-full bg-green-50 border border-green-200 px-1.5 py-0 text-[10px] text-green-700">
                        {entitySystem?.toUpperCase()}: {entityCode}
                    </span>
                )}
                {mapping.omop_concept_id && (
                    <span className="inline-flex items-center rounded-full bg-amber-50 border border-amber-200 px-1.5 py-0 text-[10px] text-amber-700">
                        OMOP: {mapping.omop_concept_id}
                    </span>
                )}
                {relation && (
                    <span className="text-blue-600 font-mono text-xs">{relation}</span>
                )}
                {relation && valueText ? (
                    <span className="text-blue-800">{valueText}</span>
                ) : relation && !valueText ? (
                    <span className="text-muted-foreground/50 italic text-xs">no value</span>
                ) : null}
            </>
        );
    };

    return (
        <div className="mb-3">
            <div className="text-xs font-medium text-muted-foreground mb-2">Field Mappings</div>
            <div className="space-y-1">
                {fieldMappings.map((mapping, idx) => (
                    // biome-ignore lint/suspicious/noArrayIndexKey: field_mappings have no stable unique id
                    <div key={idx}>
                        {idx > 0 && (
                            <div className="flex items-center gap-2 py-1">
                                <span className="text-xs font-semibold text-purple-600 bg-purple-50 px-2 py-0.5 rounded">
                                    AND
                                </span>
                                <div className="flex-1 border-t border-dashed border-muted" />
                            </div>
                        )}
                        {onEditClick ? (
                            <button
                                onClick={onEditClick}
                                className="w-full text-left flex items-center gap-2 rounded-md border bg-blue-50/50 border-blue-200 px-3 py-2 text-sm hover:bg-blue-100/50 transition-colors cursor-pointer"
                                title="Click to edit field mappings"
                                type="button"
                            >
                                {badgeContent(mapping)}
                            </button>
                        ) : (
                            <div className="w-full flex items-center gap-2 rounded-md border bg-blue-50/50 border-blue-200 px-3 py-2 text-sm">
                                {badgeContent(mapping)}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
