# Codex investigation prompt v1

You are investigating a reported defect in the current repository. Reason only from the issue extraction and the previous attempt evidence supplied below.

Form a concrete hypothesis before acting. Prefer the smallest test-focused change that can demonstrate the reported behavior. Modify tests rather than production code unless production changes are necessary to understand the failure. Do not make broad refactors, speculative fixes, classifications, or unrelated cleanup.

Run focused pytest commands when useful. Stop once the test suite demonstrates a failure related to the report. Do not claim success without evidence.

## Issue extraction

{{extraction_json}}

## Attempt

{{attempt_number}}

## Revision reason

{{revision_reason}}

## Previous evidence

{{previous_evidence}}
