import {
	CheckCircle,
	Clock,
	Hash,
	Loader2,
	Pencil,
	Wand2,
	XCircle,
} from "lucide-react";
import { useState } from "react";

import type { Criterion, ReviewActionRequest } from "../hooks/useReviews";
import { cn } from "../lib/utils";
import { CriterionAuditHistory } from "./CriterionAuditHistory";
import CriterionModifyDialog from "./CriterionModifyDialog";
import { CriterionRerunPanel } from "./CriterionRerunPanel";
import FieldMappingBadges from "./FieldMappingBadges";
import RejectDialog from "./RejectDialog";
import { DEFAULT_FIELD_VALUES } from "./structured-editor/constants";
import type {
	FieldMapping,
	FieldValue,
	RelationOperator,
	StructuredFieldFormValues,
	TemporalUnit,
} from "./structured-editor/types";
import { Button } from "./ui/Button";

interface CriterionCardProps {
	criterion: Criterion;
	onAction: (criterionId: string, action: ReviewActionRequest) => void;
	isSubmitting: boolean;
	onCriterionClick?: (criterion: Criterion) => void;
	isActive?: boolean;
	pdfUrl?: string;
}

export function ConfidenceBadge({ confidence }: { confidence: number }) {
	const percentage = Math.round(confidence * 100);

	let label: string;
	let colorClass: string;

	if (confidence >= 0.85) {
		label = "High";
		colorClass = "bg-green-100 text-green-800";
	} else if (confidence >= 0.7) {
		label = "Medium";
		colorClass = "bg-yellow-100 text-yellow-800";
	} else {
		label = "Low";
		colorClass = "bg-red-100 text-red-800";
	}

	return (
		<span
			className={cn(
				"inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
				colorClass,
			)}
		>
			{label} ({percentage}%)
		</span>
	);
}

export function CriterionReviewStatusBadge({
	status,
}: { status: string | null }) {
	const statusConfig: Record<string, { label: string; colorClass: string }> = {
		approved: { label: "Approved", colorClass: "bg-green-100 text-green-800" },
		rejected: { label: "Rejected", colorClass: "bg-red-100 text-red-800" },
		modified: { label: "Modified", colorClass: "bg-blue-100 text-blue-800" },
	};

	const config = status ? statusConfig[status] : null;
	const label = config?.label ?? "Pending";
	const colorClass = config?.colorClass ?? "bg-gray-100 text-gray-800";

	return (
		<span
			className={cn(
				"inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
				colorClass,
			)}
		>
			{label}
		</span>
	);
}

export function CriteriaTypeBadge({ type }: { type: string }) {
	const colorClass =
		type === "inclusion"
			? "bg-blue-100 text-blue-800"
			: "bg-orange-100 text-orange-800";

	return (
		<span
			className={cn(
				"inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
				colorClass,
			)}
		>
			{type}
		</span>
	);
}

export function formatTemporalConstraint(tc: Record<string, unknown>): string {
	const duration = "duration" in tc ? (tc.duration as string) : null;
	const relation = "relation" in tc ? (tc.relation as string) : null;
	const referencePoint =
		"reference_point" in tc ? (tc.reference_point as string) : null;

	if (!duration) return "";

	const relationMap: Record<string, string> = {
		within: "Within",
		before: "Before",
		after: "After",
		at_least: "At least",
	};

	const relationText = relation ? relationMap[relation] || relation : "";
	const parts = [relationText, duration];
	if (referencePoint) parts.push("of", referencePoint);

	return parts.filter(Boolean).join(" ");
}

export function formatNumericThreshold(
	threshold: Record<string, unknown>,
): string {
	const value = "value" in threshold ? threshold.value : null;
	const unit = "unit" in threshold ? (threshold.unit as string) : "";
	const comparator =
		"comparator" in threshold ? (threshold.comparator as string) : "";
	const upperValue = "upper_value" in threshold ? threshold.upper_value : null;

	if (value === null) return "";

	if (comparator === "range" && upperValue !== null) {
		return `${value}-${upperValue} ${unit}`.trim();
	}

	return `${comparator}${value} ${unit}`.trim();
}

