import { ChevronLeft, ChevronRight, Loader2, Search } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Button } from '../components/ui/Button';
import { useProtocolList } from '../hooks/useProtocols';
import type { SearchFilters } from '../hooks/useSearch';
import { useCriteriaSearch } from '../hooks/useSearch';
import { cn } from '../lib/utils';

function ConfidenceBadge({ confidence }: { confidence: number }) {
    const percentage = Math.round(confidence * 100);

    let label: string;
    let colorClass: string;

    if (confidence >= 0.85) {
        label = 'High';
        colorClass = 'bg-green-100 text-green-800';
    } else if (confidence >= 0.7) {
        label = 'Medium';
        colorClass = 'bg-yellow-100 text-yellow-800';
    } else {
        label = 'Low';
        colorClass = 'bg-red-100 text-red-800';
    }

    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
                colorClass
            )}
        >
            {label} ({percentage}%)
        </span>
    );
}

function ReviewStatusBadge({ status }: { status: string | null }) {
    const statusConfig: Record<string, { label: string; colorClass: string }> = {
        approved: { label: 'Approved', colorClass: 'bg-green-100 text-green-800' },
        rejected: { label: 'Rejected', colorClass: 'bg-red-100 text-red-800' },
        modified: { label: 'Modified', colorClass: 'bg-yellow-100 text-yellow-800' },
    };

    const config = status ? statusConfig[status] : null;
    const label = config?.label ?? 'Pending';
    const colorClass = config?.colorClass ?? 'bg-gray-100 text-gray-800';

    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
                colorClass
            )}
        >
            {label}
        </span>
    );
}

function CriteriaTypeBadge({ type }: { type: string }) {
    const colorClass =
        type === 'inclusion' ? 'bg-blue-100 text-blue-800' : 'bg-orange-100 text-orange-800';

    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize',
                colorClass
            )}
        >
            {type}
        </span>
    );
}

