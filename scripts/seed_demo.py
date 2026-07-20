"""Install the committed, read-only dashboard demo without API keys."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATABASE = ROOT / "demo" / "seed" / "triage-demo.db"
SOURCE_ARTIFACTS = ROOT / "demo" / "seed" / "artifacts"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the committed dashboard demo data.")
    parser.add_argument("--database", type=Path, default=ROOT / "triage.db")
    parser.add_argument("--artifacts", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--force", action="store_true", help="Replace existing demo destinations.")
    args = parser.parse_args()
    destinations = (args.database, args.artifacts)
    existing = [path for path in destinations if path.exists()]
    if existing and not args.force:
        parser.error("destination exists; pass --force to replace: " + ", ".join(str(path) for path in existing))
    if args.database.exists():
        args.database.unlink()
    if args.artifacts.exists():
        shutil.rmtree(args.artifacts)
    args.database.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_DATABASE, args.database)
    shutil.copytree(SOURCE_ARTIFACTS, args.artifacts)
    print(f"Installed demo database at {args.database} and artifacts at {args.artifacts}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
