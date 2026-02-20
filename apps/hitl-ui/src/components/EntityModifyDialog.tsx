import * as Dialog from '@radix-ui/react-dialog';
import { ExternalLink, Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';

import type { EntityActionRequest, EntityResponse } from '../hooks/useEntities';
import type { TerminologySearchResult } from '../hooks/useTerminologySearch';
import { EntityTypeBadge, GroundingConfidenceBadge, getRelevantSystems } from './EntityCard';
import { ErrorBadge, TerminologyBadge } from './TerminologyBadge';
import { TerminologyCombobox } from './TerminologyCombobox';
import { Button } from './ui/Button';

interface EntityModifyDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    entity: EntityResponse;
    onSave: (payload: Omit<EntityActionRequest, 'action' | 'reviewer_id'>) => void;
    isSubmitting: boolean;
}

export default function EntityModifyDialog({
    open,
    onOpenChange,
    entity,
    onSave,
    isSubmitting,
}: EntityModifyDialogProps) {
    const [editCui, setEditCui] = useState(entity.umls_cui ?? '');
    const [editSnomed, setEditSnomed] = useState(entity.snomed_code ?? '');
    const [editPreferredTerm, setEditPreferredTerm] = useState(entity.preferred_term ?? '');
    const [editRxnorm, setEditRxnorm] = useState(entity.rxnorm_code ?? '');
    const [editIcd10, setEditIcd10] = useState(entity.icd10_code ?? '');
    const [editLoinc, setEditLoinc] = useState(entity.loinc_code ?? '');
    const [editHpo, setEditHpo] = useState(entity.hpo_code ?? '');

    const relevantSystems = getRelevantSystems(entity.entity_type);

    // Reset state when dialog closes
    useEffect(() => {
        if (!open) {
            setEditCui(entity.umls_cui ?? '');
            setEditSnomed(entity.snomed_code ?? '');
            setEditPreferredTerm(entity.preferred_term ?? '');
            setEditRxnorm(entity.rxnorm_code ?? '');
            setEditIcd10(entity.icd10_code ?? '');
            setEditLoinc(entity.loinc_code ?? '');
            setEditHpo(entity.hpo_code ?? '');
        }
    }, [open, entity]);

    function handleSave() {
        onSave({
            modified_umls_cui: editCui || undefined,
            modified_snomed_code: editSnomed || undefined,
            modified_preferred_term: editPreferredTerm || undefined,
            modified_rxnorm_code: editRxnorm || undefined,
            modified_icd10_code: editIcd10 || undefined,
            modified_loinc_code: editLoinc || undefined,
            modified_hpo_code: editHpo || undefined,
        });
        onOpenChange(false);
    }

    function changed(current: string, original: string | null): boolean {
        return current !== (original ?? '');
    }

    return (
        <Dialog.Root open={open} onOpenChange={onOpenChange}>
            <Dialog.Portal>
                <Dialog.Overlay className="fixed inset-0 bg-black/50 z-50" />
                <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white dark:bg-card rounded-lg p-6 max-w-lg w-full z-50 shadow-lg max-h-[85vh] overflow-y-auto">
                    {/* Title bar */}
                    <Dialog.Title className="text-base font-semibold mb-1 flex flex-wrap items-center gap-2">
                        Modify Entity: {entity.text}
                    </Dialog.Title>
                    <div className="flex flex-wrap items-center gap-2 mb-4">
                        <EntityTypeBadge type={entity.entity_type} />
                        <GroundingConfidenceBadge confidence={entity.grounding_confidence} />
                    </div>

                    {/* System Selected panel */}
                    <div className="bg-muted/30 border rounded-lg p-4 mb-4">
                        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
                            System Selected
                        </h3>
                        <div className="flex flex-wrap gap-1.5 mb-2">
                            {entity.rxnorm_code && (
                                <TerminologyBadge system="rxnorm" code={entity.rxnorm_code} />
                            )}
                            {entity.icd10_code && (
                                <TerminologyBadge system="icd10" code={entity.icd10_code} />
                            )}
                            {entity.snomed_code && (
                                <TerminologyBadge
                                    system="snomed"
                                    code={entity.snomed_code}
                                    display={entity.preferred_term ?? undefined}
                                />
                            )}
                            {entity.loinc_code && (
                                <TerminologyBadge system="loinc" code={entity.loinc_code} />
                            )}
                            {entity.hpo_code && (
                                <TerminologyBadge system="hpo" code={entity.hpo_code} />
                            )}
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
                            {entity.grounding_error && (
                                <ErrorBadge errorReason={entity.grounding_error} />
                            )}
                        </div>
                        {entity.preferred_term && (
                            <p className="text-xs text-muted-foreground">
                                Preferred term: {entity.preferred_term}
                            </p>
                        )}
                        {entity.grounding_method && (
                            <p className="text-xs text-muted-foreground">
                                Method: {entity.grounding_method}
                            </p>
                        )}
                    </div>

                    {/* Your Corrections section */}
                    <div className="space-y-3 mb-4">
                        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                            Your Corrections
                        </h3>

                        {relevantSystems.includes('rxnorm') && (
                            <div>
                                <span className="block text-xs font-medium text-muted-foreground mb-1">
                                    RxNorm
                                    {changed(editRxnorm, entity.rxnorm_code) && (
                                        <span className="ml-1 text-amber-600">(changed)</span>
                                    )}
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
                                    {changed(editIcd10, entity.icd10_code) && (
                                        <span className="ml-1 text-amber-600">(changed)</span>
                                    )}
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
                                    {changed(editSnomed, entity.snomed_code) && (
                                        <span className="ml-1 text-amber-600">(changed)</span>
                                    )}
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
                                    {changed(editLoinc, entity.loinc_code) && (
                                        <span className="ml-1 text-amber-600">(changed)</span>
                                    )}
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
                                    {changed(editHpo, entity.hpo_code) && (
                                        <span className="ml-1 text-amber-600">(changed)</span>
                                    )}
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
                                {changed(editPreferredTerm, entity.preferred_term) && (
                                    <span className="ml-1 text-amber-600">(changed)</span>
                                )}
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
                        {/* Manual CUI/SNOMED fallback inputs */}
                        <div className="grid grid-cols-2 gap-2">
                            <label className="block">
                                <span className="block text-xs font-medium text-muted-foreground mb-1">
                                    CUI (manual)
                                    {changed(editCui, entity.umls_cui) && (
                                        <span className="ml-1 text-amber-600">(changed)</span>
                                    )}
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
                                    {changed(editSnomed, entity.snomed_code) && (
                                        <span className="ml-1 text-amber-600">(changed)</span>
                                    )}
                                </span>
                                <input
                                    type="text"
                                    value={editSnomed}
                                    onChange={(e) => setEditSnomed(e.target.value)}
                                    className="w-full rounded-md border border-input bg-muted/50 px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                />
                            </label>
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="flex items-center justify-end gap-2 pt-3 border-t">
                        <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => onOpenChange(false)}
                            disabled={isSubmitting}
                        >
                            Cancel
                        </Button>
                        <Button size="sm" onClick={handleSave} disabled={isSubmitting}>
                            {isSubmitting ? (
                                <Loader2 className="h-4 w-4 animate-spin mr-1" />
                            ) : null}
                            Save
                        </Button>
                    </div>
                </Dialog.Content>
            </Dialog.Portal>
        </Dialog.Root>
    );
}
