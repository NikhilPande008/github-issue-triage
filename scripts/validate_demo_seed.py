"""Deterministically validate the committed offline demo seed."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def alembic_head() -> str:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head() or ""


def validate(database: Path, artifacts: Path, manifest_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"cannot read manifest: {error}"]
    required = {"schema_version", "exported_at", "investigations"}
    if not required.issubset(manifest): errors.append("manifest is missing required top-level fields")
    entries = manifest.get("investigations", [])
    if not entries: errors.append("manifest contains no investigations")
    ids = [entry.get("id") for entry in entries]
    if len(ids) != len(set(ids)): errors.append("manifest contains duplicate investigation IDs")
    try:
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
    except sqlite3.Error as error:
        return [f"cannot open demo database: {error}"]
    with connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if not version or version["version_num"] != alembic_head(): errors.append("demo database is not at the current Alembic head")
        confirmed = completed_no_gap = 0
        artifact_root = artifacts.resolve()
        for entry in entries:
            row = connection.execute("SELECT repository, issue_number, issue_title, classification, asserts_failure, status FROM investigations WHERE id = ?", (entry.get("id"),)).fetchone()
            if not row:
                errors.append(f"manifest investigation is absent: {entry.get('id')}"); continue
            for field in ("repository", "issue_number", "title", "classification", "assertsFailure"):
                actual = {"title": "issue_title", "assertsFailure": "asserts_failure"}.get(field, field)
                if entry.get(field) != row[actual]: errors.append(f"manifest {field} does not match database for {entry.get('id')}")
            artifact_rows = connection.execute("SELECT path FROM artifacts WHERE investigation_id = ?", (entry.get("id"),)).fetchall()
            if entry.get("artifact_count") != len(artifact_rows): errors.append(f"manifest artifact_count does not match database for {entry.get('id')}")
            for artifact in artifact_rows:
                relative = Path(artifact["path"])
                if not relative.parts or relative.parts[0] != "artifacts": errors.append(f"artifact path has unexpected root: {relative}"); continue
                destination = (artifacts / Path(*relative.parts[1:])).resolve()
                if artifact_root not in destination.parents or not destination.is_file(): errors.append(f"artifact missing or outside demo root: {relative}")
            confirmed += row["classification"] == "BEHAVIOR_GAP_CONFIRMED"
            completed_no_gap += row["status"] == "COMPLETED_NO_GAP" and row["classification"] is not None
        if not confirmed: errors.append("demo lacks a confirmed behavior-gap case")
        if not completed_no_gap: errors.append("demo lacks a classified completed-no-gap case")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the committed offline demo seed.")
    parser.add_argument("--database", type=Path, default=ROOT / "demo" / "seed" / "triage-demo.db")
    parser.add_argument("--artifacts", type=Path, default=ROOT / "demo" / "seed" / "artifacts")
    parser.add_argument("--manifest", type=Path, default=ROOT / "demo" / "seed" / "demo-manifest.json")
    args = parser.parse_args(argv)
    errors = validate(args.database, args.artifacts, args.manifest)
    if errors:
        print("Demo seed validation failed:\n- " + "\n- ".join(errors)); return 1
    print("Demo seed validation passed."); return 0


if __name__ == "__main__":
    raise SystemExit(main())
