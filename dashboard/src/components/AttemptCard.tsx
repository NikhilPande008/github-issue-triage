import type { TimelineAttempt } from "../services/api";

export function AttemptCard({ attempt }: { attempt: TimelineAttempt }) {
  return <details className="card attempt" open><summary>Attempt {attempt.attempt_number}: {attempt.result}</summary><p><b>Hypothesis:</b> {attempt.hypothesis}</p>{attempt.revision_reason && <p><b>Revision reason:</b> {attempt.revision_reason}</p>}<p><b>Action:</b> {attempt.action}</p>{attempt.duration_ms !== null && <p><b>Duration:</b> {(attempt.duration_ms / 1000).toFixed(1)}s</p>}</details>;
}
