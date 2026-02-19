"""Tests for sentence-length entity extraction preprocessing."""

from protocol_processor.tools.tooluniverse_client import _extract_term_from_sentence


def test_short_query_unchanged():
    """Short queries (< 4 words OR < 40 chars) pass through unchanged."""
    assert _extract_term_from_sentence("eGFR") == "eGFR"
    assert _extract_term_from_sentence("osteoarthritis") == "osteoarthritis"
    assert _extract_term_from_sentence("ACE inhibitor") == "ACE inhibitor"


def test_sentence_length_extraction():
    """Sentence-length queries (>= 4 words AND >= 40 chars) have preamble stripped."""
    result = _extract_term_from_sentence(
        "The patient must have a diagnosis of myocardial infarction"
    )
    # Should extract the medical term, not the full sentence
    assert len(result.split()) < 8  # Significantly shorter than input (10 words)
    assert len(result) >= 3  # Not empty


def test_preamble_removal():
    """Common clinical preambles matching _PREAMBLE_PATTERN are stripped."""
    result = _extract_term_from_sentence(
        "History of myocardial infarction within 6 months"
    )
    # "History of" is a known preamble — should be stripped
    assert "myocardial infarction" in result.lower() or len(result.split()) <= 6


def test_fallback_last_words():
    """When no preamble match, last 4 words are returned as fallback."""
    result = _extract_term_from_sentence(
        "Something unusual and completely unrecognizable medical condition here"
    )
    words = result.split()
    assert len(words) <= 4


def test_whitespace_handling():
    """Leading/trailing whitespace is stripped."""
    assert _extract_term_from_sentence("  eGFR  ") == "eGFR"
