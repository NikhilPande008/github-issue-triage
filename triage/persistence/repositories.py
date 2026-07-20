from typing import Generic, TypeVar

from sqlalchemy import select
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


class HypothesisRepository(Repository[Hypothesis]):
    model = Hypothesis


class ArtifactRepository(Repository[Artifact]):
    model = Artifact


class LLMCallRepository(Repository[LLMCall]):
    model = LLMCall
