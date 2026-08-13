"""Every classification reports how it was reached.

This is the contract that fixes the observability bug: `main.py` incremented
`ai_categorization_count` unconditionally after `classify_document()`, so a run where
Ollama was unreachable — and every file was sorted by whether its name contained
"receipt" — reported healthy AI classification. The metric actively hid the failure.

There is no live Ollama in CI, so these test the seam rather than the model: given a
model response, a model failure, or no model at all, what does the classifier claim it
did.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import vision  # noqa: E402
from vision import (  # noqa: E402
    DEFAULT_CATEGORY,
    METHOD_HEURISTIC,
    METHOD_MOCK,
    METHOD_MODEL,
    _classification,
)


# ------------------------------------------------------------------- the stamp


def test_a_result_carries_the_method_that_produced_it():
    r = _classification("04_FINANCIAL/Tax_Records", "w2.pdf", METHOD_MODEL)
    assert r == {
        "category": "04_FINANCIAL/Tax_Records",
        "clean_filename": "w2.pdf",
        "method": METHOD_MODEL,
    }


@pytest.mark.parametrize(
    "bad", ["", None, "just some prose", "no-underscore/here", "04_FINANCIAL"]
)
def test_a_category_that_is_not_a_taxonomy_path_is_replaced(bad):
    # A model returning prose instead of a path would otherwise become a directory
    # name on the NAS.
    assert _classification(bad, "f.pdf", METHOD_MODEL)["category"] == DEFAULT_CATEGORY


def test_a_valid_category_survives():
    assert (
        _classification("02_TECHNICAL_HOMELAB/Docker_Stacks", "f.md", METHOD_MODEL)["category"]
        == "02_TECHNICAL_HOMELAB/Docker_Stacks"
    )


# -------------------------------------------------------------- the heuristic


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("2026_receipt.pdf", "04_FINANCIAL/Invoices_Receipts"),
        ("acme_invoice.pdf", "04_FINANCIAL/Invoices_Receipts"),
        ("w2_2025.pdf", "04_FINANCIAL/Tax_Records"),
        ("offer_letter.pdf", "01_PROFESSIONAL/Documentation"),
        ("something_random.pdf", DEFAULT_CATEGORY),
    ],
)
def test_the_heuristic_still_classifies_as_before(filename, expected):
    # Behaviour preserved through the refactor; only the reporting changed.
    classifier = vision.VisionClassifier.__new__(vision.VisionClassifier)
    result = classifier.fallback_heuristic(filename)
    assert result["category"] == expected
    assert result["clean_filename"] == filename


def test_the_heuristic_never_claims_to_be_the_model():
    classifier = vision.VisionClassifier.__new__(vision.VisionClassifier)
    assert classifier.fallback_heuristic("receipt.pdf")["method"] == METHOD_HEURISTIC


def test_mock_mode_is_distinguishable_from_a_model_failure():
    # Both fall back to filename matching, but "no API key configured" and "the model
    # was unreachable" call for different responses from whoever is on call.
    classifier = vision.VisionClassifier.__new__(vision.VisionClassifier)
    classifier.use_local_llm = False
    classifier.mock_mode = True
    assert classifier.classify_document("receipt.pdf")["method"] == METHOD_MOCK


# ------------------------------------------------------- model paths, mocked


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload


def _local_classifier():
    c = vision.VisionClassifier.__new__(vision.VisionClassifier)
    c.use_local_llm = True
    c.ollama_url = "http://ollama:11434"
    c.ollama_model = "gemma4:e2b"
    c.mock_mode = False
    c.schema_prompt = "classify this"
    return c


def test_a_successful_model_response_is_reported_as_the_model(tmp_path):
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    payload = {"response": '```json\n{"category": "04_FINANCIAL/Tax_Records", "clean_filename": "w2.pdf"}\n```'}
    with patch("httpx.post", return_value=_Resp(payload)):
        result = _local_classifier().classify_local_llm(str(img))
    assert result["method"] == METHOD_MODEL
    assert result["category"] == "04_FINANCIAL/Tax_Records"
    assert result["clean_filename"] == "w2.pdf"


def test_a_fenced_response_with_leading_whitespace_still_parses(tmp_path):
    # Delegating to llmkit means the fence handling is now shared with aadyon-assist,
    # where the local copy had drifted into checking startswith() against the raw
    # text — which any leading newline defeats.
    img = tmp_path / "photo.png"
    img.write_bytes(b"\x89PNG")
    payload = {"response": '\n\n  ```json\n{"category": "03_PERSONAL/Archives", "clean_filename": "x.png"}\n```'}
    with patch("httpx.post", return_value=_Resp(payload)):
        assert _local_classifier().classify_local_llm(str(img))["method"] == METHOD_MODEL


def test_an_http_error_falls_back_and_says_so(tmp_path):
    img = tmp_path / "receipt.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    with patch("httpx.post", return_value=_Resp({}, status=500)):
        result = _local_classifier().classify_local_llm(str(img))
    assert result["method"] == METHOD_HEURISTIC
    # It still classifies — the heuristic works — which is precisely why the failure
    # was invisible before.
    assert result["category"] == "04_FINANCIAL/Invoices_Receipts"


def test_an_unreachable_ollama_falls_back_and_says_so(tmp_path):
    img = tmp_path / "invoice.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    with patch("httpx.post", side_effect=OSError("connection refused")):
        assert _local_classifier().classify_local_llm(str(img))["method"] == METHOD_HEURISTIC


def test_an_unparseable_response_falls_back_and_says_so(tmp_path):
    img = tmp_path / "note.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    with patch("httpx.post", return_value=_Resp({"response": "I am not JSON"})):
        assert _local_classifier().classify_local_llm(str(img))["method"] == METHOD_HEURISTIC


def test_a_non_document_extension_uses_the_heuristic(tmp_path):
    f = tmp_path / "archive.zip"
    f.write_bytes(b"PK")
    assert _local_classifier().classify_local_llm(str(f))["method"] == METHOD_HEURISTIC


# ------------------------------------------------------------------ delegation


def test_pdf_extraction_returns_empty_rather_than_placeholder_text(tmp_path):
    # Callers here treat "" as "fall back". The other copy of this helper returned
    # "[PDF parsing failed: ...]", which a caller cannot distinguish from a document
    # that genuinely says that.
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"not a pdf")
    assert _local_classifier().extract_pdf_text(str(bad)) == ""


def test_clean_json_text_still_works_through_llmkit():
    classifier = vision.VisionClassifier.__new__(vision.VisionClassifier)
    assert classifier.clean_json_text('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert classifier.clean_json_text('  \n```\n{"a": 1}\n```  ') == '{"a": 1}'


# -------------------------------------------------------------------- metrics


def test_the_two_counters_are_distinct_metrics():
    # The whole point: a heuristic fallback must not increment the AI counter.
    import main

    assert main.AI_CATEGORIZATION_COUNTER is not main.HEURISTIC_CATEGORIZATION_COUNTER
    ai = main.AI_CATEGORIZATION_COUNTER._name
    heur = main.HEURISTIC_CATEGORIZATION_COUNTER._name
    assert ai != heur
