import {
    CheckCircle,
    ChevronDown,
    ChevronUp,
    ExternalLink,
    Loader2,
    Pencil,
    XCircle,
} from 'lucide-react';
import { useState } from 'react';

import type { EntityActionRequest, EntityResponse } from '../hooks/useEntities';
import type { TerminologySearchResult } from '../hooks/useTerminologySearch';
import { cn } from '../lib/utils';
import { ErrorBadge, TerminologyBadge } from './TerminologyBadge';
import { TerminologyCombobox } from './TerminologyCombobox';
import { Button } from './ui/Button';

interface EntityCardProps {
    entity: EntityResponse;
    onAction: (entityId: string, action: EntityActionRequest) => void;
    isSubmitting: boolean;
}

function EntityTypeBadge({ type }: { type: string }) {
    const typeConfig: Record<string, { label: string; colorClass: string }> = {
        Condition: { label: 'Condition', colorClass: 'bg-blue-100 text-blue-800' },
        Medication: { label: 'Medication', colorClass: 'bg-purple-100 text-purple-800' },
        Procedure: { label: 'Procedure', colorClass: 'bg-green-100 text-green-800' },
        Lab_Value: { label: 'Lab Value', colorClass: 'bg-orange-100 text-orange-800' },
        Demographic: { label: 'Demographic', colorClass: 'bg-gray-100 text-gray-800' },
        Biomarker: { label: 'Biomarker', colorClass: 'bg-teal-100 text-teal-800' },
    };

    const config = typeConfig[type] || { label: type, colorClass: 'bg-gray-100 text-gray-800' };

    return (
        <span
            className={cn(
                'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
                config.colorClass
            )}
        >
            {config.label}
        </span>
    );
}

