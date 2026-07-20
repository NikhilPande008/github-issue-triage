from decimal import Decimal

from triage.llm.pricing import PRICE_BOOK_VERSION, calculate_cost


def test_known_model_cost_uses_versioned_input_cached_and_output_prices() -> None:
    assert PRICE_BOOK_VERSION == "2026-07-20"
    assert calculate_cost("gpt-5.6-luna", 100, 20, 10) == Decimal("0.000142")


def test_unknown_model_cost_is_unavailable() -> None:
    assert calculate_cost("unknown-model", 100, 0, 10) is None
