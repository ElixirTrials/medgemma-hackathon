// TypeScript types for structured editor form

export type RelationOperator =
	| "="
	| "!="
	| ">"
	| ">="
	| "<"
	| "<="
	| "within"
	| "not_in_last"
	| "contains"
	| "not_contains";

export type RelationCategory = "standard" | "range" | "temporal";

export type TemporalUnit = "days" | "weeks" | "months" | "years";

export interface StandardValue {
	type: "standard";
	value: string;
	unit: string;
}

export interface RangeValue {
	type: "range";
	min: string;
	max: string;
	unit: string;
}

export interface TemporalValue {
	type: "temporal";
	duration: string;
	unit: TemporalUnit;
}

export type FieldValue = StandardValue | RangeValue | TemporalValue;

// Single field mapping with all possible fields
export interface FieldMapping {
	entity: string;
	entity_code?: string;
	entity_system?: string;
	relation: RelationOperator | "";
	value: FieldValue;
}

// Form values now contain an array of mappings
export interface StructuredFieldFormValues {
	mappings: FieldMapping[];
}

export interface StructuredFieldEditorProps {
	criterionId: string;
	initialValues?: Partial<StructuredFieldFormValues>;
	onSave: (values: StructuredFieldFormValues) => void;
	onCancel: () => void;
	isSubmitting?: boolean;
}
