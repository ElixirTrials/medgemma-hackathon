import type { ColumnDef } from '@tanstack/react-table';
import { Link } from 'react-router-dom';

import type { StructuredCriterionRow } from '../../hooks/useCriteriaSpreadsheet';
import { TerminologyBadge } from '../TerminologyBadge';
import type { TerminologySystem } from '../TerminologyBadge';
import { ConfidenceBadge } from './ConfidenceBadge';
import { ExpressionTreeCell } from './ExpressionTreeCell';
import { FieldMappingCell } from './FieldMappingCell';

function TypeBadge({ type }: { type: string }) {
    const isInclusion = type === 'inclusion';
    return (
        <span
            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${
                isInclusion
                    ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
                    : 'bg-red-100 text-red-800 border-red-300'
            }`}
        >
            {type}
        </span>
    );
}

function CategoryBadge({ category }: { category: string | null }) {
    if (!category) return <span className="text-muted-foreground text-xs">—</span>;

    const colors: Record<string, string> = {
        medical_history: 'bg-violet-100 text-violet-800 border-violet-300',
        lab_values: 'bg-cyan-100 text-cyan-800 border-cyan-300',
        medications: 'bg-blue-100 text-blue-800 border-blue-300',
        procedures: 'bg-orange-100 text-orange-800 border-orange-300',
        demographics: 'bg-pink-100 text-pink-800 border-pink-300',
        other: 'bg-gray-100 text-gray-700 border-gray-300',
    };

    return (
        <span
            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${
                colors[category] || colors.other
            }`}
        >
            {category.replace(/_/g, ' ')}
        </span>
    );
}

function ReviewBadge({ status }: { status: string | null }) {
    if (!status) return <span className="text-muted-foreground text-xs">pending</span>;

    const colors: Record<string, string> = {
        approved: 'bg-emerald-100 text-emerald-800 border-emerald-300',
        rejected: 'bg-red-100 text-red-800 border-red-300',
        modified: 'bg-amber-100 text-amber-800 border-amber-300',
        pending: 'bg-gray-100 text-gray-700 border-gray-300',
    };

    return (
        <span
            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${
                colors[status] || colors.pending
            }`}
        >
            {status}
        </span>
    );
}

function mapSystem(system: string | null): TerminologySystem | null {
    if (!system) return null;
    const lower = system.toLowerCase();
    const map: Record<string, TerminologySystem> = {
        rxnorm: 'rxnorm',
        'icd-10': 'icd10',
        icd10: 'icd10',
        snomed: 'snomed',
        loinc: 'loinc',
        hpo: 'hpo',
        umls: 'umls',
    };
    return map[lower] || null;
}

export const columns: ColumnDef<StructuredCriterionRow>[] = [
    {
        accessorKey: 'text',
        header: 'Criterion Text',
        size: 300,
        cell: ({ row }) => {
            const text = row.original.text;
            const truncated = text.length > 100 ? `${text.slice(0, 100)}...` : text;
            return (
                <div className="max-w-[300px]" title={text}>
                    <span className="text-sm leading-snug">{truncated}</span>
                </div>
            );
        },
    },
    {
        accessorKey: 'criteria_type',
        header: 'Type',
        size: 100,
        cell: ({ row }) => <TypeBadge type={row.original.criteria_type} />,
    },
    {
        accessorKey: 'category',
        header: 'Category',
        size: 130,
        cell: ({ row }) => <CategoryBadge category={row.original.category} />,
    },
    {
        accessorKey: 'entities',
        header: 'Entities',
        size: 200,
        cell: ({ row }) => {
            const entities = row.original.entities;
            if (!entities || entities.length === 0) {
                return <span className="text-muted-foreground text-xs italic">—</span>;
            }
            return (
                <div className="flex flex-wrap gap-1">
                    {entities.slice(0, 3).map((e) => {
                        const sys = mapSystem(e.grounding_system);
                        if (sys && e.grounding_code) {
                            return (
                                <TerminologyBadge
                                    key={e.id}
                                    system={sys}
                                    code={e.grounding_code}
                                    display={e.preferred_term || undefined}
                                />
                            );
                        }
                        return (
                            <span
                                key={e.id}
                                className="inline-flex items-center rounded-full border bg-gray-50 border-gray-200 px-2 py-0.5 text-xs"
                            >
                                {e.text}
                            </span>
                        );
                    })}
                    {entities.length > 3 && (
                        <span className="text-xs text-muted-foreground">
                            +{entities.length - 3}
                        </span>
                    )}
                </div>
            );
        },
    },
    {
        accessorKey: 'field_mappings',
        header: 'Field Mappings',
        size: 220,
        cell: ({ row }) => <FieldMappingCell mappings={row.original.field_mappings} />,
    },
    {
        accessorKey: 'structured_criterion',
        header: 'Expression Tree',
        size: 160,
        cell: ({ row }) => <ExpressionTreeCell tree={row.original.structured_criterion} />,
    },
    {
        accessorKey: 'confidence',
        header: 'Confidence',
        size: 120,
        cell: ({ row }) => <ConfidenceBadge value={row.original.confidence} />,
    },
    {
        accessorKey: 'assertion_status',
        header: 'Assertion',
        size: 100,
        cell: ({ row }) => {
            const status = row.original.assertion_status;
            if (!status) return <span className="text-muted-foreground text-xs">—</span>;
            return (
                <span className="inline-flex items-center rounded-full border bg-slate-100 border-slate-300 px-2 py-0.5 text-xs font-medium text-slate-700">
                    {status}
                </span>
            );
        },
    },
    {
        accessorKey: 'review_status',
        header: 'Review',
        size: 100,
        cell: ({ row }) => <ReviewBadge status={row.original.review_status} />,
    },
    {
        accessorKey: 'protocol_title',
        header: 'Protocol',
        size: 160,
        cell: ({ row }) => {
            const { protocol_id, protocol_title } = row.original;
            if (!protocol_id) return <span className="text-muted-foreground text-xs">—</span>;
            return (
                <Link
                    to={`/protocols/${protocol_id}`}
                    className="text-sm text-blue-600 hover:text-blue-800 hover:underline truncate block max-w-[150px]"
                    title={protocol_title || ''}
                >
                    {protocol_title || protocol_id.slice(0, 8)}
                </Link>
            );
        },
    },
    {
        accessorKey: 'page_number',
        header: 'Page',
        size: 60,
        cell: ({ row }) => {
            const page = row.original.page_number;
            return page ? (
                <span className="text-sm tabular-nums">{page}</span>
            ) : (
                <span className="text-muted-foreground text-xs">—</span>
            );
        },
    },
];