function GroundingConfidenceBadge({ confidence }: { confidence: number | null }) {
    if (confidence === null) {
        return (
            <span className="inline-flex items-center rounded-full bg-gray-100 text-gray-800 px-2.5 py-0.5 text-xs font-medium">
                No confidence
            </span>
        );
    }

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
            title={`Grounding confidence: ${percentage}%`}
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

/** Determine which systems are relevant for a given entity type. */
function getRelevantSystems(entityType: string): string[] {
    switch (entityType) {
        case 'Medication':
            return ['rxnorm', 'umls'];
        case 'Condition':
            return ['icd10', 'snomed', 'umls'];
        case 'Lab_Value':
            return ['loinc', 'umls'];
        case 'Biomarker':
            return ['hpo', 'umls'];
        default:
            return ['snomed', 'umls'];
    }
}

export default function EntityCard({ entity, onAction, isSubmitting }: EntityCardProps) {
    const [isEditing, setIsEditing] = useState(false);
    const [contextOpen, setContextOpen] = useState(false);

    // Edit state for all code fields
    const [editCui, setEditCui] = useState(entity.umls_cui ?? '');
    const [editSnomed, setEditSnomed] = useState(entity.snomed_code ?? '');
    const [editPreferredTerm, setEditPreferredTerm] = useState(entity.preferred_term ?? '');
    const [editRxnorm, setEditRxnorm] = useState(entity.rxnorm_code ?? '');
    const [editIcd10, setEditIcd10] = useState(entity.icd10_code ?? '');
    const [editLoinc, setEditLoinc] = useState(entity.loinc_code ?? '');
    const [editHpo, setEditHpo] = useState(entity.hpo_code ?? '');

    const isLowConfidence = (entity.grounding_confidence ?? 0) < 0.7;
    const relevantSystems = getRelevantSystems(entity.entity_type);

    // Check if entity has any codes
    const hasCodes =
        entity.umls_cui ||
        entity.snomed_code ||
        entity.rxnorm_code ||
        entity.icd10_code ||
        entity.loinc_code ||
        entity.hpo_code;

    function handleApprove() {
        onAction(entity.id, {
            action: 'approve',
            reviewer_id: 'current-user',
        });
    }

    function handleReject() {
        onAction(entity.id, {
            action: 'reject',
            reviewer_id: 'current-user',
        });
    }

    function handleModifySave() {
        onAction(entity.id, {
            action: 'modify',
            reviewer_id: 'current-user',
            modified_umls_cui: editCui || undefined,
            modified_snomed_code: editSnomed || undefined,
            modified_preferred_term: editPreferredTerm || undefined,
            modified_rxnorm_code: editRxnorm || undefined,
            modified_icd10_code: editIcd10 || undefined,
            modified_loinc_code: editLoinc || undefined,
            modified_hpo_code: editHpo || undefined,
        });
        setIsEditing(false);
    }

    function handleModifyCancel() {
        setEditCui(entity.umls_cui ?? '');
        setEditSnomed(entity.snomed_code ?? '');
        setEditPreferredTerm(entity.preferred_term ?? '');
        setEditRxnorm(entity.rxnorm_code ?? '');
        setEditIcd10(entity.icd10_code ?? '');
        setEditLoinc(entity.loinc_code ?? '');
        setEditHpo(entity.hpo_code ?? '');
        setIsEditing(false);
    }

    const contextText = entity.context_window?.text as string | undefined;

    return (
        <div
            className={cn(
                'rounded-lg border bg-card p-4 shadow-sm',
                isLowConfidence && 'border-l-4 border-l-red-300'
            )}
        >
            {/* Header row */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
                <EntityTypeBadge type={entity.entity_type} />
                <GroundingConfidenceBadge confidence={entity.grounding_confidence} />
                <ReviewStatusBadge status={entity.review_status} />
                {entity.grounding_method && (
                    <span
                        className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-600"
                        title={`Grounding method: ${entity.grounding_method}`}
                    >
                        {entity.grounding_method}
                    </span>
                )}
            </div>

            {/* Entity text */}
            <p className="text-sm font-medium text-foreground mb-3">{entity.text}</p>

            {/* Multi-code badge section */}
            <div className="flex flex-wrap gap-1.5 mb-3">
                {entity.rxnorm_code && (
                    <TerminologyBadge system="rxnorm" code={entity.rxnorm_code} />
                )}
                {entity.icd10_code && <TerminologyBadge system="icd10" code={entity.icd10_code} />}
                {entity.snomed_code && (
                    <TerminologyBadge
                        system="snomed"
                        code={entity.snomed_code}
                        display={entity.preferred_term ?? undefined}
                    />
                )}
                {entity.loinc_code && <TerminologyBadge system="loinc" code={entity.loinc_code} />}
                {entity.hpo_code && <TerminologyBadge system="hpo" code={entity.hpo_code} />}
                {entity.umls_cui && (
                    <a
                        href={`https://uts.nlm.nih.gov/cts/umls/concept/${entity.umls_cui}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 rounded-full border border-indigo-300 bg-indigo-100 px-2.5 py-0.5 text-xs font-medium text-indigo-800 hover:bg-indigo-200 transition-colors"
                    >
                        CUI: {entity.umls_cui}
                        <ExternalLink className="h-3 w-3" />
                    </a>
                )}
                {entity.grounding_error && <ErrorBadge errorReason={entity.grounding_error} />}
                {!hasCodes && !entity.grounding_error && (
                    <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-500">
                        Not grounded
                    </span>
                )}
            </div>

            {/* Edit mode */}
            {isEditing && (
                <div className="space-y-3 mb-3 border-t pt-3">
                    {/* Per-system comboboxes for relevant systems */}
                    {relevantSystems.includes('rxnorm') && (
                        <div>
                            <span className="block text-xs font-medium text-muted-foreground mb-1">
                                RxNorm
                            </span>
                            <TerminologyCombobox
                                system="rxnorm"
                                value={editRxnorm}
                                onChange={(val) => setEditRxnorm(val)}
                                onSelect={(result: TerminologySearchResult) => {
                                    setEditRxnorm(result.code);
                                }}
                            />
                        </div>
                    )}
                    {relevantSystems.includes('icd10') && (
                        <div>
                            <span className="block text-xs font-medium text-muted-foreground mb-1">
                                ICD-10
                            </span>
                            <TerminologyCombobox
                                system="icd10"
                                value={editIcd10}
                                onChange={(val) => setEditIcd10(val)}
                                onSelect={(result: TerminologySearchResult) => {
                                    setEditIcd10(result.code);
                                }}
                            />
                        </div>
                    )}
                    {relevantSystems.includes('snomed') && (
                        <div>
                            <span className="block text-xs font-medium text-muted-foreground mb-1">
                                SNOMED
                            </span>
                            <TerminologyCombobox
                                system="snomed"
                                value={editSnomed}
                                onChange={(val) => setEditSnomed(val)}
                                onSelect={(result: TerminologySearchResult) => {
                                    setEditSnomed(result.code);
                                    if (result.display) setEditPreferredTerm(result.display);
                                }}
                            />
                        </div>
                    )}
                    {relevantSystems.includes('loinc') && (
                        <div>
                            <span className="block text-xs font-medium text-muted-foreground mb-1">
                                LOINC
                            </span>
                            <TerminologyCombobox
                                system="loinc"
                                value={editLoinc}
                                onChange={(val) => setEditLoinc(val)}
                                onSelect={(result: TerminologySearchResult) => {
                                    setEditLoinc(result.code);
                                }}
                            />
                        </div>
                    )}
                    {relevantSystems.includes('hpo') && (
                        <div>
                            <span className="block text-xs font-medium text-muted-foreground mb-1">
                                HPO
                            </span>
                            <TerminologyCombobox
                                system="hpo"
                                value={editHpo}
                                onChange={(val) => setEditHpo(val)}
                                onSelect={(result: TerminologySearchResult) => {
                                    setEditHpo(result.code);
                                }}
                            />
                        </div>
                    )}
                    {/* UMLS always shown */}
                    <div>
                        <span className="block text-xs font-medium text-muted-foreground mb-1">
                            UMLS
                        </span>
                        <TerminologyCombobox
                            system="umls"
                            value={editPreferredTerm}
                            onChange={(val) => setEditPreferredTerm(val)}
                            onSelect={(result: TerminologySearchResult) => {
                                setEditCui(result.code);
                                setEditPreferredTerm(result.display);
                            }}
                        />
                    </div>
                    {/* Manual CUI input fallback */}
                    <div className="grid grid-cols-2 gap-2">
                        <label className="block">
                            <span className="block text-xs font-medium text-muted-foreground mb-1">
                                CUI (manual)
                            </span>
                            <input
                                type="text"
                                value={editCui}
                                onChange={(e) => setEditCui(e.target.value)}
                                className="w-full rounded-md border border-input bg-muted/50 px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            />
                        </label>
                        <label className="block">
                            <span className="block text-xs font-medium text-muted-foreground mb-1">
                                SNOMED (manual)
                            </span>
                            <input
                                type="text"
                                value={editSnomed}
                                onChange={(e) => setEditSnomed(e.target.value)}
                                className="w-full rounded-md border border-input bg-muted/50 px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            />
                        </label>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button size="sm" onClick={handleModifySave} disabled={isSubmitting}>
                            {isSubmitting ? (
                                <Loader2 className="h-4 w-4 animate-spin mr-1" />
                            ) : null}
                            Save
                        </Button>
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={handleModifyCancel}
                            disabled={isSubmitting}
                        >
                            Cancel
                        </Button>
                    </div>
                </div>
            )}

            {/* Context window (collapsible) */}
            {contextText && (
                <div className="border-t pt-3 mb-3">
                    <button
                        type="button"
                        className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                        onClick={() => setContextOpen(!contextOpen)}
                    >
                        {contextOpen ? (
                            <ChevronUp className="h-4 w-4" />
                        ) : (
                            <ChevronDown className="h-4 w-4" />
                        )}
                        Context
                    </button>
                    {contextOpen && (
                        <p className="mt-2 text-xs text-muted-foreground bg-muted/30 rounded-md p-2">
                            {contextText}
                        </p>
                    )}
                </div>
            )}

            {/* Action buttons */}
            {!isEditing && (
                <div className="flex items-center gap-2 pt-2 border-t">
                    <Button
                        size="sm"
                        variant="outline"
                        className="text-green-700 border-green-300 hover:bg-green-50"
                        onClick={handleApprove}
                        disabled={isSubmitting || entity.review_status === 'approved'}
                    >
                        {isSubmitting ? (
                            <Loader2 className="h-4 w-4 animate-spin mr-1" />
                        ) : (
                            <CheckCircle className="h-4 w-4 mr-1" />
                        )}
                        Approve
                    </Button>
                    <Button
                        size="sm"
                        variant="outline"
                        className="text-red-700 border-red-300 hover:bg-red-50"
                        onClick={handleReject}
                        disabled={isSubmitting || entity.review_status === 'rejected'}
                    >
                        {isSubmitting ? (
                            <Loader2 className="h-4 w-4 animate-spin mr-1" />
                        ) : (
                            <XCircle className="h-4 w-4 mr-1" />
                        )}
                        Reject
                    </Button>
                    <Button
                        size="sm"
                        variant="outline"
                        className="text-blue-700 border-blue-300 hover:bg-blue-50"
                        onClick={() => setIsEditing(true)}
                        disabled={isSubmitting}
                    >
                        <Pencil className="h-4 w-4 mr-1" />
                        Modify
                    </Button>
                </div>
            )}
        </div>
    );
}
