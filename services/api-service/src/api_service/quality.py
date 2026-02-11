"""PDF quality analyzer for computing text extractability and encoding type.

Analyzes uploaded protocol PDFs to determine:
- Text extractability ratio (pages with extractable text / total pages)
- Page count
- Whether the document contains images (scanned content)
- Encoding type classification (text, scanned, mixed)
- Overall quality score as a weighted composite

Uses PyMuPDF (fitz) for PDF analysis without requiring external tools.
"""

from __future__ import annotations

import logging

import fitz
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class QualityResult(BaseModel):
    """Result of PDF quality analysis.

    Attributes:
        text_extractability: Ratio of pages with extractable text (0.0-1.0).
        page_count: Total number of pages in the PDF.
        has_images: Whether any pages contain embedded images.
        encoding_type: Classification -- "text", "scanned", or "mixed".
        overall_score: Weighted composite quality score (0.0-1.0).
        is_low_quality: True if overall_score < 0.5.
    """

    text_extractability: float
    page_count: int
    has_images: bool
    encoding_type: str
    overall_score: float
    is_low_quality: bool


def compute_quality_score(pdf_bytes: bytes) -> QualityResult:
    """Analyze PDF bytes and compute a quality score.

    Opens the PDF from raw bytes using PyMuPDF, examines each page
    for text content and images, and produces a composite quality
    score useful for determining extraction feasibility.

    Args:
        pdf_bytes: Raw PDF file content.

    Returns:
        QualityResult with all analysis fields populated.

    Raises:
        Exception: If the PDF cannot be opened or parsed.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    total_pages = len(doc)
    pages_with_text = 0
    pages_with_images = 0

    for page in doc:
        # Check for extractable text
        text = page.get_text("text").strip()
        if text:
            pages_with_text += 1

        # Check for embedded images
        images = page.get_images()
        if images:
            pages_with_images += 1

    doc.close()

    # Calculate metrics
    if total_pages == 0:
        return QualityResult(
            text_extractability=0.0,
            page_count=0,
            has_images=False,
            encoding_type="scanned",
            overall_score=0.0,
            is_low_quality=True,
        )

    text_extractability = pages_with_text / total_pages
    has_images = pages_with_images > 0

    # Determine encoding type
    if text_extractability > 0.8:
        encoding_type = "text"
    elif text_extractability < 0.2:
        encoding_type = "scanned"
    else:
        encoding_type = "mixed"

    # Calculate composite score
    # - 70% weight on text extractability (most important for extraction)
    # - 20% weight on page count (more pages = more content, capped at 100)
    # - 10% weight on encoding type bonus
    encoding_bonus = (
        1.0
        if encoding_type == "text"
        else 0.5 if encoding_type == "mixed" else 0.0
    )
    overall_score = (
        0.7 * text_extractability
        + 0.2 * min(1.0, total_pages / 100)
        + 0.1 * encoding_bonus
    )

    is_low_quality = overall_score < 0.5

    return QualityResult(
        text_extractability=text_extractability,
        page_count=total_pages,
        has_images=has_images,
        encoding_type=encoding_type,
        overall_score=overall_score,
        is_low_quality=is_low_quality,
    )


def quality_result_to_metadata(
    result: QualityResult,
) -> dict[str, str]:
    """Convert QualityResult to flat string dict for GCS custom metadata.

    GCS custom metadata values must be strings. This converts
    all fields to string representations.

    Args:
        result: QualityResult from compute_quality_score.

    Returns:
        Dict with string keys and string values for GCS metadata.
    """
    return {
        "quality_score": str(result.overall_score),
        "text_extractability": str(result.text_extractability),
        "page_count": str(result.page_count),
        "encoding_type": result.encoding_type,
        "has_images": str(result.has_images).lower(),
        "is_low_quality": str(result.is_low_quality).lower(),
    }
