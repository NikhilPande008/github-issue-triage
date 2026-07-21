"""Attributed OpenAI reservations and separate, unpriced Codex limits."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from triage.config.settings import Settings
from triage.domain.enums import BudgetStatus
from triage.llm.pricing import OPENAI_PROVIDER
from triage.persistence.models import Investigation, LLMCall


class BudgetExceeded(RuntimeError):
    pass


class BudgetService:
    def __init__(self, session, settings: Settings):
        self.session, self.settings = session, settings

    def reserve_openai(self, investigation_id: str, amount: Decimal | None = None) -> Decimal:
        amount = amount if amount is not None else self.settings.budget_openai_reservation_usd
        if amount <= 0:
            return Decimal("0")
        investigation = self.session.get(Investigation, investigation_id)
        if investigation is None:
            raise BudgetExceeded("Budget unavailable: investigation does not exist")
        if self.settings.budget_openai_per_investigation_usd is not None:
            used = Decimal(investigation.tracked_openai_cost_usd or 0) + Decimal(investigation.reserved_openai_cost_usd or 0)
            if used + amount > self.settings.budget_openai_per_investigation_usd:
                return self._exceed(investigation, "Per-investigation tracked OpenAI budget exceeded")
        now = datetime.now(timezone.utc)
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month = day.replace(day=1)
        for cap, start, label in ((self.settings.budget_openai_repository_daily_usd, day, "daily"), (self.settings.budget_openai_repository_monthly_usd, month, "monthly")):
            if cap is None:
                continue
            total = self._repository_openai(investigation.repository, start)
            reserved = self.session.scalar(select(func.coalesce(func.sum(Investigation.reserved_openai_cost_usd), 0)).where(Investigation.repository == investigation.repository)) or 0
            if Decimal(total) + Decimal(reserved) + amount > cap:
                return self._exceed(investigation, f"Repository {label} tracked OpenAI budget exceeded")
        investigation.reserved_openai_cost_usd = Decimal(investigation.reserved_openai_cost_usd or 0) + amount
        investigation.budget_status = BudgetStatus.RESERVED
        self.session.commit()
        return amount

    def reconcile_openai(self, investigation_id: str, reserved: Decimal, actual: Decimal | None) -> None:
        investigation = self.session.get(Investigation, investigation_id)
        if investigation is None:
            return
        investigation.reserved_openai_cost_usd = max(Decimal("0"), Decimal(investigation.reserved_openai_cost_usd or 0) - reserved)
        if actual is None:
            investigation.budget_status = BudgetStatus.UNBUDGETABLE
            investigation.budget_reason = "OpenAI model pricing is unavailable; no fictional USD cost was recorded"
        else:
            investigation.tracked_openai_cost_usd = Decimal(investigation.tracked_openai_cost_usd or 0) + actual
            investigation.budget_status = BudgetStatus.AVAILABLE
        self.session.commit()

    def before_codex(self, investigation_id: str) -> None:
        investigation = self.session.get(Investigation, investigation_id)
        if investigation is None:
            raise BudgetExceeded("Budget unavailable: investigation does not exist")
        cap = self.settings.budget_codex_per_investigation_seconds
        if cap and Decimal(investigation.codex_wall_seconds or 0) >= cap:
            self._exceed(investigation, "Per-investigation unpriced Codex wall-time cap exceeded")
        investigation.codex_wall_cap_seconds = cap
        self.session.commit()

    def record_codex(self, investigation_id: str, latency_ms: int) -> None:
        investigation = self.session.get(Investigation, investigation_id)
        if investigation is None:
            return
        seconds = Decimal(latency_ms) / Decimal(1000)
        cap = self.settings.budget_codex_per_investigation_seconds
        if cap and Decimal(investigation.codex_wall_seconds or 0) + seconds > cap:
            self._exceed(investigation, "Per-investigation unpriced Codex wall-time cap exceeded")
        investigation.codex_invocation_count += 1
        investigation.codex_wall_seconds = Decimal(investigation.codex_wall_seconds or 0) + seconds
        investigation.codex_wall_cap_seconds = cap
        self.session.commit()

    def _repository_openai(self, repository: str, start: datetime):
        return self.session.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0)).join(Investigation, LLMCall.investigation_id == Investigation.id).where(Investigation.repository == repository, LLMCall.provider == OPENAI_PROVIDER, LLMCall.created_at >= start)) or 0

    def _exceed(self, investigation: Investigation, reason: str):
        investigation.budget_status = BudgetStatus.EXCEEDED
        investigation.budget_reason = reason
        self.session.commit()
        raise BudgetExceeded(reason)