export function extractThresholdsList(
	nt: Record<string, unknown> | null,
): Array<Record<string, unknown>> {
	if (!nt) return [];

	// Shape 1: {"thresholds": [...]} wrapper object
	if ("thresholds" in nt && Array.isArray(nt.thresholds)) {
		return nt.thresholds as Array<Record<string, unknown>>;
	}

	// Shape 2: raw array stored directly
	if (Array.isArray(nt)) {
		return nt as Array<Record<string, unknown>>;
	}

	// Shape 3: single threshold object without wrapper
	if ("value" in nt && "comparator" in nt) {
		return [nt];
	}

	return [];
}

/** Map extraction comparator strings to RelationOperator. */
function mapComparator(comparator: string): RelationOperator | "" {
	const map: Record<string, RelationOperator> = {
		">=": ">=",
		"<=": "<=",
		">": ">",
		"<": "<",
		"==": "=",
		"=": "=",
		range: "within",
	};
	return map[comparator] ?? "";
}

/** Parse a duration string like "6 months" into {value, unit}. */
function parseDuration(duration: string): {
	value: string;
	unit: TemporalUnit;
} {
	const match = duration.match(/^(\d+)\s*(days?|weeks?|months?|years?)$/i);
	if (match) {
		const raw = match[2].toLowerCase().replace(/s$/, "");
		const unitMap: Record<string, TemporalUnit> = {
			day: "days",
			week: "weeks",
			month: "months",
			year: "years",
		};
		return { value: match[1], unit: unitMap[raw] ?? "days" };
	}
	return { value: duration, unit: "days" };
}

/**
 * Build initial form values for the structured editor from a criterion's
 * AI-extracted data (numeric_thresholds, temporal_constraint, conditions).
 */
export function buildInitialValues(
	criterion: Criterion,
): StructuredFieldFormValues {
	// Priority 1: existing field_mappings from a previous structured edit
	const cond = criterion.conditions as Record<string, unknown> | null;
	if (cond && "field_mappings" in cond && Array.isArray(cond.field_mappings)) {
		const fms = cond.field_mappings as Array<Record<string, unknown>>;
		const mappings: FieldMapping[] = fms.map((fm) => {
			const rel = (fm.relation as string) ?? "";
			const rawVal = fm.value as Record<string, unknown> | undefined;
			let value: FieldValue = { type: "standard", value: "", unit: "" };
			if (rawVal && rawVal.type === "range") {
				value = {
					type: "range",
					min: String(rawVal.min ?? ""),
					max: String(rawVal.max ?? ""),
					unit: String(rawVal.unit ?? ""),
				};
			} else if (rawVal && rawVal.type === "temporal") {
				value = {
					type: "temporal",
					duration: String(rawVal.duration ?? ""),
					unit: (rawVal.unit as TemporalUnit) ?? "days",
				};
			} else if (rawVal && rawVal.type === "standard") {
				value = {
					type: "standard",
					value: String(rawVal.value ?? ""),
					unit: String(rawVal.unit ?? ""),
				};
			}
			return {
				entity: String(fm.entity ?? ""),
				entity_code: fm.entity_code ? String(fm.entity_code) : undefined,
				entity_system: fm.entity_system ? String(fm.entity_system) : undefined,
				relation: (rel as RelationOperator) || "",
				value,
			};
		});
		if (mappings.length > 0) return { mappings };
	}

	// Priority 2: infer from AI-extracted data (entities + thresholds + temporal)
	const mappings: FieldMapping[] = [];

	const entities = criterion.entities ?? [];
	const thresholds = extractThresholdsList(criterion.numeric_thresholds);

	const entityLabel = (e: { preferred_term: string | null; text: string }) =>
		e.preferred_term || e.text;

	const measurableEntities = entities.filter(
		(e) =>
			e.entity_type === "Lab_Value" ||
			e.entity_type === "Biomarker" ||
			e.entity_type === "Demographic",
	);

	for (let i = 0; i < thresholds.length; i++) {
		const t = thresholds[i];
		const comparator = (t.comparator as string) ?? "";
		const val = t.value as number | null;
		const unit = (t.unit as string) ?? "";
		const upperVal = t.upper_value as number | null;

		if (val === null || val === undefined) continue;

		const matchedEntity = measurableEntities[i];
		const entity = matchedEntity ? entityLabel(matchedEntity) : "";
		const entityCode =
			matchedEntity?.snomed_code ?? matchedEntity?.umls_cui ?? undefined;
		const entitySystem = matchedEntity?.snomed_code
			? "snomed"
			: matchedEntity?.umls_cui
				? "umls"
				: undefined;

		if (comparator === "range" && upperVal != null) {
			mappings.push({
				entity,
				entity_code: entityCode,
				entity_system: entitySystem,
				relation: "within" as RelationOperator,
				value: { type: "range", min: String(val), max: String(upperVal), unit },
			});
		} else {
			const relation = mapComparator(comparator);
			mappings.push({
				entity,
				entity_code: entityCode,
				entity_system: entitySystem,
				relation,
				value: { type: "standard", value: String(val), unit },
			});
		}
	}

	const unmatchedEntities = entities.filter(
		(e) =>
			e.entity_type === "Condition" ||
			e.entity_type === "Medication" ||
			e.entity_type === "Procedure",
	);
	for (const e of unmatchedEntities) {
		const code = e.snomed_code ?? e.umls_cui ?? undefined;
		const system = e.snomed_code ? "snomed" : e.umls_cui ? "umls" : undefined;
		mappings.push({
			entity: entityLabel(e),
			entity_code: code,
			entity_system: system,
			relation: "",
			value: { type: "standard", value: "", unit: "" },
		});
	}

	if (criterion.temporal_constraint) {
		const tc = criterion.temporal_constraint;
		const duration = tc.duration as string | undefined;
		const referencePoint = tc.reference_point as string | undefined;

		if (duration) {
			const parsed = parseDuration(duration);
			mappings.push({
				entity: referencePoint ?? "",
				relation: "not_in_last" as RelationOperator,
				value: { type: "temporal", duration: parsed.value, unit: parsed.unit },
			});
		}
	}

	if (mappings.length === 0) return DEFAULT_FIELD_VALUES;
	return { mappings };
}

