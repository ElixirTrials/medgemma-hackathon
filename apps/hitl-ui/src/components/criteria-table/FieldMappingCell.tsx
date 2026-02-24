interface RawMapping {
    entity: string;
    entity_code?: string;
    entity_system?: string;
    omop_concept_id?: string;
    relation: string;
    value: unknown;
    unit?: string;
}

interface FieldMappingCellProps {
    mappings: Array<Record<string, unknown>>;
}

const MAX_VALUE_LEN = 80;

function truncate(s: string): string {
    return s.length > MAX_VALUE_LEN ? `${s.slice(0, MAX_VALUE_LEN)}…` : s;
}

function formatValue(value: unknown, unit?: string): string {
    if (value === null || value === undefined) return '';
    if (typeof value === 'string' || typeof value === 'number') {
        return truncate(unit ? `${value} ${unit}` : String(value));
    }
    if (typeof value === 'object') {
        const v = value as Record<string, unknown>;
        if (v.type === 'range') return truncate(`${v.min}–${v.max}${v.unit ? ` ${v.unit}` : ''}`);
        if (v.type === 'temporal') return truncate(`${v.duration} ${v.unit}`);
        if (v.type === 'standard') return truncate(`${v.value}${v.unit ? ` ${v.unit}` : ''}`);
    }
    return '';
}

function MappingPill({ mapping }: { mapping: RawMapping }) {
    const valueText = formatValue(mapping.value, mapping.unit);

    return (
        <div className="inline-flex items-center gap-1 rounded-md border bg-blue-50/60 border-blue-200 px-2 py-0.5 text-[11px]">
            <span className="font-semibold text-blue-900">{mapping.entity}</span>
            {mapping.entity_code && (
                <span className="rounded-full bg-green-50 border border-green-200 px-1 py-0 text-[9px] text-green-700">
                    {mapping.entity_system?.toUpperCase()}: {mapping.entity_code}
                </span>
            )}
            {mapping.relation && (
                <span className="text-blue-600 font-mono">{mapping.relation}</span>
            )}
            {valueText && <span className="text-blue-800">{valueText}</span>}
        </div>
    );
}

export function FieldMappingCell({ mappings }: FieldMappingCellProps) {
    if (!mappings || mappings.length === 0) {
        return <span className="text-muted-foreground text-xs italic">—</span>;
    }

    return (
        <div className="flex flex-wrap gap-1">
            {mappings.slice(0, 3).map((m, i) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: mappings have no stable id
                <MappingPill key={i} mapping={m as unknown as RawMapping} />
            ))}
            {mappings.length > 3 && (
                <span className="text-xs text-muted-foreground">+{mappings.length - 3} more</span>
            )}
        </div>
    );
}
