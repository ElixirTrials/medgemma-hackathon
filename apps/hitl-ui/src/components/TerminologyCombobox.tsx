import * as Popover from '@radix-ui/react-popover';
import { Command } from 'cmdk';
import { Loader2 } from 'lucide-react';
import { useState } from 'react';

import type { TerminologySearchResult } from '../hooks/useTerminologySearch';
import { useTerminologySearch } from '../hooks/useTerminologySearch';
import { cn } from '../lib/utils';
import type { TerminologySystem } from './TerminologyBadge';

const SYSTEM_LABELS: Record<TerminologySystem, string> = {
    rxnorm: 'RxNorm',
    icd10: 'ICD-10',
    snomed: 'SNOMED',
    loinc: 'LOINC',
    hpo: 'HPO',
    umls: 'UMLS',
};

interface TerminologyComboboxProps {
    system: TerminologySystem;
    value: string;
    onSelect: (result: TerminologySearchResult) => void;
    onChange: (value: string) => void;
    placeholder?: string;
    className?: string;
}

export function TerminologyCombobox({
    system,
    value,
    onSelect,
    onChange,
    placeholder,
    className,
}: TerminologyComboboxProps) {
    const [open, setOpen] = useState(false);
    const [inputValue, setInputValue] = useState(value);

    const { results, isLoading, isCircuitOpen, validationHint } = useTerminologySearch(
        system,
        inputValue
    );

    const systemLabel = SYSTEM_LABELS[system];
    const resolvedPlaceholder = placeholder ?? `Search ${systemLabel}...`;

    // Show popover when there's input and either results, loading, or enough chars
    const shouldShowPopover =
        inputValue.trim().length > 0 &&
        (results.length > 0 || isLoading || inputValue.trim().length >= 3);

    function handleInputChange(newValue: string) {
        setInputValue(newValue);
        onChange(newValue);
        setOpen(true);
    }

    function handleSelect(result: TerminologySearchResult) {
        setInputValue(result.display);
        onSelect(result);
        setOpen(false);
    }

    return (
        <div>
            <Popover.Root open={open && shouldShowPopover} onOpenChange={setOpen}>
                <Popover.Trigger asChild>
                    <input
                        type="text"
                        value={inputValue}
                        onChange={(e) => handleInputChange(e.target.value)}
                        onFocus={() => setOpen(true)}
                        placeholder={resolvedPlaceholder}
                        className={cn(
                            'w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                            isCircuitOpen && 'border-amber-400',
                            className
                        )}
                    />
                </Popover.Trigger>
                <Popover.Portal>
                    <Popover.Content
                        className="z-[60] w-[var(--radix-popover-trigger-width)] rounded-md border bg-popover p-0 shadow-md outline-none"
                        align="start"
                        sideOffset={4}
                    >
                        <Command shouldFilter={false} className="rounded-md">
                            <Command.List className="max-h-[300px] overflow-y-auto">
                                {isLoading && (
                                    <Command.Loading>
                                        <div className="flex items-center gap-2 px-4 py-3 text-sm text-muted-foreground">
                                            <Loader2 className="h-4 w-4 animate-spin" />
                                            <span>Searching {systemLabel}...</span>
                                        </div>
                                    </Command.Loading>
                                )}

                                {!isLoading &&
                                    inputValue.trim().length > 0 &&
                                    inputValue.trim().length < 3 && (
                                        <Command.Empty>
                                            <div className="px-4 py-3 text-sm text-muted-foreground">
                                                Type at least 3 characters
                                            </div>
                                        </Command.Empty>
                                    )}

                                {!isLoading &&
                                    inputValue.trim().length >= 3 &&
                                    results.length === 0 && (
                                        <Command.Empty>
                                            <div className="px-4 py-3 text-sm text-muted-foreground">
                                                No results found in {systemLabel}
                                            </div>
                                        </Command.Empty>
                                    )}

                                {results.map((result) => (
                                    <Command.Item
                                        key={`${result.system}-${result.code}`}
                                        value={result.code}
                                        onSelect={() => handleSelect(result)}
                                        className={cn(
                                            'flex flex-col gap-1 px-4 py-3 cursor-pointer',
                                            'hover:bg-accent hover:text-accent-foreground',
                                            'aria-selected:bg-accent aria-selected:text-accent-foreground',
                                            'border-b border-border last:border-b-0'
                                        )}
                                    >
                                        <div className="flex items-center justify-between w-full">
                                            <span className="font-medium text-sm">
                                                {result.display}
                                            </span>
                                            <span className="text-xs text-muted-foreground ml-2">
                                                {result.code}
                                            </span>
                                        </div>
                                        {result.semantic_type && (
                                            <div className="text-xs text-muted-foreground">
                                                {result.semantic_type}
                                            </div>
                                        )}
                                    </Command.Item>
                                ))}
                            </Command.List>
                        </Command>
                    </Popover.Content>
                </Popover.Portal>
            </Popover.Root>

            {validationHint && <p className="mt-1 text-xs text-amber-600">{validationHint}</p>}
        </div>
    );
}
