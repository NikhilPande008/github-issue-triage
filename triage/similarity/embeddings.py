from math import sqrt
from typing import Protocol


class EmbeddingProvider(Protocol):
    provider: str
    model: str
    def embed(self, text: str) -> list[float]: ...


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    denominator = sqrt(sum(value * value for value in left)) * sqrt(sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0
