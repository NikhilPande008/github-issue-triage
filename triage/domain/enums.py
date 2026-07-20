from enum import StrEnum


class InvestigationStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Classification(StrEnum):
    REPRODUCED = "REPRODUCED"
    NEEDS_INFO = "NEEDS_INFO"
    WONT_REPRO = "WONT_REPRO"
    NOT_A_BUG = "NOT_A_BUG"
    DUPLICATE = "DUPLICATE"
