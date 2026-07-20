from fastapi import FastAPI

from triage.api.routes.artifacts import router as artifacts_router
from triage.api.routes.investigations import router as investigations_router
from triage.config.settings import Settings
from triage.core.logging import configure_logging

settings = Settings()
configure_logging(settings.log_level)

app = FastAPI()
app.include_router(investigations_router)
app.include_router(artifacts_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
