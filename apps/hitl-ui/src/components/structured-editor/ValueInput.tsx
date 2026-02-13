// Adaptive value input component that switches based on relation category

import * as Select from '@radix-ui/react-select';
import { ChevronDown } from 'lucide-react';

import { cn } from '../../lib/utils';
import { TEMPORAL_UNITS } from './constants';
import type { FieldValue, RelationCategory } from './types';

interface ValueInputProps {
    category: RelationCategory;
    value: FieldValue;
    onChange: (value: FieldValue) => void;
    disabled?: boolean;
}

// Sub-component for standard single value + unit input
function StandardValueInput({
    value,
    onChange,
    disabled,
}: {
    value: FieldValue;
    onChange: (value: FieldValue) => void;
    disabled?: boolean;
}) {
    const standardValue = value.type === 'standard' ? value : { value: '', unit: '' };

    return (
        <div className="grid grid-cols-2 gap-3">
            <label className="block">
                <span className="block text-sm font-medium text-muted-foreground mb-1">Value</span>
                <input
                    type="text"
                    value={standardValue.value}
                    onChange={(e) =>
                        onChange({
                            type: 'standard',
                            value: e.target.value,
                            unit: standardValue.unit,
                        })
                    }
                    disabled={disabled}
                    className={cn(
                        'w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                />
            </label>
            <label className="block">
                <span className="block text-sm font-medium text-muted-foreground mb-1">Unit</span>
                <input
                    type="text"
                    placeholder="e.g., years, mg/dL"
                    value={standardValue.unit}
                    onChange={(e) =>
                        onChange({
                            type: 'standard',
                            value: standardValue.value,
                            unit: e.target.value,
                        })
                    }
                    disabled={disabled}
                    className={cn(
                        'w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                />
            </label>
        </div>
    );
}

// Sub-component for range min/max + unit input
function RangeValueInput({
    value,
    onChange,
    disabled,
}: {
    value: FieldValue;
    onChange: (value: FieldValue) => void;
    disabled?: boolean;
}) {
    const rangeValue = value.type === 'range' ? value : { min: '', max: '', unit: '' };

    return (
        <div className="grid grid-cols-3 gap-3">
            <label className="block">
                <span className="block text-sm font-medium text-muted-foreground mb-1">Min</span>
                <input
                    type="text"
                    value={rangeValue.min}
                    onChange={(e) =>
                        onChange({
                            type: 'range',
                            min: e.target.value,
                            max: rangeValue.max,
                            unit: rangeValue.unit,
                        })
                    }
                    disabled={disabled}
                    className={cn(
                        'w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                />
            </label>
            <label className="block">
                <span className="block text-sm font-medium text-muted-foreground mb-1">Max</span>
                <input
                    type="text"
                    value={rangeValue.max}
                    onChange={(e) =>
                        onChange({
                            type: 'range',
                            min: rangeValue.min,
                            max: e.target.value,
                            unit: rangeValue.unit,
                        })
                    }
                    disabled={disabled}
                    className={cn(
                        'w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                />
            </label>
            <label className="block">
                <span className="block text-sm font-medium text-muted-foreground mb-1">Unit</span>
                <input
                    type="text"
                    placeholder="e.g., mg/dL"
                    value={rangeValue.unit}
                    onChange={(e) =>
                        onChange({
                            type: 'range',
                            min: rangeValue.min,
                            max: rangeValue.max,
                            unit: e.target.value,
                        })
                    }
                    disabled={disabled}
                    className={cn(
                        'w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                />
            </label>
        </div>
    );
}

// Sub-component for temporal duration + unit dropdown
function TemporalValueInput({
    value,
    onChange,
    disabled,
}: {
    value: FieldValue;
    onChange: (value: FieldValue) => void;
    disabled?: boolean;
}) {
    const temporalValue =
        value.type === 'temporal' ? value : { duration: '', unit: 'days' as const };
    const selectedUnit = TEMPORAL_UNITS.find((u) => u.value === temporalValue.unit);

    return (
        <div className="grid grid-cols-2 gap-3">
            <label className="block">
                <span className="block text-sm font-medium text-muted-foreground mb-1">
                    Duration
                </span>
                <input
                    type="text"
                    value={temporalValue.duration}
                    onChange={(e) =>
                        onChange({
                            type: 'temporal',
                            duration: e.target.value,
                            unit: temporalValue.unit,
                        })
                    }
                    disabled={disabled}
                    className={cn(
                        'w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                        'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                />
            </label>
            <div>
                <span className="block text-sm font-medium text-muted-foreground mb-1">Unit</span>
                <Select.Root
                    value={temporalValue.unit}
                    onValueChange={(newUnit) =>
                        onChange({
                            type: 'temporal',
                            duration: temporalValue.duration,
                            unit: newUnit as 'days' | 'weeks' | 'months' | 'years',
                        })
                    }
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
                        <Select.Value>{selectedUnit?.label ?? 'Select unit'}</Select.Value>
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
                                {TEMPORAL_UNITS.map((unit) => (
                                    <Select.Item
                                        key={unit.value}
                                        value={unit.value}
                                        className={cn(
                                            'relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none',
                                            'focus:bg-accent focus:text-accent-foreground',
                                            'data-[disabled]:pointer-events-none data-[disabled]:opacity-50'
                                        )}
                                    >
                                        <Select.ItemText>{unit.label}</Select.ItemText>
                                    </Select.Item>
                                ))}
                            </Select.Viewport>
                        </Select.Content>
                    </Select.Portal>
                </Select.Root>
            </div>
        </div>
    );
}

// Main adaptive value input component
export function ValueInput({ category, value, onChange, disabled }: ValueInputProps) {
    switch (category) {
        case 'standard':
            return <StandardValueInput value={value} onChange={onChange} disabled={disabled} />;
        case 'range':
            return <RangeValueInput value={value} onChange={onChange} disabled={disabled} />;
        case 'temporal':
            return <TemporalValueInput value={value} onChange={onChange} disabled={disabled} />;
    }
}
