import type { Criterion } from "../hooks/useReviews";

interface FieldMappingBadgesProps {
	criterion: Criterion;
	onEditClick?: () => void;
}

function formatMappingValue(value: Record<string, unknown>): string {
	if (typeof value !== "object" || value === null) return "";
	if (value.type === "range")
		return `${value.min}–${value.max}${value.unit ? ` ${value.unit}` : ""}`;
	if (value.type === "temporal") return `${value.duration} ${value.unit}`;
	if (value.type === "standard")
		return `${value.value}${value.unit ? ` ${value.unit}` : ""}`;
	return "";
}

function renderValue(value: unknown): string {
	if (value === null || value === undefined) return "";
	if (typeof value === "string") return value;
	if (typeof value === "number") return String(value);
	if (typeof value === "object")
		return formatMappingValue(value as Record<string, unknown>);
	return "";
}

export default function FieldMappingBadges({
	criterion,
	onEditClick,
}: FieldMappingBadgesProps) {
	const cond = criterion.conditions as Record<string, unknown> | null;
	const fieldMappings =
		cond && "field_mappings" in cond && Array.isArray(cond.field_mappings)
			? (cond.field_mappings as Array<{
					entity: string;
					entity_code?: string;
					entity_system?: string;
					relation: string;
					value: unknown;
				}>)
			: null;

	if (!fieldMappings || fieldMappings.length === 0) return null;

	const badgeContent = (mapping: (typeof fieldMappings)[number]) => {
		const valueText = renderValue(mapping.value);
		return (
			<>
				<span className="font-semibold text-blue-900">
					{mapping.entity || "—"}
				</span>
				{mapping.entity_code && (
					<span className="inline-flex items-center rounded-full bg-green-50 border border-green-200 px-1.5 py-0 text-[10px] text-green-700">
						{mapping.entity_system?.toUpperCase()}: {mapping.entity_code}
					</span>
				)}
				{mapping.relation && (
					<span className="text-blue-600 font-mono text-xs">
						{mapping.relation}
					</span>
				)}
				{mapping.relation && valueText ? (
					<span className="text-blue-800">{valueText}</span>
				) : mapping.relation && !valueText ? (
					<span className="text-muted-foreground/50 italic text-xs">
						no value
					</span>
				) : null}
			</>
		);
	};

	return (
		<div className="mb-3">
			<div className="text-xs font-medium text-muted-foreground mb-2">
				Field Mappings
			</div>
			<div className="space-y-1">
				{fieldMappings.map((mapping, idx) => (
					// biome-ignore lint/suspicious/noArrayIndexKey: field_mappings have no stable unique id
					<div key={idx}>
						{idx > 0 && (
							<div className="flex items-center gap-2 py-1">
								<span className="text-xs font-semibold text-purple-600 bg-purple-50 px-2 py-0.5 rounded">
									AND
								</span>
								<div className="flex-1 border-t border-dashed border-muted" />
							</div>
						)}
						{onEditClick ? (
							<button
								onClick={onEditClick}
								className="w-full text-left flex items-center gap-2 rounded-md border bg-blue-50/50 border-blue-200 px-3 py-2 text-sm hover:bg-blue-100/50 transition-colors cursor-pointer"
								title="Click to edit field mappings"
								type="button"
							>
								{badgeContent(mapping)}
							</button>
						) : (
							<div className="w-full flex items-center gap-2 rounded-md border bg-blue-50/50 border-blue-200 px-3 py-2 text-sm">
								{badgeContent(mapping)}
							</div>
						)}
					</div>
				))}
			</div>
		</div>
	);
}
