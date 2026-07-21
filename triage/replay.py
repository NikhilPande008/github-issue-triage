"""Safe best-effort replay planning from persisted reproducibility manifests."""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


REQUIRED = {"repository", "repository_commit", "runner", "focused_test_command", "network_policy", "dependency_snapshot"}


def create_replay_plan(manifest_path: Path, artifacts_root: Path) -> Path:
    """Validate immutable inputs and create a separate replay record.

    It intentionally never overwrites original evidence or silently substitutes
    missing image/dependency inputs. Execution remains best-effort because base
    image digests and external package registries may no longer be available.
    """
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Replay unavailable: reproducibility manifest is missing or invalid") from error
    missing = sorted(key for key in REQUIRED if not manifest.get(key))
    if missing:
        raise ValueError("Replay unavailable: manifest lacks " + ", ".join(missing))
    replay_dir = artifacts_root / "replays" / str(uuid4())
    replay_dir.mkdir(parents=True, exist_ok=False)
    plan = {
        "source_manifest": str(manifest_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "immutable_inputs": {key: manifest[key] for key in REQUIRED},
        "exact_replay_guarantee": bool(manifest.get("sandbox_image_digests") and manifest.get("lockfile_sha256")),
        "warning": "This is a separate replay plan. Original evidence is unchanged; unavailable images or dependencies prevent exact replay.",
    }
    output = replay_dir / "replay_plan.json"
    output.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    return output
