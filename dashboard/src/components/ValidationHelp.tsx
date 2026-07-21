export const ASSERTS_FAILURE_EXPLANATION =
  "Set only when the deterministic pytest-evidence validator confirms a genuine test assertion failure; it is never decided by a model.";
export const VALIDATION_REASON_EXPLANATION =
  "The deterministic validator’s evidence-based reason for accepting or rejecting the pytest result.";

export function ValidationHelp({ kind }: { kind: "assertsFailure" | "validation reason" }) {
  const explanation = kind === "assertsFailure" ? ASSERTS_FAILURE_EXPLANATION : VALIDATION_REASON_EXPLANATION;
  return <details className="validation-help"><summary aria-label={`About ${kind}`}><span aria-hidden="true">ⓘ</span><span className="sr-only">About {kind}</span></summary><span className="validation-help-copy">{explanation}</span></details>;
}
