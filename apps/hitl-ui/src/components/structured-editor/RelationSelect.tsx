// Radix UI Select wrapper for relation/operator dropdown

import * as Select from '@radix-ui/react-select';
import { ChevronDown } from 'lucide-react';

import { cn } from '../../lib/utils';
import { RELATIONS } from './constants';
import type { RelationOperator } from './types';

interface RelationSelectProps {
    value: RelationOperator | '';
    onChange: (value: RelationOperator) => void;
    disabled?: boolean;
}

export function RelationSelect({ value, onChange, disabled }: RelationSelectProps) {
    const selectedRelation = RELATIONS.find((r) => r.operator === value);
    const displayLabel = selectedRelation?.label ?? 'Select relation...';

    // Group relations by display category
    const comparisonRelations = RELATIONS.filter((r) =>
        ['=', '!=', '>', '>=', '<', '<='].includes(r.operator)
    );
    const rangeRelations = RELATIONS.filter((r) => r.operator === 'within');
    const temporalRelations = RELATIONS.filter((r) => r.operator === 'not_in_last');
    const textMatchRelations = RELATIONS.filter((r) =>
        ['contains', 'not_contains'].includes(r.operator)
    );

    return (
        <Select.Root
            value={value}
            onValueChange={(newValue) => onChange(newValue as RelationOperator)}
            disabled={disabled}
        >
            <Select.Trigger
                className={cn(
                    'w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    'flex items-center justify-between',
                    'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
            >
                <Select.Value>{displayLabel}</Select.Value>
                <Select.Icon>
                    <ChevronDown className="h-4 w-4 opacity-50" />
                </Select.Icon>
            </Select.Trigger>

            <Select.Portal>
                <Select.Content
                    className="overflow-hidden bg-popover rounded-md border shadow-md z-50"
                    position="popper"
                    sideOffset={4}
                >
                    <Select.Viewport className="p-1">
                        {/* Comparison group */}
                        <Select.Group>
                            <Select.Label className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                                Comparison
                            </Select.Label>
                            {comparisonRelations.map((relation) => (
                                <Select.Item
                                    key={relation.operator}
                                    value={relation.operator}
                                    className={cn(
                                        'relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none',
                                        'focus:bg-accent focus:text-accent-foreground',
                                        'data-[disabled]:pointer-events-none data-[disabled]:opacity-50'
                                    )}
                                >
                                    <Select.ItemText>{relation.label}</Select.ItemText>
                                </Select.Item>
                            ))}
                        </Select.Group>

                        {/* Range group */}
                        <Select.Group>
                            <Select.Label className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                                Range
                            </Select.Label>
                            {rangeRelations.map((relation) => (
                                <Select.Item
                                    key={relation.operator}
                                    value={relation.operator}
                                    className={cn(
                                        'relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none',
                                        'focus:bg-accent focus:text-accent-foreground',
                                        'data-[disabled]:pointer-events-none data-[disabled]:opacity-50'
                                    )}
                                >
                                    <Select.ItemText>{relation.label}</Select.ItemText>
                                </Select.Item>
                            ))}
                        </Select.Group>

                        {/* Temporal group */}
                        <Select.Group>
                            <Select.Label className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                                Temporal
                            </Select.Label>
                            {temporalRelations.map((relation) => (
                                <Select.Item
                                    key={relation.operator}
                                    value={relation.operator}
                                    className={cn(
                                        'relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none',
                                        'focus:bg-accent focus:text-accent-foreground',
                                        'data-[disabled]:pointer-events-none data-[disabled]:opacity-50'
                                    )}
                                >
                                    <Select.ItemText>{relation.label}</Select.ItemText>
                                </Select.Item>
                            ))}
                        </Select.Group>

                        {/* Text Match group */}
                        <Select.Group>
                            <Select.Label className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                                Text Match
                            </Select.Label>
                            {textMatchRelations.map((relation) => (
                                <Select.Item
                                    key={relation.operator}
                                    value={relation.operator}
                                    className={cn(
                                        'relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none',
                                        'focus:bg-accent focus:text-accent-foreground',
                                        'data-[disabled]:pointer-events-none data-[disabled]:opacity-50'
                                    )}
                                >
                                    <Select.ItemText>{relation.label}</Select.ItemText>
                                </Select.Item>
                            ))}
                        </Select.Group>
                    </Select.Viewport>
                </Select.Content>
            </Select.Portal>
        </Select.Root>
    );
}
