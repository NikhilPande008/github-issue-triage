MAX_TERMINAL_EVIDENCE_CHARS = 12_000
TRUNCATION_NOTICE = "[Earlier terminal output omitted; final output preserved.]\n"


def tail_terminal_evidence(text: str, limit: int = MAX_TERMINAL_EVIDENCE_CHARS) -> str:
    """Bound prompt evidence while retaining pytest failures and final summaries."""
    if len(text) <= limit:
        return text
    retained = limit - len(TRUNCATION_NOTICE)
    return TRUNCATION_NOTICE + text[-retained:]
