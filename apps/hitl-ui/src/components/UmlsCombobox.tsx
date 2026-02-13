import * as Popover from '@radix-ui/react-popover';
import { Command } from 'cmdk';
import { Loader2 } from 'lucide-react';
import { useState } from 'react';

import { type UmlsSearchResult, useUmlsSearch } from '../hooks/useUmlsSearch';
import { cn } from '../lib/utils';

interface UmlsComboboxProps {
    value: string;
    onSelect: (result: UmlsSearchResult) => void;
    onChange: (value: string) => void;
    placeholder?: string;
    className?: string;
}

export function UmlsCombobox({
    value,
    onSelect,
    onChange,
    placeholder = 'Search UMLS concepts...',
    className,
}: UmlsComboboxProps) {
    const [open, setOpen] = useState(false);
    const [inputValue, setInputValue] = useState(value);

    const { results, isLoading } = useUmlsSearch(inputValue);

    // Determine if popover should be open
    const shouldShowPopover =
        inputValue.trim().length > 0 &&
        (results.length > 0 || isLoading || inputValue.trim().length >= 3);

    function handleInputChange(newValue: string) {
        setInputValue(newValue);
        onChange(newValue);
        setOpen(true);
    }

    function handleSelect(result: UmlsSearchResult) {
        setInputValue(result.preferred_term);
        onSelect(result);
        setOpen(false);
    }

    return (
        <Popover.Root open={open && shouldShowPopover} onOpenChange={setOpen}>
            <Popover.Trigger asChild>
                <input
                    type="text"
                    value={inputValue}
                    onChange={(e) => handleInputChange(e.target.value)}
                    onFocus={() => setOpen(true)}
                    placeholder={placeholder}
                    className={cn(
                        'w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        className
                    )}
                />
            </Popover.Trigger>
            <Popover.Portal>
                <Popover.Content
                    className="z-50 w-[var(--radix-popover-trigger-width)] rounded-md border bg-popover p-0 shadow-md outline-none"
                    align="start"
                    sideOffset={4}
                >
                    <Command shouldFilter={false} className="rounded-md">
                        <Command.List className="max-h-[300px] overflow-y-auto">
                            {isLoading && (
                                <Command.Loading>
                                    <div className="flex items-center gap-2 px-4 py-3 text-sm text-muted-foreground">
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                        <span>Searching UMLS...</span>
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
                                            No concepts found
                                        </div>
                                    </Command.Empty>
                                )}

                            {results.map((result) => (
                                <Command.Item
                                    key={result.cui}
                                    value={result.cui}
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
                                            {result.preferred_term}
                                        </span>
                                        <span className="text-xs text-muted-foreground ml-2">
                                            {result.cui}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                        <span>{result.semantic_type}</span>
                                        {result.snomed_code && (
                                            <>
                                                <span>•</span>
                                                <span>SNOMED: {result.snomed_code}</span>
                                            </>
                                        )}
                                    </div>
                                </Command.Item>
                            ))}
                        </Command.List>
                    </Command>
                </Popover.Content>
            </Popover.Portal>
        </Popover.Root>
    );
}
