import type { TimelineAttempt } from "../services/api";

export function Timeline({ attempts }: { attempts: TimelineAttempt[] }) {
  return <section className="card"><h2>Attempts</h2>{attempts.length ? <ol className="timeline">{attempts.map((attempt) => <li key={attempt.attempt_number}><strong>Attempt {attempt.attempt_number} · {attempt.result}</strong><span>{attempt.action}</span><p><b>Hypothesis:</b> {attempt.hypothesis}</p>{attempt.revision_reason && <p><b>Revision:</b> {attempt.revision_reason}</p>}{attempt.duration_ms !== null && <p><b>Duration:</b> {(attempt.duration_ms / 1000).toFixed(1)}s</p>}</li>)}</ol> : <p>No attempt timeline was recorded.</p>}</section>;
}