export default function SearchPage() {
    const [query, setQuery] = useState('');
    const [debouncedQuery, setDebouncedQuery] = useState('');
    const [filters, setFilters] = useState<SearchFilters>({});
    const [page, setPage] = useState(1);
    const pageSize = 20;

    // Debounce search query
    const [debounceTimer, setDebounceTimer] = useState<NodeJS.Timeout | null>(null);

    function handleQueryChange(newQuery: string) {
        setQuery(newQuery);

        if (debounceTimer) {
            clearTimeout(debounceTimer);
        }

        const timer = setTimeout(() => {
            setDebouncedQuery(newQuery);
            setPage(1);
        }, 300);

        setDebounceTimer(timer);
    }

    // Fetch protocols for dropdown
    const { data: protocolsData } = useProtocolList(1, 100);

    // Search results
    const {
        data: searchData,
        isLoading,
        error,
    } = useCriteriaSearch(debouncedQuery, filters, page, pageSize);

    function handleFilterChange(filterKey: keyof SearchFilters, value: string) {
        setFilters((prev) => ({
            ...prev,
            [filterKey]: value || undefined,
        }));
        setPage(1);
    }

    function handleClearFilters() {
        setFilters({});
        setPage(1);
    }

    const hasFilters = filters.protocol_id || filters.criteria_type || filters.review_status;
    const showResults = debouncedQuery.length >= 2;

    return (
        <div className="container mx-auto p-6">
            <header className="mb-6">
                <h1 className="text-3xl font-bold text-foreground mb-2">Search Criteria</h1>
                <p className="text-muted-foreground">
                    Search across all eligibility criteria with relevance ranking
                </p>
            </header>

            {/* Search bar */}
            <div className="mb-6">
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => handleQueryChange(e.target.value)}
                        placeholder="Search for criteria (e.g., diabetes, age, blood pressure)..."
                        className="w-full pl-10 pr-4 py-3 rounded-lg border border-input bg-background text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                </div>
            </div>

            {/* Filter bar */}
            <div className="mb-6 p-4 rounded-lg border bg-card">
                <div className="flex items-center gap-4 flex-wrap">
                    <span className="text-sm font-medium text-muted-foreground">Filters:</span>

                    <select
                        value={filters.protocol_id || ''}
                        onChange={(e) => handleFilterChange('protocol_id', e.target.value)}
                        className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                    >
                        <option value="">All Protocols</option>
                        {protocolsData?.items.map((protocol) => (
                            <option key={protocol.id} value={protocol.id}>
                                {protocol.title}
                            </option>
                        ))}
                    </select>

                    <select
                        value={filters.criteria_type || ''}
                        onChange={(e) => handleFilterChange('criteria_type', e.target.value)}
                        className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                    >
                        <option value="">All Types</option>
                        <option value="inclusion">Inclusion</option>
                        <option value="exclusion">Exclusion</option>
                    </select>

                    <select
                        value={filters.review_status || ''}
                        onChange={(e) => handleFilterChange('review_status', e.target.value)}
                        className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                    >
                        <option value="">All Status</option>
                        <option value="approved">Approved</option>
                        <option value="rejected">Rejected</option>
                        <option value="modified">Modified</option>
                        <option value="pending">Pending</option>
                    </select>

                    {hasFilters && (
                        <Button variant="outline" size="sm" onClick={handleClearFilters}>
                            Clear Filters
                        </Button>
                    )}
                </div>
            </div>

            {/* Results */}
            {!showResults ? (
                <div className="text-center py-16 rounded-lg border bg-card">
                    <Search className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                    <h3 className="text-lg font-medium text-foreground mb-2">
                        Search across all criteria
                    </h3>
                    <p className="text-muted-foreground">
                        Try terms like "diabetes", "age", "blood pressure", or "BMI"
                    </p>
                </div>
            ) : isLoading ? (
                <div className="flex items-center justify-center py-16">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
            ) : error ? (
                <div className="text-center py-16 rounded-lg border border-destructive/50 bg-destructive/10">
                    <p className="text-destructive">Failed to search: {error.message}</p>
                </div>
            ) : searchData && searchData.items.length === 0 ? (
                <div className="text-center py-16 rounded-lg border bg-card">
                    <h3 className="text-lg font-medium text-foreground mb-2">
                        No criteria match "{debouncedQuery}"
                    </h3>
                    <p className="text-muted-foreground">Try different search terms</p>
                </div>
            ) : (
                <>
                    {/* Results summary */}
                    <div className="mb-4 flex items-center justify-between">
                        <p className="text-sm text-muted-foreground">
                            Found {searchData?.total ?? 0} results for "{debouncedQuery}"
                        </p>
                        <p className="text-sm text-muted-foreground">
                            Page {page} of {searchData?.pages ?? 1}
                        </p>
                    </div>

                    {/* Results list */}
                    <div className="space-y-4 mb-6">
                        {searchData?.items.map((result) => (
                            <div
                                key={result.id}
                                className="rounded-lg border bg-card p-4 hover:shadow-md transition-shadow"
                            >
                                <div className="flex items-start justify-between gap-4 mb-3">
                                    <Link
                                        to={`/protocols/${result.protocol_id}`}
                                        className="text-sm font-medium text-primary hover:underline"
                                    >
                                        {result.protocol_title}
                                    </Link>
                                    <span className="text-xs text-muted-foreground whitespace-nowrap">
                                        Rank #{result.rank}
                                    </span>
                                </div>

                                <div className="flex flex-wrap items-center gap-2 mb-3">
                                    <CriteriaTypeBadge type={result.criteria_type} />
                                    <ConfidenceBadge confidence={result.confidence} />
                                    <ReviewStatusBadge status={result.review_status} />
                                </div>

                                <p className="text-sm text-foreground mb-3">{result.text}</p>

                                <Link
                                    to={`/reviews/${result.batch_id}`}
                                    className="text-sm text-primary hover:underline"
                                >
                                    View in Review →
                                </Link>
                            </div>
                        ))}
                    </div>

                    {/* Pagination */}
                    {searchData && searchData.pages > 1 && (
                        <div className="flex items-center justify-center gap-2">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setPage((p) => Math.max(1, p - 1))}
                                disabled={page === 1}
                            >
                                <ChevronLeft className="h-4 w-4" />
                                Previous
                            </Button>
                            <span className="text-sm text-muted-foreground px-4">
                                Page {page} of {searchData.pages}
                            </span>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setPage((p) => Math.min(searchData.pages, p + 1))}
                                disabled={page === searchData.pages}
                            >
                                Next
                                <ChevronRight className="h-4 w-4" />
                            </Button>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
