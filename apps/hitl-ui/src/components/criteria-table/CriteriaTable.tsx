import {
    type ColumnDef,
    type SortingState,
    flexRender,
    getCoreRowModel,
    getSortedRowModel,
    useReactTable,
} from '@tanstack/react-table';
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, ChevronRight } from 'lucide-react';
import { useState } from 'react';

import type { StructuredCriterionRow } from '../../hooks/useCriteriaSpreadsheet';
import { cn } from '../../lib/utils';
import { ExpressionTreeCell } from './ExpressionTreeCell';

interface CriteriaTableProps {
    data: StructuredCriterionRow[];
    columns: ColumnDef<StructuredCriterionRow>[];
}

function ExpandedRow({ row }: { row: StructuredCriterionRow }) {
    return (
        <tr>
            <td colSpan={11} className="bg-muted/30 px-6 py-4 border-b">
                <div className="space-y-3">
                    <div>
                        <h4 className="text-xs font-semibold text-muted-foreground mb-1">
                            Full Criterion Text
                        </h4>
                        <p className="text-sm leading-relaxed">{row.text}</p>
                    </div>
                    {row.structured_criterion && (
                        <div>
                            <h4 className="text-xs font-semibold text-muted-foreground mb-1">
                                Expression Tree
                            </h4>
                            <ExpressionTreeCell tree={row.structured_criterion} expanded />
                        </div>
                    )}
                    {row.field_mappings.length > 0 && (
                        <div>
                            <h4 className="text-xs font-semibold text-muted-foreground mb-1">
                                All Field Mappings ({row.field_mappings.length})
                            </h4>
                            <div className="grid gap-1">
                                {row.field_mappings.map((m, i) => (
                                    <div
                                        // biome-ignore lint/suspicious/noArrayIndexKey: no stable id
                                        key={i}
                                        className="inline-flex items-center gap-2 rounded border bg-blue-50/60 border-blue-200 px-2 py-1 text-xs"
                                    >
                                        <span className="font-semibold text-blue-900">
                                            {(m as Record<string, string>).entity || '?'}
                                        </span>
                                        <span className="font-mono text-blue-600">
                                            {(m as Record<string, string>).relation}
                                        </span>
                                        <span>
                                            {String((m as Record<string, unknown>).value ?? '')}
                                        </span>
                                        {(m as Record<string, string>).unit && (
                                            <span className="text-muted-foreground">
                                                {(m as Record<string, string>).unit}
                                            </span>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </td>
        </tr>
    );
}

export function CriteriaTable({ data, columns }: CriteriaTableProps) {
    const [sorting, setSorting] = useState<SortingState>([]);
    const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

    const table = useReactTable({
        data,
        columns,
        state: { sorting },
        onSortingChange: setSorting,
        getCoreRowModel: getCoreRowModel(),
        getSortedRowModel: getSortedRowModel(),
    });

    const toggleRow = (id: string) => {
        setExpandedRows((prev) => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    };

    return (
        <div className="rounded-lg border bg-card shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
                <table className="w-full">
                    <thead className="sticky top-0 z-10 bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80 border-b">
                        {table.getHeaderGroups().map((headerGroup) => (
                            <tr key={headerGroup.id}>
                                <th className="w-8 px-2 py-3" />
                                {headerGroup.headers.map((header) => (
                                    <th
                                        key={header.id}
                                        className={cn(
                                            'px-3 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider',
                                            header.column.getCanSort() &&
                                                'cursor-pointer select-none hover:text-foreground transition-colors'
                                        )}
                                        style={{ width: header.getSize() }}
                                        onClick={header.column.getToggleSortingHandler()}
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter' || e.key === ' ') {
                                                e.preventDefault();
                                                header.column.getToggleSortingHandler()?.(e);
                                            }
                                        }}
                                        tabIndex={header.column.getCanSort() ? 0 : undefined}
                                    >
                                        <div className="flex items-center gap-1">
                                            {flexRender(
                                                header.column.columnDef.header,
                                                header.getContext()
                                            )}
                                            {header.column.getCanSort() && (
                                                <span className="text-muted-foreground/50">
                                                    {header.column.getIsSorted() === 'asc' ? (
                                                        <ArrowUp className="h-3 w-3" />
                                                    ) : header.column.getIsSorted() === 'desc' ? (
                                                        <ArrowDown className="h-3 w-3" />
                                                    ) : (
                                                        <ArrowUpDown className="h-3 w-3" />
                                                    )}
                                                </span>
                                            )}
                                        </div>
                                    </th>
                                ))}
                            </tr>
                        ))}
                    </thead>
                    <tbody>
                        {table.getRowModel().rows.map((row, idx) => {
                            const isExpanded = expandedRows.has(row.original.id);
                            return (
                                <>
                                    <tr
                                        key={row.id}
                                        className={cn(
                                            'border-b transition-colors duration-150',
                                            idx % 2 === 0 ? 'bg-background' : 'bg-muted/20',
                                            'hover:bg-accent/50',
                                            isExpanded && 'bg-accent/30'
                                        )}
                                    >
                                        <td className="w-8 px-2 py-2">
                                            <button
                                                type="button"
                                                onClick={() => toggleRow(row.original.id)}
                                                className="p-0.5 rounded hover:bg-muted transition-colors"
                                            >
                                                {isExpanded ? (
                                                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                                                ) : (
                                                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                                                )}
                                            </button>
                                        </td>
                                        {row.getVisibleCells().map((cell) => (
                                            <td
                                                key={cell.id}
                                                className="px-3 py-2.5 text-sm align-top"
                                            >
                                                {flexRender(
                                                    cell.column.columnDef.cell,
                                                    cell.getContext()
                                                )}
                                            </td>
                                        ))}
                                    </tr>
                                    {isExpanded && (
                                        <ExpandedRow
                                            key={`${row.id}-expanded`}
                                            row={row.original}
                                        />
                                    )}
                                </>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {data.length === 0 && (
                <div className="py-12 text-center text-muted-foreground">
                    <p className="text-lg font-medium">No criteria found</p>
                    <p className="text-sm mt-1">
                        Try adjusting your filters or upload a protocol first.
                    </p>
                </div>
            )}
        </div>
    );
}
