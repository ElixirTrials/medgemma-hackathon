import { X } from 'lucide-react';

interface FilterChipProps {
    label: string;
    value: string;
    onRemove: () => void;
}

export function FilterChip({ label, value, onRemove }: FilterChipProps) {
    return (
        <span className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-800 transition-all duration-200 animate-in fade-in slide-in-from-left-1">
            <span className="text-blue-500">{label}:</span>
            <span>{value}</span>
            <button
                type="button"
                onClick={onRemove}
                className="ml-0.5 rounded-full p-0.5 hover:bg-blue-200 transition-colors"
            >
                <X className="h-3 w-3" />
            </button>
        </span>
    );
}

interface ProtocolOption {
    id: string;
    title: string;
}

interface FilterBarProps {
    protocolId: string;
    setProtocolId: (v: string) => void;
    protocols: ProtocolOption[];
    criteriaType: string;
    setCriteriaType: (v: string) => void;
    category: string;
    setCategory: (v: string) => void;
    minConfidence: string;
    setMinConfidence: (v: string) => void;
}

const CRITERIA_TYPES = ['inclusion', 'exclusion'];
const CATEGORIES = [
    'medical_history',
    'lab_values',
    'medications',
    'procedures',
    'demographics',
    'other',
];

export function FilterBar({
    protocolId,
    setProtocolId,
    protocols,
    criteriaType,
    setCriteriaType,
    category,
    setCategory,
    minConfidence,
    setMinConfidence,
}: FilterBarProps) {
    return (
        <div className="flex flex-wrap items-center gap-3">
            <select
                value={protocolId}
                onChange={(e) => setProtocolId(e.target.value)}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
            >
                <option value="">All protocols</option>
                {protocols.map((p) => (
                    <option key={p.id} value={p.id}>
                        {p.title || p.id}
                    </option>
                ))}
            </select>

            <select
                value={criteriaType}
                onChange={(e) => setCriteriaType(e.target.value)}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
            >
                <option value="">All types</option>
                {CRITERIA_TYPES.map((t) => (
                    <option key={t} value={t}>
                        {t.charAt(0).toUpperCase() + t.slice(1)}
                    </option>
                ))}
            </select>

            <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
            >
                <option value="">All categories</option>
                {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                        {c.replace(/_/g, ' ')}
                    </option>
                ))}
            </select>

            <div className="flex items-center gap-1.5">
                <label htmlFor="min-confidence" className="text-xs text-muted-foreground">
                    Min confidence:
                </label>
                <input
                    id="min-confidence"
                    type="number"
                    min="0"
                    max="1"
                    step="0.1"
                    value={minConfidence}
                    onChange={(e) => setMinConfidence(e.target.value)}
                    className="w-16 rounded-md border border-input bg-background px-2 py-1.5 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
                    placeholder="0.0"
                />
            </div>

            {/* Active filter chips */}
            <div className="flex flex-wrap gap-1.5">
                {protocolId && (
                    <FilterChip
                        label="Protocol"
                        value={protocols.find((p) => p.id === protocolId)?.title || protocolId}
                        onRemove={() => setProtocolId('')}
                    />
                )}
                {criteriaType && (
                    <FilterChip
                        label="Type"
                        value={criteriaType}
                        onRemove={() => setCriteriaType('')}
                    />
                )}
                {category && (
                    <FilterChip
                        label="Category"
                        value={category.replace(/_/g, ' ')}
                        onRemove={() => setCategory('')}
                    />
                )}
                {minConfidence && (
                    <FilterChip
                        label="Min conf"
                        value={minConfidence}
                        onRemove={() => setMinConfidence('')}
                    />
                )}
            </div>
        </div>
    );
}
