from decimal import Decimal, ROUND_HALF_UP

PRICE_BOOK_VERSION = "2026-07-20"
OPENAI_PROVIDER = "openai"

# The application-supported API model tariff. Unknown models deliberately have
# no entry and therefore no locally calculated cost.
PRICE_BOOK: dict[str, dict[str, Decimal]] = {
    "gpt-5.6-luna": {
        "input_per_million": Decimal("1.00"),
        "cached_input_per_million": Decimal("0.10"),
        "output_per_million": Decimal("6.00"),
    }
}


def calculate_cost(
    model: str, input_tokens: int, cached_input_tokens: int, output_tokens: int
) -> Decimal | None:
    """Return a versioned local calculation, or None when the model is unknown."""
    if cached_input_tokens > input_tokens:
        raise ValueError("cached input tokens cannot exceed input tokens")
    prices = PRICE_BOOK.get(model)
    if prices is None:
        return None
    uncached_input_tokens = input_tokens - cached_input_tokens
    cost = (
        Decimal(uncached_input_tokens) * prices["input_per_million"]
        + Decimal(cached_input_tokens) * prices["cached_input_per_million"]
        + Decimal(output_tokens) * prices["output_per_million"]
    ) / Decimal("1000000")
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
