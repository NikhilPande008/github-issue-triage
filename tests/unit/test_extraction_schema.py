import pytest

from triage.extraction.schema import ExtractionValidationError, validate_extraction_json


VALID_EXTRACTION = """{
  "summary": "A request fails",
  "steps_to_reproduce": ["Call get"],
  "expected_behavior": "A response is returned",
  "actual_behavior": "An exception occurs",
  "environment": {},
  "affected_area": null,
  "repro_code": null,
  "missing_info": ["Python version"],
  "confidence": 0.8
}"""


def test_valid_extraction_json_is_parsed() -> None:
    extraction = validate_extraction_json(VALID_EXTRACTION)
    assert extraction.affected_area is None
    assert extraction.steps_to_reproduce == ["Call get"]


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"summary": "missing required fields"}',
        VALID_EXTRACTION[:-2] + ', "invented_field": "no"}',
    ],
)
def test_invalid_extraction_json_fails_without_repair(content: str) -> None:
    with pytest.raises(ExtractionValidationError):
        validate_extraction_json(content)
