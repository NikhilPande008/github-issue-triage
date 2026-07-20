#!/usr/bin/env python3
"""Disposable feasibility spike: can Codex create an assertion-failing requests test?"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
IMAGE = "requests-feasibility-spike:latest"
REPO_URL = "https://github.com/psf/requests.git"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run(command: list[str], log, *, cwd: str | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
    log.write("\n$ " + " ".join(command) + "\n")
    log.flush()
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write(result.stdout)
    log.write(f"[exit {result.returncode}]\n")
    log.flush()
    if check and result.returncode:
        raise RuntimeError(f"command failed: {' '.join(command)}")
    return result


def api_json(url: str) -> object:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "requests-feasibility-spike"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_issue(number: int) -> dict[str, object]:
    issue = api_json(f"https://api.github.com/repos/psf/requests/issues/{number}")
    comments = api_json(f"https://api.github.com/repos/psf/requests/issues/{number}/comments")
    if not isinstance(issue, dict) or not isinstance(comments, list):
        raise RuntimeError("GitHub returned an unexpected issue payload")
    return {
        "number": number,
        "title": issue.get("title", ""),
        "body": issue.get("body", ""),
        "comments": [
            {"author": c.get("user", {}).get("login", ""), "body": c.get("body", "")}
            for c in comments if isinstance(c, dict)
        ],
        "url": issue.get("html_url", ""),
    }


def extract_issue(issue: dict[str, object]) -> dict[str, object]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for the GPT-5.6 extraction step")
    prompt = """Extract only the facts needed to reproduce this GitHub issue in psf/requests. Return strict JSON with keys: summary, expected_behavior, observed_behavior, reproduction_clues, relevant_versions, uncertainty. Do not propose code changes or tests.\n\nIssue:\n""" + json.dumps(issue)
    payload = json.dumps({"model": "gpt-5.6", "input": prompt}).encode()
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"GPT extraction failed: HTTP {error.code}: {error.read().decode(errors='replace')}") from error
    text = result.get("output_text", "") if isinstance(result, dict) else ""
    if not text:
        raise RuntimeError("GPT extraction returned no output_text")
    try:
        extracted = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError("GPT extraction did not return strict JSON") from error
    if not isinstance(extracted, dict):
        raise RuntimeError("GPT extraction did not return a JSON object")
    return extracted


def docker(log, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return run(["docker", *args], log, check=check)


def docker_exec(log, container: str, command: str) -> subprocess.CompletedProcess[str]:
    return docker(log, "exec", container, "sh", "-lc", command)


def assertion_failure(pytest_output: str) -> bool:
    # Pytest prints this for ordinary `assert` rewrites; collection/import/syntax failures do not.
    return bool(re.search(r"(?:^|\n)E\s+AssertionError(?::|$)", pytest_output))


def changed_test(diff_names: str) -> bool:
    return any(name.startswith("tests/") and name.endswith(".py") for name in diff_names.splitlines())


def only_test_changes(diff_names: str) -> bool:
    names = [name for name in diff_names.splitlines() if name]
    return bool(names) and all(name.startswith("tests/") and name.endswith(".py") for name in names)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", required=True, type=int, help="psf/requests GitHub issue number")
    args = parser.parse_args()

    if shutil.which("docker") is None:
        print("NOT REPRODUCED")
        print("Docker is required.", file=sys.stderr)
        return 2

    ARTIFACTS.mkdir(exist_ok=True)
    for name in ("terminal.log", "pytest_output.txt", "git.diff", "extraction.json", "final_report.json"):
        (ARTIFACTS / name).unlink(missing_ok=True)

    report: dict[str, object] = {"issue": args.issue, "status": "NOT REPRODUCED", "attempts": 0, "assertsFailure": False}
    container = f"requests-spike-{os.getpid()}-{int(time.time())}"
    extraction: dict[str, object] | None = None

    with (ARTIFACTS / "terminal.log").open("w", encoding="utf-8") as log:
        try:
            issue = fetch_issue(args.issue)
            extraction = extract_issue(issue)
            write_json(ARTIFACTS / "extraction.json", {"issue": issue, "extraction": extraction})

            docker(log, "build", "-t", IMAGE, str(ROOT), check=True)
            # Let Codex write its transient state in the container, but mount only its existing login read-only.
            auth = Path.home() / ".codex" / "auth.json"
            if not auth.is_file():
                raise RuntimeError("Codex login not found at ~/.codex/auth.json; run `codex login` first")
            docker(log, "run", "-d", "--name", container, "-v", f"{ARTIFACTS.resolve()}:/artifacts", "-v", f"{auth}:/root/.codex/auth.json:ro", IMAGE, "sleep", "infinity", check=True)
            docker_exec(log, container, "git clone --depth 1 " + REPO_URL + " /work/repo")
            docker_exec(log, container, "cd /work/repo && python -m pip install --upgrade pip && python -m pip install -r requirements-dev.txt")
            baseline = docker_exec(log, container, "cd /work/repo && python -m pytest -q")
            if baseline.returncode:
                raise RuntimeError("baseline pytest did not pass; refusing to attribute a later failure to the new test")

            extraction_text = json.dumps(extraction, indent=2)
            for attempt in range(1, 4):
                report["attempts"] = attempt
                prompt = textwrap.dedent(f"""
                    You are the investigation agent for a disposable feasibility spike. Work only in /work/repo, which is psf/requests at HEAD.
                    Issue extraction (produced by another model; do not redo extraction):
                    {extraction_text}

                    This is attempt {attempt} of at most 3. Inspect the repository and issue clues, form a concrete hypothesis, then modify or add a pytest test under tests/ that demonstrates the reported bug. Run pytest yourself and inspect the result. The goal is a NEW test assertion that fails at unmodified HEAD because the product behavior is wrong. Do not fix production code. Do not introduce syntax/import/collection errors, skips, xfails, artificial `assert False`, or assertions unrelated to the issue. If the hypothesis fails, leave useful evidence and revise it on the next attempt. End after this attempt.
                """)
                docker_exec(log, container, "cd /work/repo && codex exec --sandbox danger-full-access --ephemeral " + shlex.quote(prompt))
                names = docker_exec(log, container, "cd /work/repo && git diff --name-only").stdout
                pytest = docker_exec(log, container, "cd /work/repo && python -m pytest -q")
                (ARTIFACTS / "pytest_output.txt").write_text(pytest.stdout, encoding="utf-8")
                diff = docker_exec(log, container, "cd /work/repo && git diff --no-ext-diff").stdout
                (ARTIFACTS / "git.diff").write_text(diff, encoding="utf-8")
                if only_test_changes(names) and changed_test(names) and pytest.returncode != 0 and assertion_failure(pytest.stdout):
                    report.update({"status": "REPRODUCED", "assertsFailure": True, "changed_tests": names.splitlines()})
                    break
        except Exception as error:
            report["error"] = str(error)
            if extraction is None:
                write_json(ARTIFACTS / "extraction.json", {"error": str(error)})
            # Required artifact names exist even if setup cannot begin.
            for name in ("pytest_output.txt", "git.diff"):
                (ARTIFACTS / name).touch(exist_ok=True)
        finally:
            docker(log, "rm", "-f", container)

    write_json(ARTIFACTS / "final_report.json", report)
    print(report["status"])
    return 0 if report["status"] == "REPRODUCED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
