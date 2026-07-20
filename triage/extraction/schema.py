from pydantic import ValidationError

from triage.domain.models import IssueExtraction


class ExtractionValidationError(ValueError):
    pass


def validate_extraction_json(content: str) -> IssueExtraction:
    """Validate an unmodified model response against the agreed contract."""
    try:
        return IssueExtraction.model_validate_json(content)
    except ValidationError as error:
        raise ExtractionValidationError(str(error)) from error
