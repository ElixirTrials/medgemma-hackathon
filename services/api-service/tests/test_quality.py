"""Unit tests for PDF quality scoring algorithm.

Tests compute_quality_score and quality_result_to_metadata using
minimal in-memory PDFs created with PyMuPDF (fitz).
"""

import pymupdf as fitz
import pytest

from api_service.quality import compute_quality_score, quality_result_to_metadata


def _make_text_pdf(num_pages: int = 3) -> bytes:
    """Create a minimal PDF with text on every page."""
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1} with extractable text content.")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_image_pdf(num_pages: int = 3) -> bytes:
    """Create a minimal PDF with only images (no extractable text).

    Uses a tiny 1x1 PNG to simulate a scanned document.
    """
    doc = fitz.open()
    # Create a small 2x2 pixel PNG in memory
    img_doc = fitz.open()
    img_page = img_doc.new_page(width=2, height=2)
    # Draw a filled rectangle as content
    shape = img_page.new_shape()
    shape.draw_rect(fitz.Rect(0, 0, 2, 2))
    shape.finish(fill=(0, 0, 0))
    shape.commit()
    pix = img_page.get_pixmap()
    img_bytes = pix.tobytes("png")
    img_doc.close()

    for _ in range(num_pages):
        page = doc.new_page()
        page.insert_image(fitz.Rect(72, 72, 200, 200), stream=img_bytes)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_mixed_pdf() -> bytes:
    """Create a PDF with both text and image-only pages (mixed encoding)."""
    doc = fitz.open()

    # Create image bytes
    img_doc = fitz.open()
    img_page = img_doc.new_page(width=2, height=2)
    shape = img_page.new_shape()
    shape.draw_rect(fitz.Rect(0, 0, 2, 2))
    shape.finish(fill=(0, 0, 0))
    shape.commit()
    pix = img_page.get_pixmap()
    img_bytes = pix.tobytes("png")
    img_doc.close()

    # 3 text pages + 7 image-only pages = 30% text extractability -> "mixed"
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"Text page {i + 1}")
    for _ in range(7):
        page = doc.new_page()
        page.insert_image(fitz.Rect(72, 72, 200, 200), stream=img_bytes)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_empty_pdf() -> bytes:
    """Create a minimal PDF that fitz will open with zero extractable pages.

    PyMuPDF cannot save a document with 0 pages, so we create a
    single blank page (no text, no images) and then delete it,
    yielding valid PDF bytes that open as having 0 pages.
    """
    doc = fitz.open()
    doc.new_page()
    doc.delete_page(0)
    # PyMuPDF still cannot save with 0 pages, so craft raw PDF bytes
    # that represent a valid but empty PDF structure.
    doc.close()

    # Minimal valid PDF with 0 pages
    # This is a well-formed PDF 1.4 with an empty Pages tree.
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
        b"xref\n0 3\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"trailer<</Size 3/Root 1 0 R>>\nstartxref\n108\n%%EOF"
    )


class TestComputeQualityScore:
    """Tests for compute_quality_score."""

    def test_text_pdf_high_extractability(self) -> None:
        result = compute_quality_score(_make_text_pdf(num_pages=3))
        assert result.text_extractability == 1.0
        assert result.encoding_type == "text"
        assert result.page_count == 3
        assert result.has_images is False
        assert result.is_low_quality is False
        assert result.overall_score > 0.7

    def test_scanned_pdf_low_extractability(self) -> None:
        result = compute_quality_score(_make_image_pdf(num_pages=3))
        assert result.text_extractability == 0.0
        assert result.encoding_type == "scanned"
        assert result.has_images is True
        assert result.is_low_quality is True
        assert result.overall_score < 0.5

    def test_mixed_pdf_medium_extractability(self) -> None:
        result = compute_quality_score(_make_mixed_pdf())
        assert 0.2 <= result.text_extractability <= 0.8
        assert result.encoding_type == "mixed"
        assert result.page_count == 10

    def test_empty_pdf_zero_score(self) -> None:
        result = compute_quality_score(_make_empty_pdf())
        assert result.page_count == 0
        assert result.overall_score == 0.0
        assert result.is_low_quality is True

    def test_large_page_count_caps_score_component(self) -> None:
        """Page-count component should cap at 1.0 (100 pages max contribution)."""
        result = compute_quality_score(_make_text_pdf(num_pages=150))
        # With 150 pages text: extractability=1.0, pages capped at 1.0
        # 0.7*1.0 + 0.2*1.0 + 0.1*1.0 = 1.0
        assert result.overall_score == pytest.approx(1.0, abs=0.01)


class TestQualityResultToMetadata:
    """Tests for quality_result_to_metadata."""

    def test_converts_to_string_dict(self) -> None:
        result = compute_quality_score(_make_text_pdf())
        metadata = quality_result_to_metadata(result)

        assert isinstance(metadata, dict)
        # All values must be strings (GCS metadata requirement)
        for key, val in metadata.items():
            assert isinstance(key, str)
            assert isinstance(val, str)

        assert "quality_score" in metadata
        assert "text_extractability" in metadata
        assert "page_count" in metadata
        assert "encoding_type" in metadata
        assert metadata["has_images"] in ("true", "false")
        assert metadata["is_low_quality"] in ("true", "false")
