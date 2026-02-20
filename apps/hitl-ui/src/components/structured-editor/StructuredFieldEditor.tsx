// Main structured field editor component with multiple entity/relation/value mappings

import { Loader2, Plus, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";

import type { TerminologySearchResult } from "../../hooks/useTerminologySearch";
import type { TerminologySystem } from "../TerminologyBadge";
import { TerminologyCombobox } from "../TerminologyCombobox";
import { Button } from "../ui/Button";
import { RelationSelect } from "./RelationSelect";
import { ValueInput } from "./ValueInput";
import {
	DEFAULT_FIELD_VALUES,
	DEFAULT_MAPPING,
	RELATION_CATEGORY_MAP,
	getDefaultValueForCategory,
} from "./constants";
import type {
	RelationOperator,
	StructuredFieldEditorProps,
	StructuredFieldFormValues,
} from "./types";

const TERMINOLOGY_SYSTEMS: Array<{ value: TerminologySystem; label: string }> =
	[
		{ value: "snomed", label: "SNOMED" },
		{ value: "loinc", label: "LOINC" },
		{ value: "rxnorm", label: "RxNorm" },
		{ value: "icd10", label: "ICD-10" },
		{ value: "hpo", label: "HPO" },
		{ value: "umls", label: "UMLS" },
	];

export function StructuredFieldEditor({
	criterionId,
	initialValues,
	onSave,
	onCancel,
	isSubmitting = false,
}: StructuredFieldEditorProps) {
	const { control, handleSubmit, watch, setValue } =
		useForm<StructuredFieldFormValues>({
			defaultValues: initialValues ?? DEFAULT_FIELD_VALUES,
		});

	const { fields, append, remove } = useFieldArray({
		control,
		name: "mappings",
	});

	// Per-mapping terminology system selector state
	const [systemSelections, setSystemSelections] = useState<
		Record<number, TerminologySystem>
	>(() => {
		const initial: Record<number, TerminologySystem> = {};
		const mappings = initialValues?.mappings ?? DEFAULT_FIELD_VALUES.mappings;
		for (let i = 0; i < mappings.length; i++) {
			initial[i] = (mappings[i].entity_system as TerminologySystem) || "snomed";
		}
		return initial;
	});

	const getSystem = (index: number): TerminologySystem =>
		systemSelections[index] ?? "snomed";

	const setSystem = (index: number, system: TerminologySystem) =>
		setSystemSelections((prev) => ({ ...prev, [index]: system }));

	// Watch all mappings for validation
	const allMappings = watch("mappings");

	// Track previous relations for each mapping to detect changes
	const previousRelationsRef = useRef<Array<RelationOperator | "">>([]);

	// State cleanup on relation change - prevent state leak between categories
	useEffect(() => {
		allMappings.forEach((mapping, index) => {
			const currentRelation = mapping.relation;
			const previousRelation = previousRelationsRef.current[index] ?? "";

			// Skip on initial mount (previousRelation is empty string initially)
			if (previousRelation === "" && currentRelation === "") {
				return;
			}

			// If relation actually changed
			if (previousRelation !== currentRelation && currentRelation !== "") {
				const newCategory =
					RELATION_CATEGORY_MAP[currentRelation as RelationOperator];
				const currentCategory = mapping.value.type;

				// If category changed, reset value to default for new category
				if (newCategory !== currentCategory) {
					setValue(
						`mappings.${index}.value`,
						getDefaultValueForCategory(newCategory),
					);
				}
			}

			// Update ref for next change detection
			previousRelationsRef.current[index] = currentRelation;
		});
	}, [allMappings, setValue]);

	// Check if we can add a new mapping (last mapping must have entity filled)
	const canAddMapping = () => {
		if (fields.length === 0) return true;
		const lastMapping = allMappings[allMappings.length - 1];
		return lastMapping && lastMapping.entity.trim() !== "";
	};

	const handleAddMapping = () => {
		if (canAddMapping()) {
			append(DEFAULT_MAPPING);
		}
	};

	return (
		<div className="space-y-4">
			{/* Mapping cards */}
			{fields.map((field, index) => {
				const mapping = allMappings[index];
				const relationCategory =
					mapping?.relation !== ""
						? RELATION_CATEGORY_MAP[mapping.relation as RelationOperator]
						: null;

				return (
					<div key={field.id} className="border rounded-lg p-3 mb-3 relative">
						{/* Mapping label and remove button */}
						<div className="flex items-center justify-between mb-3">
							<span className="text-sm font-medium text-muted-foreground">
								Mapping {index + 1}
							</span>
							<Button
								type="button"
								size="sm"
								variant="ghost"
								onClick={() => remove(index)}
								disabled={fields.length === 1 || isSubmitting}
								className="h-6 w-6 p-0"
							>
								<Trash2 className="h-4 w-4 text-red-600" />
							</Button>
						</div>

						{/* Entity field with terminology search */}
						<div className="mb-3">
							<label
								htmlFor={`entity-${criterionId}-${index}`}
								className="block text-sm font-medium text-muted-foreground mb-1"
							>
								Entity
							</label>
							<div className="flex gap-2">
								<select
									value={getSystem(index)}
									onChange={(e) =>
										setSystem(index, e.target.value as TerminologySystem)
									}
									disabled={isSubmitting}
									className="rounded-md border border-input bg-background px-2 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 disabled:cursor-not-allowed w-[100px] shrink-0"
								>
									{TERMINOLOGY_SYSTEMS.map((s) => (
										<option key={s.value} value={s.value}>
											{s.label}
										</option>
									))}
								</select>
								<Controller
									name={`mappings.${index}.entity`}
									control={control}
									render={({ field }) => (
										<div className="flex-1">
											<TerminologyCombobox
												system={getSystem(index)}
												value={field.value}
												onChange={(val) => {
													field.onChange(val);
													// Clear code/system when user types freely
													setValue(`mappings.${index}.entity_code`, undefined);
													setValue(
														`mappings.${index}.entity_system`,
														undefined,
													);
												}}
												onSelect={(result: TerminologySearchResult) => {
													field.onChange(result.display);
													setValue(
														`mappings.${index}.entity_code`,
														result.code,
													);
													setValue(
														`mappings.${index}.entity_system`,
														getSystem(index),
													);
												}}
												placeholder="Search terminology..."
											/>
										</div>
									)}
								/>
							</div>
							{mapping?.entity_code && (
								<div className="mt-1">
									<span className="inline-flex items-center rounded-full bg-green-50 border border-green-200 px-2 py-0.5 text-xs text-green-700">
										{mapping.entity_system?.toUpperCase()}:{" "}
										{mapping.entity_code}
									</span>
								</div>
							)}
						</div>

						{/* Relation field */}
						<div className="mb-3">
							<label
								htmlFor={`relation-${criterionId}-${index}`}
								className="block text-sm font-medium text-muted-foreground mb-1"
							>
								Relation
							</label>
							<Controller
								name={`mappings.${index}.relation`}
								control={control}
								render={({ field }) => (
									<RelationSelect
										value={field.value}
										onChange={field.onChange}
										disabled={isSubmitting}
									/>
								)}
							/>
						</div>

						{/* Value field - conditionally rendered based on relation category */}
						{relationCategory && (
							<div>
								<Controller
									name={`mappings.${index}.value`}
									control={control}
									render={({ field }) => (
										<ValueInput
											category={relationCategory}
											value={field.value}
											onChange={field.onChange}
											disabled={isSubmitting}
										/>
									)}
								/>
							</div>
						)}
					</div>
				);
			})}

			{/* Add Mapping button */}
			<div className="mb-3">
				<Button
					type="button"
					size="sm"
					variant="outline"
					onClick={handleAddMapping}
					disabled={!canAddMapping() || isSubmitting}
					className="w-full"
				>
					<Plus className="h-4 w-4 mr-1" />
					Add Mapping
				</Button>
				{!canAddMapping() && fields.length > 0 && (
					<p className="text-xs text-muted-foreground mt-1">
						Complete the current mapping before adding another
					</p>
				)}
			</div>

			{/* Action buttons */}
			<div className="flex items-center gap-2 pt-2">
				<Button
					size="sm"
					onClick={handleSubmit(onSave)}
					disabled={isSubmitting}
				>
					{isSubmitting ? (
						<Loader2 className="h-4 w-4 animate-spin mr-1" />
					) : null}
					Save
				</Button>
				<Button
					size="sm"
					variant="outline"
					onClick={onCancel}
					disabled={isSubmitting}
				>
					Cancel
				</Button>
			</div>
		</div>
	);
}

// Export as both default and named export for flexible importing
export default StructuredFieldEditor;
