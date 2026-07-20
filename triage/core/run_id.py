from uuid import uuid4


def new_run_id() -> str:
    """Return a unique identifier to attach to one investigation's logs."""
    return str(uuid4())