export default function CriterionCard({
	criterion,
	onAction,
	isSubmitting,
	onCriterionClick,
	isActive,
	pdfUrl,
}: CriterionCardProps) {
	const [modifyDialogOpen, setModifyDialogOpen] = useState(false);
	const [rejectDialogOpen, setRejectDialogOpen] = useState(false);

	function handleApprove() {
		onAction(criterion.id, {
			action: "approve",
			reviewer_id: "current-user",
		});
	}

	function handleReject() {
		setRejectDialogOpen(true);
	}

	function handleRejectConfirm(data: { reasons: string[]; comment?: string }) {
		onAction(criterion.id, {
			action: "reject",
			reviewer_id: "current-user",
			reject_reasons: data.reasons,
			comment: data.comment,
		});
	}

	return (
		<div
			className={cn(
				"rounded-lg border bg-card p-4 shadow-sm border-l-4",
				criterion.review_status === "approved" && "border-l-green-500",
				criterion.review_status === "rejected" && "border-l-red-500",
				criterion.review_status === "modified" && "border-l-blue-500",
				!criterion.review_status && "border-l-yellow-400",
			)}
		>
			{/* Header row */}
			<div className="flex flex-wrap items-center gap-2 mb-3">
				<CriteriaTypeBadge type={criterion.criteria_type} />
				{criterion.category && (
					<span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-700">
						{criterion.category}
					</span>
				)}
				<ConfidenceBadge confidence={criterion.confidence} />
				<CriterionReviewStatusBadge status={criterion.review_status} />
				{criterion.page_number != null && (
					<span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 ml-auto">
						p.{criterion.page_number}
					</span>
				)}
			</div>

			{/* Body - criterion text (read-only, clickable for PDF navigation) */}
			<p
				className={cn(
					"text-sm text-foreground mb-3",
					criterion.page_number != null &&
						"cursor-pointer hover:bg-accent/50 rounded px-1 -mx-1 transition-colors",
					isActive && "bg-accent/30 rounded px-1 -mx-1",
				)}
				onClick={() => {
					if (criterion.page_number != null && onCriterionClick) {
						onCriterionClick(criterion);
					}
				}}
				onKeyDown={(e) => {
					if (
						(e.key === "Enter" || e.key === " ") &&
						criterion.page_number != null &&
						onCriterionClick
					) {
						onCriterionClick(criterion);
					}
				}}
				role={criterion.page_number != null ? "button" : undefined}
				tabIndex={criterion.page_number != null ? 0 : undefined}
				title={
					criterion.page_number != null
						? `Click to view source (page ${criterion.page_number})`
						: undefined
				}
			>
				{criterion.text}
			</p>

			{/* Field mapping badges */}
			<FieldMappingBadges
				criterion={criterion}
				onEditClick={() => setModifyDialogOpen(true)}
			/>

			{/* Assertion status tag */}
			{criterion.assertion_status &&
				criterion.assertion_status !== "PRESENT" && (
					<div className="mb-3">
						<span className="inline-flex items-center rounded-full bg-purple-100 px-2.5 py-0.5 text-xs font-medium text-purple-800">
							{criterion.assertion_status}
						</span>
					</div>
				)}

			{/* Temporal constraint */}
			{criterion.temporal_constraint &&
				formatTemporalConstraint(criterion.temporal_constraint) && (
					<div className="mb-3 flex items-center gap-1.5">
						<Clock className="h-3.5 w-3.5 text-indigo-600" />
						<span className="inline-flex items-center rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-medium text-indigo-800">
							{formatTemporalConstraint(criterion.temporal_constraint)}
						</span>
					</div>
				)}

			{/* Numeric thresholds */}
			{extractThresholdsList(criterion.numeric_thresholds).length > 0 && (
				<div className="mb-3 flex flex-wrap items-center gap-1.5">
					<Hash className="h-3.5 w-3.5 text-teal-600" />
					{extractThresholdsList(criterion.numeric_thresholds).map(
						(threshold) => {
							const text = formatNumericThreshold(threshold);
							return text ? (
								<span
									key={text}
									className="inline-flex items-center rounded-full bg-teal-100 px-2.5 py-0.5 text-xs font-medium text-teal-800"
								>
									{text}
								</span>
							) : null;
						},
					)}
				</div>
			)}

			{/* Action buttons */}
			<div className="flex items-center gap-2 pt-2 border-t">
				<Button
					size="sm"
					variant="outline"
					className="text-green-700 border-green-300 hover:bg-green-50"
					onClick={handleApprove}
					disabled={isSubmitting || criterion.review_status === "approved"}
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
					disabled={isSubmitting || criterion.review_status === "rejected"}
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
					onClick={() => setModifyDialogOpen(true)}
					disabled={isSubmitting}
				>
					<Pencil className="h-4 w-4 mr-1" />
					Modify
				</Button>
				<CriterionRerunPanel
					criterionId={criterion.id}
					criterionText={criterion.text}
					currentExtraction={{
						criteria_type: criterion.criteria_type,
						category: criterion.category,
						temporal_constraint: criterion.temporal_constraint,
						conditions: criterion.conditions,
						numeric_thresholds: criterion.numeric_thresholds,
						text: criterion.text,
					}}
					onAccept={(revised) => {
						onAction(criterion.id, {
							action: "modify",
							reviewer_id: "current-user",
							modified_text: revised.text as string | undefined,
							modified_type: revised.criteria_type as string | undefined,
							modified_category: revised.category as string | undefined,
							modified_structured_fields: revised,
							comment: "AI-assisted correction with reviewer feedback",
						});
					}}
					trigger={
						<Button
							size="sm"
							variant="outline"
							className="text-purple-700 border-purple-300 hover:bg-purple-50"
							disabled={isSubmitting}
						>
							<Wand2 className="h-4 w-4 mr-1" />
							Correct with AI
						</Button>
					}
				/>
			</div>

			{/* Audit history section */}
			<CriterionAuditHistory criterionId={criterion.id} />

			<RejectDialog
				open={rejectDialogOpen}
				onOpenChange={setRejectDialogOpen}
				onConfirm={handleRejectConfirm}
			/>

			<CriterionModifyDialog
				open={modifyDialogOpen}
				onOpenChange={setModifyDialogOpen}
				criterion={criterion}
				onAction={(action) => onAction(criterion.id, action)}
				isSubmitting={isSubmitting}
				pdfUrl={pdfUrl}
			/>
		</div>
	);
}
