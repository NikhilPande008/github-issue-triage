import type { TimelineAttempt } from "../services/api";

export function Timeline({ attempts }: { attempts: TimelineAttempt[] }) {
  return <section className="card"><h2>Timeline</h2>{attempts.length ? <ol className="timeline">{attempts.map((attempt) => <li key={attempt.attempt_number}><strong>Attempt {attempt.attempt_number}</strong><span>{attempt.action}</span><span>{attempt.result}</span>{attempt.revision_reason && <p>Revision: {attempt.revision_reason}</p>}</li>)}</ol> : <p>No attempt timeline was recorded.</p>}</section>;
}
