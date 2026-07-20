# Disposable feasibility spike

Run from the repository root:

```sh
OPENAI_API_KEY=... python spike/run_spike.py --issue 1234
```

The script fetches the public `psf/requests` issue and comments, has GPT-5.6 perform extraction only, then starts a fresh Python 3.12 Docker container. Codex, running inside that container, gets up to three attempts to add a failing pytest assertion at requests HEAD.

Codex authentication must already be available in `~/.codex`; it is mounted read-only into the container and never copied to `artifacts/`.

Artifacts are overwritten per run:

- `terminal.log`
- `pytest_output.txt`
- `git.diff`
- `extraction.json`
- `final_report.json`

`REPRODUCED` means both a changed `tests/*.py` file and pytest output containing an `AssertionError` were observed. Every other outcome is `NOT REPRODUCED`.
