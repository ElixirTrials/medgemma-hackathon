import * as Dialog from "@radix-ui/react-dialog";
import { Clock, Hash, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import type { Criterion, ReviewActionRequest } from "../hooks/useReviews";
import {
	ConfidenceBadge,
	CriteriaTypeBadge,
	CriterionReviewStatusBadge,
	buildInitialValues,
	extractThresholdsList,
	formatNumericThreshold,
	formatTemporalConstraint,
} from "./CriterionCard";
import FieldMappingBadges from "./FieldMappingBadges";
import { TerminologyBadge } from "./TerminologyBadge";
import TextBoundaryAdjuster from "./TextBoundaryAdjuster";
import { StructuredFieldEditor } from "./structured-editor/StructuredFieldEditor";
import type { StructuredFieldFormValues } from "./structured-editor/types";
import { Button } from "./ui/Button";

interface CriterionModifyDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	criterion: Criterion;
	onAction: (action: ReviewActionRequest) => void;
	isSubmitting: boolean;
	pdfUrl?: string;
}

export default function CriterionModifyDialog({
	open,
	onOpenChange,
	criterion,
	onAction,
	isSubmitting,
	pdfUrl,
}: CriterionModifyDialogProps) {
	const [modifiedText, setModifiedText] = useState(criterion.text);
	const [structuredValues, setStructuredValues] =
		useState<StructuredFieldFormValues | null>(null);

	// Reset state when dialog closes
	useEffect(() => {
		if (!open) {
			setModifiedText(criterion.text);
			setStructuredValues(null);
		}
	}, [open, criterion.text]);

	const handleTextBoundaryChange = useCallback((newText: string) => {
		setModifiedText(newText);
	}, []);

	function handleStructuredSave(values: StructuredFieldFormValues) {
		setStructuredValues(values);
	}

	function handleSave() {
		const action: ReviewActionRequest = {
			action: "modify",
			reviewer_id: "current-user",
		};

		// Include modified text if changed
		if (modifiedText !== criterion.text) {
			action.modified_text = modifiedText;
		}

		// Include structured field changes if any
		if (structuredValues) {
			action.modified_structured_fields = {
				field_mappings: structuredValues.mappings as Array<{
					entity: string;
					entity_code?: string;
					entity_system?: string;
					relation: string;
					value: unknown;
				}>,
			};
		}

		onAction(action);
		onOpenChange(false);
	}

	return (
		<Dialog.Root open={open} onOpenChange={onOpenChange}>
			<Dialog.Portal>
				<Dialog.Overlay className="fixed inset-0 bg-black/50 z-50" />
				<Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white dark:bg-card rounded-lg p-6 max-w-2xl w-full z-50 shadow-lg max-h-[85vh] overflow-y-auto">
					{/* Title bar */}
					<Dialog.Title className="text-base font-semibold mb-1">
						Modify Criterion
					</Dialog.Title>
					<div className="flex flex-wrap items-center gap-2 mb-4">
						<CriteriaTypeBadge type={criterion.criteria_type} />
						{criterion.category && (
							<span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-700">
								{criterion.category}
							</span>
						)}
						<ConfidenceBadge confidence={criterion.confidence} />
						<CriterionReviewStatusBadge status={criterion.review_status} />
					</div>

					{/* System Selected panel */}
					<div className="bg-muted/30 border rounded-lg p-4 mb-4">
						<h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
							System Selected
						</h3>

						{/* Field mappings (read-only) */}
						<FieldMappingBadges criterion={criterion} />

						{/* Temporal constraint */}
						{criterion.temporal_constraint &&
							formatTemporalConstraint(criterion.temporal_constraint) && (
								<div className="mb-2 flex items-center gap-1.5">
									<Clock className="h-3.5 w-3.5 text-indigo-600" />
									<span className="inline-flex items-center rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-medium text-indigo-800">
										{formatTemporalConstraint(criterion.temporal_constraint)}
									</span>
								</div>
							)}

						{/* Numeric thresholds */}
						{extractThresholdsList(criterion.numeric_thresholds).length > 0 && (
							<div className="mb-2 flex flex-wrap items-center gap-1.5">
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

						{/* Entities with terminology badges */}
						{criterion.entities && criterion.entities.length > 0 && (
							<div className="mt-2">
								<p className="text-xs text-muted-foreground mb-1">Entities:</p>
								<div className="flex flex-wrap gap-1.5">
									{criterion.entities.map((entity) => (
										<span
											key={entity.id}
											className="inline-flex items-center gap-1"
										>
											<span className="text-xs font-medium">{entity.text}</span>
											{entity.snomed_code && (
												<TerminologyBadge
													system="snomed"
													code={entity.snomed_code}
												/>
											)}
											{entity.umls_cui && (
												<TerminologyBadge
													system="umls"
													code={entity.umls_cui}
												/>
											)}
										</span>
									))}
								</div>
							</div>
						)}
					</div>

					{/* Text Boundary Adjuster */}
					{pdfUrl && criterion.page_number != null && (
						<div className="mb-4">
							<h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
								Adjust Text Boundary
							</h3>
							<TextBoundaryAdjuster
								criterionText={criterion.text}
								pageNumber={criterion.page_number}
								pdfUrl={pdfUrl}
								onChange={handleTextBoundaryChange}
							/>
						</div>
					)}

					{/* Structured Fields section */}
					<div className="mb-4">
						<h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
							Structured Fields
						</h3>
						<StructuredFieldEditor
							criterionId={criterion.id}
							initialValues={buildInitialValues(criterion)}
							onSave={handleStructuredSave}
							onCancel={() => {
								/* no-op in dialog context, cancel handled by dialog */
							}}
							isSubmitting={isSubmitting}
						/>
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
