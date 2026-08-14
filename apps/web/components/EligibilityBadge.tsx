// The eligibility partition is the safety property that keeps ranking honest, so it gets its own
// badge: BLOCKED is a definitive failure, UNRESOLVED is missing evidence, and only ELIGIBLE
// candidates are ever ranked against each other.
const LABELS: Record<string,string> = {
  eligible: "ELIGIBLE",
  unresolved: "UNRESOLVED — EVIDENCE OUTSTANDING",
  blocked: "BLOCKED — DEFINITIVE FAILURE",
};

export function EligibilityBadge({eligibility}:{eligibility:string}){
  return <span className="badge" data-eligibility={eligibility} data-testid={`eligibility-${eligibility}`}>
    {LABELS[eligibility] ?? String(eligibility).toUpperCase()}
  </span>;
}
