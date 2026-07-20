import json
from pathlib import Path

from triage.github.models import GitHubIssue

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "extraction_system_v2.md"
USER_PROMPT_PATH = PROMPTS_DIR / "extraction_user_v1.md"


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def render_user_prompt(issue: GitHubIssue) -> str:
    template = USER_PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{{issue_json}}", json.dumps(issue.model_dump(mode="json"), indent=2))
