from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from triage.budget import BudgetExceeded, BudgetService
from triage.config.settings import Settings
from triage.persistence.database import Base, create_engine_from_url
from triage.persistence.models import Investigation


def test_openai_reservation_reconciles_and_releases_unused_amount(tmp_path) -> None:
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'budget.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(budget_openai_per_investigation_usd=Decimal("0.20"), budget_openai_reservation_usd=Decimal("0.10"))
    with factory() as session:
        investigation = Investigation(repository="owner/repo", issue_number=1)
        session.add(investigation); session.commit()
        budget = BudgetService(session, settings)
        reserved = budget.reserve_openai(investigation.id)
        assert investigation.reserved_openai_cost_usd == Decimal("0.10")
        budget.reconcile_openai(investigation.id, reserved, Decimal("0.025"))
        assert investigation.reserved_openai_cost_usd == 0
        assert investigation.tracked_openai_cost_usd == Decimal("0.025")


def test_investigation_cap_blocks_next_openai_or_codex_action(tmp_path) -> None:
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'budget.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(budget_openai_per_investigation_usd=Decimal("0.10"), budget_openai_reservation_usd=Decimal("0.10"), budget_codex_per_investigation_seconds=1)
    with factory() as session:
        investigation = Investigation(repository="owner/repo", issue_number=1, codex_wall_seconds=Decimal("1"))
        session.add(investigation); session.commit()
        budget = BudgetService(session, settings)
        budget.reserve_openai(investigation.id)
        with pytest.raises(BudgetExceeded):
            budget.reserve_openai(investigation.id)
        with pytest.raises(BudgetExceeded):
            budget.before_codex(investigation.id)
