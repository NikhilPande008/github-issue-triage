from decimal import Decimal
from typing import Generic, TypeVar

from sqlalchemy import select
from triage.domain.enums import InvestigationStatus
from triage.llm.pricing import OPENAI_PROVIDER
from sqlalchemy.orm import Session

from triage.persistence.models import Artifact, Hypothesis, Investigation, LLMCall

ModelT = TypeVar("ModelT")


class Repository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: Session):
        self.session = session

    def create(self, item: ModelT) -> ModelT:
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def get(self, item_id: str) -> ModelT | None:
        return self.session.get(self.model, item_id)

    def list(self) -> list[ModelT]:
        return list(self.session.scalars(select(self.model)))

    def update(self, item: ModelT, **values: object) -> ModelT:
        for name, value in values.items():
            setattr(item, name, value)
        self.session.commit()
        self.session.refresh(item)
        return item

    def delete(self, item: ModelT) -> None:
        self.session.delete(item)
        self.session.commit()


class InvestigationRepository(Repository[Investigation]):
    model = Investigation

    def processed_issue_numbers(self, repository: str) -> set[int]:
        """Completed/failed runs are resumable batch work; interrupted runs may be retried."""
        statement = select(Investigation.issue_number).where(
            Investigation.repository == repository,
            Investigation.status.in_([InvestigationStatus.COMPLETED, InvestigationStatus.FAILED]),
        )
        return set(self.session.scalars(statement))


class HypothesisRepository(Repository[Hypothesis]):
    model = Hypothesis


class ArtifactRepository(Repository[Artifact]):
    model = Artifact


class LLMCallRepository(Repository[LLMCall]):
    model = LLMCall

    def tracked_cost_usd(self, investigation_id: str) -> float | None:
        """Return only fully priced, linked OpenAI API cost for terminal reporting."""
        costs = list(
            self.session.scalars(
                select(LLMCall.cost_usd).where(
                    LLMCall.investigation_id == investigation_id,
                    LLMCall.provider == OPENAI_PROVIDER,
                )
            )
        )
        if not costs or any(cost is None for cost in costs):
            return None
        return float(sum((Decimal(cost) for cost in costs), Decimal("0")))
