import { cn } from '../lib/utils';

export type TerminologySystem = 'rxnorm' | 'icd10' | 'snomed' | 'loinc' | 'hpo' | 'umls';

const SYSTEM_COLORS: Record<TerminologySystem, string> = {
    rxnorm: 'bg-blue-100 text-blue-800 border-blue-300',
    icd10: 'bg-orange-100 text-orange-800 border-orange-300',
    snomed: 'bg-green-100 text-green-800 border-green-300',
    loinc: 'bg-purple-100 text-purple-800 border-purple-300',
    hpo: 'bg-teal-100 text-teal-800 border-teal-300',
    umls: 'bg-indigo-100 text-indigo-800 border-indigo-300',
};

const SYSTEM_LABELS: Record<TerminologySystem, string> = {
    rxnorm: 'RxNorm',
    icd10: 'ICD-10',
    snomed: 'SNOMED',
    loinc: 'LOINC',
    hpo: 'HPO',
    umls: 'CUI',
};

interface TerminologyBadgeProps {
    system: TerminologySystem;
    code: string;
    display?: string;
    className?: string;
}

export function TerminologyBadge({ system, code, display, className }: TerminologyBadgeProps) {
    const colors = SYSTEM_COLORS[system];
    const label = SYSTEM_LABELS[system];

    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium',
                colors,
                className
            )}
        >
            {label}: {code}
            {display && <span className="ml-1 opacity-75">({display})</span>}
        </span>
    );
}

interface ErrorBadgeProps {
    errorReason: string;
    className?: string;
}

export function ErrorBadge({ errorReason, className }: ErrorBadgeProps) {
    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full border border-red-300 bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800',
                className
            )}
            title={errorReason}
        >
            Failed: {errorReason}
        </span>
    );
}
