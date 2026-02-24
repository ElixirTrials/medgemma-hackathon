import { ChevronLeft, ChevronRight, FileSpreadsheet, Loader2 } from 'lucide-react';
import { useState } from 'react';

import { CriteriaTable } from '../components/criteria-table/CriteriaTable';
import { columns } from '../components/criteria-table/columns';
import { FilterBar } from '../components/criteria-table/filters';
import { Button } from '../components/ui/Button';
import { useCriteriaSpreadsheet } from '../hooks/useCriteriaSpreadsheet';

export default function CriteriaSpreadsheet() {
    const [page, setPage] = useState(1);
    const [criteriaType, setCriteriaType] = useState('');
    const [category, setCategory] = useState('');
    const [minConfidence, setMinConfidence] = useState('');

    const { data, isLoading, error } = useCriteriaSpreadsheet({
        page,
        pageSize: 50,
        criteriaType: criteriaType || undefined,
        category: category || undefined,
        minConfidence: minConfidence ? Number.parseFloat(minConfidence) : undefined,
        sortBy: 'confidence',
        sortOrder: 'desc',
    });

    const totalCriteria = data?.total ?? 0;
    const totalPages = data?.pages ?? 1;
    const items = data?.items ?? [];

    // Stats
    const inclusionCount = items.filter((i) => i.criteria_type === 'inclusion').length;
    const exclusionCount = items.filter((i) => i.criteria_type === 'exclusion').length;
    const avgConfidence =
        items.length > 0 ? items.reduce((s, i) => s + i.confidence, 0) / items.length : 0;
    const groundedCount = items.filter((i) => i.entities.some((e) => e.grounding_code)).length;

    return (
        <div className="container mx-auto p-6 space-y-6">
            {/* Header */}
            <header className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <FileSpreadsheet className="h-7 w-7 text-blue-600" />
                    <div>
                        <h1 className="text-2xl font-bold text-foreground">Structured Criteria</h1>
                        <p className="text-sm text-muted-foreground">
                            Browse and filter extracted eligibility criteria across all protocols
                        </p>
                    </div>
                </div>
                <div className="text-sm text-muted-foreground tabular-nums">
                    {totalCriteria} criteria total
                </div>
            </header>

            {/* Stats summary */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="rounded-lg border bg-card p-4">
                    <div className="text-2xl font-bold text-emerald-600 tabular-nums">
                        {inclusionCount}
                    </div>
                    <div className="text-xs text-muted-foreground">Inclusion (this page)</div>
                </div>
                <div className="rounded-lg border bg-card p-4">
                    <div className="text-2xl font-bold text-red-600 tabular-nums">
                        {exclusionCount}
                    </div>
                    <div className="text-xs text-muted-foreground">Exclusion (this page)</div>
                </div>
                <div className="rounded-lg border bg-card p-4">
                    <div className="text-2xl font-bold text-blue-600 tabular-nums">
                        {Math.round(avgConfidence * 100)}%
                    </div>
                    <div className="text-xs text-muted-foreground">Avg confidence</div>
                </div>
                <div className="rounded-lg border bg-card p-4">
                    <div className="text-2xl font-bold text-purple-600 tabular-nums">
                        {groundedCount}
                    </div>
                    <div className="text-xs text-muted-foreground">With grounding</div>
                </div>
            </div>

            {/* Filters */}
            <div className="rounded-lg border bg-card p-4">
                <FilterBar
                    criteriaType={criteriaType}
                    setCriteriaType={(v) => {
                        setCriteriaType(v);
                        setPage(1);
                    }}
                    category={category}
                    setCategory={(v) => {
                        setCategory(v);
                        setPage(1);
                    }}
                    minConfidence={minConfidence}
                    setMinConfidence={(v) => {
                        setMinConfidence(v);
                        setPage(1);
                    }}
                />
            </div>

            {/* Table */}
            {isLoading ? (
                <div className="flex items-center justify-center py-20">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                    <span className="ml-3 text-muted-foreground">Loading criteria...</span>
                </div>
            ) : error ? (
                <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6 text-center">
                    <p className="text-destructive font-medium">Failed to load criteria</p>
                    <p className="text-sm text-muted-foreground mt-1">{String(error)}</p>
                </div>
            ) : (
                <CriteriaTable data={items} columns={columns} />
            )}

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between">
                    <div className="text-sm text-muted-foreground">
                        Page {page} of {totalPages}
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setPage((p) => Math.max(1, p - 1))}
                            disabled={page <= 1}
                        >
                            <ChevronLeft className="h-4 w-4 mr-1" />
                            Previous
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                            disabled={page >= totalPages}
                        >
                            Next
                            <ChevronRight className="h-4 w-4 ml-1" />
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
}
